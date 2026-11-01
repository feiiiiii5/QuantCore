"""Tushare Pro provider: recorded fixtures by default, live only with an explicit token.

Fixture mode (the default in tests) reads JSON/CSV files from ``fixture_dir`` with the
same field names as the Tushare Pro endpoints.  Live mode is opt-in and requires
``allow_network=True`` plus a token from the constructor, ``TUSHARE_TOKEN`` or keyring.

Unit handling ``TODO(verify)``: Tushare ``daily.vol`` is in lots (手, 100 shares) and
``daily.amount`` in thousand CNY; both are converted to shares/CNY here.  Field lists
and permissions must be re-verified against the official Tushare Pro documentation
before relying on live data.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import (
    normalize_bars,
    normalize_corporate_actions,
    normalize_financials,
    normalize_securities,
)
from ..errors import ProviderPermissionError, ProviderUnavailableError
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    RetryPolicy,
    retry_call,
    subset_frame,
)

FIXTURE_FILES: dict[str, str] = {
    "calendar": "calendar",
    "securities": "securities",
    "daily_bars": "daily_bars",
    "financials": "financials",
    "corporate_actions": "corporate_actions",
}

TUSHARE_PERMISSION = ProviderPermission(
    requires_credentials=True,
    env_vars=("TUSHARE_TOKEN",),
    keyring_service="quantcore.tushare",
    license_note="Tushare Pro token required; observe the provider's terms and call quotas.",
)

TUSHARE_QUOTA = ProviderQuota(
    max_calls=500,
    window_seconds=60.0,
    daily_call_limit=50_000,
    tier="pro-free",
    notes="TODO(verify): points-based quota depends on the account tier",
)


def _split_ts_code(value: str) -> tuple[str, str, str]:
    """Split ``600000.SH`` into ``(code, exchange, sec_id)``."""
    text = str(value).strip().upper()
    if "." in text:
        code, exchange = text.split(".", 1)
    else:
        code, exchange = text, ""
    if not exchange:
        exchange = "SH" if code.startswith(("6", "9")) else "SZ"
    return code, exchange, f"{exchange}.{code}"


def normalize_tushare_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise Tushare ``daily`` (+ limit/suspend/adj) rows to canonical bars."""
    out = frame.copy()
    if "ts_code" in out.columns:
        split = out["ts_code"].map(_split_ts_code)
        out["sec_id"] = [item[2] for item in split]
        out["code"] = [item[0] for item in split]
    rename = {
        "trade_date": "date",
        "vol": "volume",
        "up_limit": "limit_up",
        "down_limit": "limit_down",
        "suspend_flag": "suspended",
        "limit": "limit_up",
    }
    out = out.rename(columns={key: value for key, value in rename.items() if key in out.columns})
    if "date" in out.columns:
        out["date"] = out["date"].map(to_date_int).astype("int32")
    if "volume" in out.columns:
        out["volume"] = (pd.to_numeric(out["volume"], errors="coerce").fillna(0) * 100).round()
    if "amount" in out.columns:
        # TODO(verify): Tushare daily.amount is in thousand CNY.
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0) * 1000.0
    if "suspended" in out.columns:
        out["suspended"] = out["suspended"].fillna(0).astype(bool)
    for column in ("adj_factor", "limit_up", "limit_down"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "adj_factor" not in out.columns:
        out["adj_factor"] = 1.0
    if "pre_close" not in out.columns:
        out["pre_close"] = out.groupby("sec_id")["close"].shift(1)
    if "turnover" not in out.columns:
        shares = pd.to_numeric(out.get("float_shares", 0), errors="coerce").fillna(0.0)
        out["turnover"] = np.where(shares > 0, out["volume"] / shares, 0.0)
    if "total_shares" not in out.columns:
        out["total_shares"] = 0
    if "float_shares" not in out.columns:
        out["float_shares"] = 0
    for column in ("mktcap", "float_mktcap"):
        if column not in out.columns:
            out[column] = 0.0
    if "st" not in out.columns:
        out["st"] = False
    out["st"] = out["st"].fillna(False).astype(bool)
    out["source"] = "TUSHARE_FIXTURE"
    return normalize_bars(out)


def normalize_tushare_securities(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise Tushare ``stock_basic`` rows to the canonical security master."""
    out = frame.copy()
    if "ts_code" in out.columns:
        split = out["ts_code"].map(_split_ts_code)
        out["sec_id"] = [item[2] for item in split]
        out["code"] = (
            out["symbol"].astype(str) if "symbol" in out.columns else [item[0] for item in split]
        )
        out["exchange"] = [item[1] for item in split]
    board = {
        "主板": "MAIN",
        "创业板": "GEM",
        "科创板": "STAR",
        "北交所": "BSE",
    }
    if "market" in out.columns:
        out["board"] = out["market"].map(board).fillna("MAIN")
    if "industry" not in out.columns:
        out["industry"] = ""
    for column in ("list_date", "delist_date"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype("int32")
    if "sec_type" not in out.columns:
        out["sec_type"] = "STOCK"
    out["source"] = "TUSHARE_FIXTURE"
    return normalize_securities(out)


def normalize_tushare_financials(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise Tushare ``fina_indicator`` rows to canonical PIT financials."""
    out = frame.copy()
    if "ts_code" in out.columns:
        out["sec_id"] = out["ts_code"].map(lambda value: _split_ts_code(value)[2])
    rename = {
        "n_income": "net_profit",
        "total_hldr_eqy_exc_min_int": "total_equity",
    }
    out = out.rename(columns={key: value for key, value in rename.items() if key in out.columns})
    for column in ("end_date", "ann_date", "f_ann_date"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype("int32")
    for column in ("report_type", "update_flag"):
        if column not in out.columns:
            out[column] = "1"
        out[column] = out[column].astype(str)
    for column in ("revenue", "net_profit", "total_assets", "total_equity", "roe", "eps", "bps"):
        if column not in out.columns:
            out[column] = np.nan
    out["dividend_per_share"] = pd.to_numeric(
        out.get("dividend_per_share", 0), errors="coerce"
    ).fillna(0.0)
    out["source"] = "TUSHARE_FIXTURE"
    return normalize_financials(out)


def normalize_tushare_actions(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise Tushare ``dividend`` rows to canonical corporate actions."""
    out = frame.copy()
    if "ts_code" in out.columns:
        out["sec_id"] = out["ts_code"].map(lambda value: _split_ts_code(value)[2])
    rename = {
        "cash_div_tax": "cash_per_share",
        "stk_div": "split_ratio",
    }
    out = out.rename(columns={key: value for key, value in rename.items() if key in out.columns})
    if "split_ratio" in out.columns:
        out["split_ratio"] = 1.0 + pd.to_numeric(out["split_ratio"], errors="coerce").fillna(0.0)
    else:
        out["split_ratio"] = 1.0
    for column in ("ann_date", "record_date", "ex_date", "pay_date"):
        if column not in out.columns:
            out[column] = 0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype("int32")
    if "rights_ratio" not in out.columns:
        out["rights_ratio"] = 0.0
    if "rights_price" not in out.columns:
        out["rights_price"] = 0.0
    out["source"] = "TUSHARE_FIXTURE"
    return normalize_corporate_actions(out)


class TushareProvider(DataProvider):
    """Tushare Pro adapter (fixture-first, live opt-in)."""

    name: ClassVar[str] = "tushare"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        financials=True, corporate_actions=True
    )
    quota: ClassVar[ProviderQuota] = TUSHARE_QUOTA
    permission: ClassVar[ProviderPermission] = TUSHARE_PERMISSION

    def __init__(
        self,
        fixture_dir: str | Path | None = None,
        token: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.fixture_dir = Path(fixture_dir) if fixture_dir is not None else None
        self._token = token
        self._pro: Any | None = None
        self._cache: dict[str, pd.DataFrame] = {}

    # -- lifecycle --------------------------------------------------------
    @property
    def fixture_mode(self) -> bool:
        return self.fixture_dir is not None

    def resolve_token(self) -> str | None:
        return self._token or self.permission.resolve_credential()

    def ensure_available(self) -> None:
        if self.fixture_mode:
            assert self.fixture_dir is not None
            if not self.fixture_dir.exists():
                raise ProviderUnavailableError(
                    f"tushare fixture_dir does not exist: {self.fixture_dir}"
                )
            return
        if not self.allow_network:
            raise ProviderPermissionError(
                "Tushare live mode is disabled (allow_network=False); use a fixture_dir for "
                "offline tests or pass allow_network=True with a token"
            )
        if not self.resolve_token():
            self.require_permission()

    def _fixture_frame(self, dataset: str) -> pd.DataFrame:
        assert self.fixture_dir is not None
        base = self.fixture_dir / FIXTURE_FILES[dataset]
        for suffix in (".json", ".csv", ".parquet"):
            path = base.with_suffix(suffix)
            if path.exists():
                if suffix == ".json":
                    return pd.read_json(path)
                if suffix == ".csv":
                    return pd.read_csv(path)
                return pd.read_parquet(path)
        raise ProviderUnavailableError(
            f"tushare fixture for {dataset!r} not found under {self.fixture_dir}"
        )

    def _live_pro(self) -> Any:
        if self._pro is not None:
            return self._pro
        if not self.allow_network:
            raise ProviderPermissionError("network access is disabled for TushareProvider")
        token = self.resolve_token()
        if not token:
            self.require_permission()
        try:
            import tushare
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ProviderUnavailableError(
                "tushare is not installed; install the optional 'tushare' package for live mode"
            ) from exc
        self.limiter.acquire()
        self._pro = tushare.pro_api(token)
        return self._pro

    def _live_call(self, endpoint: str, **params: Any) -> pd.DataFrame:
        pro = self._live_pro()

        def call() -> pd.DataFrame:
            self.limiter.acquire()
            self._request_count += 1
            result = getattr(pro, endpoint)(**params)
            if not isinstance(result, pd.DataFrame):
                return pd.DataFrame(result)
            return result

        return retry_call(call, self.retry_policy or RetryPolicy())

    # -- contract ---------------------------------------------------------
    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        start_i, end_i = to_date_int(start), to_date_int(end)
        if self.fixture_mode:
            frame = self._fixture_frame("calendar")
            column = "date" if "date" in frame.columns else frame.columns[0]
            return TradingCalendar.from_dates(frame[column].tolist()).slice(start_i, end_i)
        self.ensure_available()
        frame = self._live_call(
            "trade_cal",
            exchange="SSE",
            start_date=str(start_i),
            end_date=str(end_i),
            is_open="1",
        )
        # TODO(verify): Tushare trade_cal returns cal_date/is_open columns.
        return TradingCalendar.from_dates(frame["cal_date"].tolist()).slice(start_i, end_i)

    def fetch_security_master(self) -> pd.DataFrame:
        if self.fixture_mode:
            return normalize_tushare_securities(self._fixture_frame("securities"))
        self.ensure_available()
        frame = self._live_call("stock_basic", exchange="", list_status="L")
        # TODO(verify): stock_basic paginates by list_status (L/D/P).
        return normalize_tushare_securities(frame)

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        start_i, end_i = to_date_int(start), to_date_int(end)
        if self.fixture_mode:
            frame = self._fixture_frame("daily_bars")
            normalized = normalize_tushare_daily(frame)
            return subset_frame(normalized, start_i, end_i, codes=codes)
        self.ensure_available()
        # Live path: one call per security is required by Tushare's API; keep it simple.
        code_list = list(codes or [])
        if not code_list:
            raise ProviderUnavailableError("live Tushare bars require an explicit code list")
        frames = []
        for code in code_list:
            frame = self._live_call(
                "daily", ts_code=code, start_date=str(start_i), end_date=str(end_i)
            )
            if frame.empty:
                continue
            adj = self._live_call(
                "adj_factor", ts_code=code, start_date=str(start_i), end_date=str(end_i)
            )
            limits = self._live_call(
                "stk_limit", ts_code=code, start_date=str(start_i), end_date=str(end_i)
            )
            frame = frame.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
            if not limits.empty:
                frame = frame.merge(
                    limits[["trade_date", "up_limit", "down_limit"]], on="trade_date", how="left"
                )
            frames.append(frame)
        if not frames:
            return normalize_tushare_daily(
                pd.DataFrame(columns=["ts_code", "trade_date", "open", "high", "low", "close"])
            )
        return subset_frame(
            normalize_tushare_daily(pd.concat(frames, ignore_index=True)),
            start_i,
            end_i,
            codes=codes,
        )

    def fetch_financials(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("financials")
        if self.fixture_mode:
            frame = normalize_tushare_financials(self._fixture_frame("financials"))
            return subset_frame(
                frame, to_date_int(start), to_date_int(end), date_column="ann_date", codes=codes
            )
        self.ensure_available()
        raise ProviderUnavailableError(
            "live Tushare financials are not implemented yet; fixture mode is supported (M2)"
        )

    def fetch_corporate_actions(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("corporate_actions")
        if self.fixture_mode:
            frame = normalize_tushare_actions(self._fixture_frame("corporate_actions"))
            return subset_frame(
                frame, to_date_int(start), to_date_int(end), date_column="ex_date", codes=codes
            )
        self.ensure_available()
        raise ProviderUnavailableError(
            "live Tushare corporate actions are not implemented yet; fixture mode is supported (M2)"
        )
