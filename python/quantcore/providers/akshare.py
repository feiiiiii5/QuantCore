"""AKShare adapter (contract-level, lazy import, fixture/fake-module tested).

AKShare is a complementary/fallback source: it is *not* a runtime dependency.  The
adapter only supports daily bars; limits are derived from the board prefix and must be
re-verified against official rules before real research (``TODO(verify)``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import normalize_bars
from ..errors import ProviderPermissionError, ProviderUnavailableError
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    subset_frame,
)

AKSHARE_COLUMNS: dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "换手率": "turnover",
}


def code_to_sec_id(code: str) -> tuple[str, str]:
    """Map a 6-digit A-share code to ``(sec_id, exchange)``."""
    text = str(code).strip().zfill(6)
    if text.startswith(("6", "9")):
        exchange = "SH"
    elif text.startswith(("8", "4")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"{exchange}.{text}", exchange


def board_limit_pct(code: str) -> float:
    """Board price-limit percentage derived from the code prefix (``TODO(verify)``)."""
    text = str(code).zfill(6)
    if text.startswith("300") or text.startswith("688"):
        return 0.20
    if text.startswith(("8", "4")):
        return 0.30
    return 0.10


def normalize_akshare_daily(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    """Normalise an AKShare ``stock_zh_a_hist`` frame to canonical bars."""
    out = frame.rename(
        columns={key: value for key, value in AKSHARE_COLUMNS.items() if key in frame}
    )
    missing = [
        column for column in ("date", "open", "high", "low", "close") if column not in out.columns
    ]
    if missing:
        raise ProviderUnavailableError(f"akshare frame is missing columns: {missing}")
    sec_id, _ = code_to_sec_id(code)
    out = out.copy()
    out["date"] = out["date"].map(to_date_int).astype("int32")
    out["sec_id"] = sec_id
    out["code"] = str(code).zfill(6)
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "volume" in out.columns:  # TODO(verify): AKShare reports volume in lots (手)
        out["volume"] = (pd.to_numeric(out["volume"], errors="coerce").fillna(0) * 100).round()
    else:
        out["volume"] = 0
    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0.0)
    else:
        out["amount"] = (out["close"] * out["volume"]).round(2)
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    out["pre_close"] = out["close"].shift(1)
    pct = board_limit_pct(code)
    out["limit_up"] = np.round(out["pre_close"] * (1.0 + pct), 2)
    out["limit_down"] = np.round(out["pre_close"] * (1.0 - pct), 2)
    out["adj_factor"] = 1.0
    out["suspended"] = False
    out["st"] = False
    out["turnover"] = pd.to_numeric(out.get("turnover", 0.0), errors="coerce").fillna(0.0) / 100.0
    out["total_shares"] = 0
    out["float_shares"] = 0
    out["mktcap"] = 0.0
    out["float_mktcap"] = 0.0
    out["source"] = "AKSHARE"
    return normalize_bars(out)


class AKShareProvider(DataProvider):
    """Daily-bar adapter around ``akshare.stock_zh_a_hist``."""

    name: ClassVar[str] = "akshare"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        calendar=False, security_master=False, daily_bars=True
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=60,
        window_seconds=60.0,
        min_interval_seconds=0.5,
        tier="free",
        notes="TODO(verify): AKShare upstream rate limits vary by endpoint",
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission(
        license_note="AKShare scrapes public sites; upstream terms apply."
    )

    def __init__(self, module: Any | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._module = module

    def _ak(self) -> Any:
        if self._module is not None:
            return self._module
        if not self.allow_network:
            raise ProviderPermissionError(
                "AKShare network access is disabled; pass allow_network=True (and install akshare) "
                "or inject a module for contract tests"
            )
        try:  # lazy import: akshare is an optional dependency
            import akshare
        except ImportError as exc:
            raise ProviderUnavailableError(
                "akshare is not installed; install it to use the AKShare adapter"
            ) from exc
        self._module = akshare
        return akshare

    def ensure_available(self) -> None:
        self._ak()

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        raise ProviderUnavailableError("AKShare adapter does not provide a trading calendar")

    def fetch_security_master(self) -> pd.DataFrame:
        raise ProviderUnavailableError("AKShare adapter does not provide a security master")

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        module = self._ak()
        start_i, end_i = to_date_int(start), to_date_int(end)
        code_list = [str(code) for code in (codes or [])]
        if not code_list:
            raise ProviderUnavailableError("AKShare adapter requires an explicit code list")
        frames = []
        for code in code_list:
            self.limiter.acquire()
            self._request_count += 1
            raw = module.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=str(start_i),
                end_date=str(end_i),
                adjust="",
            )
            if raw is None or len(raw) == 0:
                continue
            frames.append(normalize_akshare_daily(pd.DataFrame(raw), code))
        if not frames:
            return pd.DataFrame(
                columns=list(
                    normalize_akshare_daily(
                        pd.DataFrame({"日期": [], "开盘": [], "收盘": [], "最高": [], "最低": []}),
                        code_list[0],
                    ).columns
                )
            )
        return subset_frame(pd.concat(frames, ignore_index=True), start_i, end_i, codes=codes)
