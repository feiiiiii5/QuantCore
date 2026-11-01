"""mootdx (通达信本地/在线行情) adapter (contract-level, lazy import).

Like the AKShare adapter this is a complementary source, not a runtime dependency.
Only daily bars are supported; unit conventions are marked ``TODO(verify)``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import normalize_bars
from ..errors import ProviderPermissionError, ProviderUnavailableError
from .akshare import board_limit_pct, code_to_sec_id
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    subset_frame,
)

MOOTDX_COLUMNS: dict[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "vol": "volume",
    "volume": "volume",
    "amount": "amount",
}

MOOTDX_DAILY_FREQUENCY = 9  # 9 = daily bars in mootdx's TDX frequency enum


def normalize_mootdx_daily(
    frame: pd.DataFrame, code: str, frequency: int = MOOTDX_DAILY_FREQUENCY
) -> pd.DataFrame:
    """Normalise a mootdx ``bars`` frame to canonical daily bars."""
    if frequency != MOOTDX_DAILY_FREQUENCY:
        raise ProviderUnavailableError("mootdx adapter only supports daily bars (frequency=9)")
    out = frame.copy()
    date_column = next(
        (column for column in ("datetime", "date", "trade_date") if column in out.columns), None
    )
    if date_column is not None:
        out["date"] = out[date_column].map(to_date_int).astype("int32")
    elif isinstance(out.index, pd.DatetimeIndex):
        out["date"] = [int(value.strftime("%Y%m%d")) for value in out.index]
    else:
        raise ProviderUnavailableError("mootdx frame has no date column or DatetimeIndex")
    out = out.rename(
        columns={key: value for key, value in MOOTDX_COLUMNS.items() if key in out.columns}
    )
    missing = [column for column in ("open", "high", "low", "close") if column not in out.columns]
    if missing:
        raise ProviderUnavailableError(f"mootdx frame is missing columns: {missing}")
    sec_id, _ = code_to_sec_id(code)
    out["sec_id"] = sec_id
    out["code"] = str(code).zfill(6)
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "volume" in out.columns:  # TODO(verify): mootdx vol unit is lots (手)
        out["volume"] = (pd.to_numeric(out["volume"], errors="coerce").fillna(0) * 100).round()
    else:
        out["volume"] = 0
    out["amount"] = (
        pd.to_numeric(out["amount"], errors="coerce").fillna(0.0)
        if "amount" in out.columns
        else (out["close"] * out["volume"]).round(2)
    )
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    out["pre_close"] = out["close"].shift(1)
    out["pre_close"] = out["pre_close"].fillna(out["open"]).fillna(out["close"])
    pct = board_limit_pct(code)
    out["limit_up"] = np.round(out["pre_close"] * (1.0 + pct), 2)
    out["limit_down"] = np.round(out["pre_close"] * (1.0 - pct), 2)
    out["adj_factor"] = 1.0
    out["suspended"] = False
    out["st"] = False
    out["turnover"] = 0.0
    out["total_shares"] = 0
    out["float_shares"] = 0
    out["mktcap"] = 0.0
    out["float_mktcap"] = 0.0
    out["source"] = "MOOTDX"
    return normalize_bars(out)


class MootdxProvider(DataProvider):
    """Daily-bar adapter around mootdx's TDX quote client."""

    name: ClassVar[str] = "mootdx"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        calendar=False, security_master=False, daily_bars=True
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=120,
        window_seconds=60.0,
        min_interval_seconds=0.25,
        tier="free",
        notes="TODO(verify): TDX server connection limits",
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission(
        license_note="TDX public quote servers; upstream terms apply."
    )

    def __init__(self, module: Any | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._module = module
        self._client: Any | None = None

    def _md(self) -> Any:
        if self._module is not None:
            return self._module
        if not self.allow_network:
            raise ProviderPermissionError(
                "mootdx network access is disabled; pass allow_network=True (and install mootdx) "
                "or inject a module for contract tests"
            )
        try:  # lazy import: mootdx is an optional dependency
            import mootdx.quotes  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderUnavailableError(
                "mootdx is not installed; install it to use the mootdx adapter"
            ) from exc
        self._module = mootdx.quotes
        return mootdx.quotes

    def _quotes_client(self) -> Any:
        if self._client is not None:
            return self._client
        module = self._md()
        self.limiter.acquire()
        self._request_count += 1
        self._client = module.Quotes.factory(market="std")
        return self._client

    def ensure_available(self) -> None:
        self._md()

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        raise ProviderUnavailableError("mootdx adapter does not provide a trading calendar")

    def fetch_security_master(self) -> pd.DataFrame:
        raise ProviderUnavailableError("mootdx adapter does not provide a security master")

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        start_i, end_i = to_date_int(start), to_date_int(end)
        client = self._quotes_client()
        code_list = [str(code) for code in (codes or [])]
        if not code_list:
            raise ProviderUnavailableError("mootdx adapter requires an explicit code list")
        frames = []
        for code in code_list:
            self.limiter.acquire()
            self._request_count += 1
            raw = client.bars(symbol=code, frequency=MOOTDX_DAILY_FREQUENCY, offset=800)
            if raw is None or len(raw) == 0:
                continue
            frames.append(normalize_mootdx_daily(pd.DataFrame(raw), code))
        if not frames:
            return pd.DataFrame(columns=["date", "sec_id", "code", "open", "high", "low", "close"])
        return subset_frame(pd.concat(frames, ignore_index=True), start_i, end_i, codes=codes)
