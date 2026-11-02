"""Eastmoney (东方财富) public-web provider: full A-share universe + daily bars.

OPTIONAL FALLBACK source. On some networks (including the dev machine used to record the
fixtures) push2/push2his intermittently answer with an empty reply after a handful of
requests; the primary real-data provider is quantcore.providers.sina. This adapter is kept
as a contract-complete fallback: no token, paginated clist universe, kline daily bars with
fqt=0 (raw) + fqt=1 (forward-adjusted) and approximate corporate actions derived from the
factor jump. Research and simulation only; no broker/order routing.

Units (verified against a recorded sample and cross-checked amount/volume): kline
volume is in lots (手) and is multiplied by 100 into canonical shares; amount is CNY (元);
prices are raw for fqt=0. Corporate actions are approximate (EASTMONEY_APPROX) and marked
TODO(verify) in docs/data-dictionary.md.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ClassVar

import httpx
import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import normalize_bars, normalize_corporate_actions
from ..errors import ProviderError, ProviderPermissionError
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    RateLimiter,
    RetryPolicy,
    retry_call,
)
from .public_web import (
    build_canonical_bars,
    code_to_sec_id,
    derive_adjustment,
    empty_corporate_actions,
    empty_public_bars,
    infer_board,
    normalize_code,
)

CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
INDEX_SECID = "1.000001"
PUBLIC_UT = "bd1d9ddb04089700cf9c27f6f7426281"  # public web-app id, not a credential
UNIVERSE_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
UNIVERSE_FIELDS = "f12,f14,f26"
KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"
KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
KLINE_COLUMNS: tuple[str, ...] = (
    "date",
    "open",
    "close",
    "high",
    "low",
    "volume",
    "amount",
    "amplitude",
    "pct_chg",
    "change",
    "turnover",
)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    "Accept": "application/json,text/plain,*/*",
}


class _RetryableRequestError(ProviderError):
    """Transient transport failure (timeout/throttle/empty reply) worth retrying."""


def secid_for_code(value: str) -> str:
    """Eastmoney secid: market 1 for SH main/STAR, 0 for SZ and BJ."""
    code = normalize_code(value)
    board = infer_board(code)
    market = "1" if board in {"MAIN", "STAR"} and code.startswith("6") else "0"
    return f"{market}.{code}"


def _date_or_zero(value: Any) -> int:
    try:
        return to_date_int(value)
    except (TypeError, ValueError):
        return 0


def universe_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Rows from a clist payload; Eastmoney returns diff as a list or as a dict."""
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        return [diff[key] for key in sorted(diff, key=lambda item: int(item))]
    return [dict(item) for item in diff if isinstance(item, Mapping)]


def normalize_eastmoney_universe(payload: Mapping[str, Any]) -> pd.DataFrame:
    """Normalise clist rows to the canonical security master (board from prefix)."""
    rows: list[dict[str, Any]] = []
    for item in universe_rows(payload):
        try:
            code = normalize_code(str(item.get("f12", "")))
            board = infer_board(code)
        except ProviderError:
            continue
        sec_id, exchange = code_to_sec_id(code)
        rows.append(
            {
                "sec_id": sec_id,
                "code": code,
                "exchange": exchange,
                "name": str(item.get("f14") or "").strip(),
                "board": board,
                "list_date": _date_or_zero(item.get("f26")),
                "delist_date": 0,
                "sec_type": "STOCK",
                "industry": "",
                "source": "EASTMONEY",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "sec_id",
            "code",
            "exchange",
            "name",
            "board",
            "list_date",
            "delist_date",
            "sec_type",
            "industry",
            "source",
        ],
    )


def parse_kline_payload(payload: Mapping[str, Any], code: str) -> pd.DataFrame:
    """Parse raw kline CSV strings into a frame (units untouched)."""
    data = payload.get("data") or {}
    raw_rows = data.get("klines") or []
    records: list[list[str]] = []
    for line in raw_rows:
        parts = str(line).split(",")
        if len(parts) != len(KLINE_COLUMNS):
            raise ProviderError(f"eastmoney kline row has {len(parts)} fields for {code}: {line!r}")
        records.append(parts)
    frame = pd.DataFrame(records, columns=list(KLINE_COLUMNS))
    if frame.empty:
        return frame
    frame["date"] = [to_date_int(value) for value in frame["date"]]
    frame["code"] = normalize_code(code)
    return frame.sort_values("date", kind="stable").reset_index(drop=True)


def normalize_eastmoney_kline(payload: Mapping[str, Any], code: str) -> pd.DataFrame:
    """Parse a kline payload into raw-price rows with canonical units (volume x100)."""
    frame = parse_kline_payload(payload, code)
    if frame.empty:
        return frame
    out = frame.copy()
    code_norm = normalize_code(code)
    out["sec_id"] = code_to_sec_id(code_norm)[0]
    for column in ("open", "close", "high", "low", "amount", "change"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce").fillna(0).round().astype("int64")
    out["volume"] = (volume * 100).astype("int64")  # 手 -> 股
    for column in ("amplitude", "pct_chg", "turnover"):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0) / 100.0
    out = out.dropna(subset=["open", "close", "high", "low"])
    return out.sort_values("date", kind="stable").reset_index(drop=True)


class EastmoneyProvider(DataProvider):
    """Full A-share universe + daily bars from Eastmoney public quote endpoints (fallback)."""

    name: ClassVar[str] = "eastmoney"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        financials=False, corporate_actions=True, realtime=False
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=120,
        window_seconds=60.0,
        min_interval_seconds=0.3,
        tier="public-web",
        notes=(
            "Unofficial public Eastmoney web endpoints; no token and no fallback guarantee. "
            "The dev network intermittently answers with an empty reply after a handful of "
            "requests; use as a fallback only. Self-imposed: <=2 concurrent, >=0.3s between "
            "request starts, 2 retries with exponential backoff. Do not redistribute."
        ),
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission(
        requires_credentials=False,
        license_note=(
            "Eastmoney public quote endpoints (unofficial, may rate-limit); personal research "
            "use only, fetched data must not be redistributed. Network access must be enabled "
            "explicitly (QC_ALLOW_NETWORK=1)."
        ),
    )

    def __init__(
        self,
        *,
        transport: Callable[[str, Mapping[str, Any]], Any] | None = None,
        codes: Iterable[str] | None = None,
        limit: int | None = None,
        max_workers: int = 2,
        page_size: int = 100,
        index_secid: str = INDEX_SECID,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        allow_network: bool = False,
    ) -> None:
        super().__init__(limiter=limiter, retry=retry, allow_network=allow_network)
        self._transport = transport
        self.codes = [normalize_code(value) for value in codes] if codes else None
        self.limit = int(limit) if limit is not None else None
        self.max_workers = max(1, min(4, int(max_workers)))
        self.page_size = max(1, int(page_size))
        self.index_secid = index_secid
        self._limiter_lock = threading.Lock()
        self._master: pd.DataFrame | None = None
        self._st_by_sec: dict[str, bool] = {}
        self._action_cache: dict[tuple[str, int, int], pd.DataFrame] = {}

    def ensure_available(self) -> None:
        if self._transport is not None or self.allow_network:
            return
        if os.environ.get("QC_ALLOW_NETWORK") == "1":
            self.allow_network = True
            return
        raise ProviderPermissionError(
            "eastmoney network access is disabled; set QC_ALLOW_NETWORK=1 or pass "
            "allow_network=True (public endpoints, no token; personal research use only)"
        )

    def _acquire(self) -> None:
        with self._limiter_lock:
            self.limiter.acquire()
            self._request_count += 1

    @staticmethod
    def _checked_payload(
        kind: str, params: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        rc = payload.get("rc", 0)
        if rc not in (0, None):
            detail = payload.get("msg") or payload.get("dsc") or "unknown error"
            raise ProviderError(
                f"eastmoney {kind} rc={rc}: {detail} "
                f"(params={json.dumps(dict(params), ensure_ascii=False)})"
            )
        return dict(payload)

    def _request_json(self, kind: str, params: Mapping[str, Any]) -> dict[str, Any]:
        request = dict(params)
        if self._transport is not None:
            self._acquire()
            payload = self._transport(kind, request)
            if not isinstance(payload, Mapping):
                raise ProviderError(f"eastmoney {kind} transport returned a non-object payload")
            return self._checked_payload(kind, request, payload)
        self.ensure_available()
        url = KLINE_URL if kind in {"kline", "index_kline"} else CLIST_URL

        def attempt() -> dict[str, Any]:
            self._acquire()
            try:
                response = httpx.get(
                    url,
                    params=request,
                    headers=REQUEST_HEADERS,
                    timeout=20.0,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                raise _RetryableRequestError(f"network error: {exc}") from exc
            if response.status_code == 429 or response.status_code >= 500:
                raise _RetryableRequestError(f"http {response.status_code} (throttled)")
            if response.status_code >= 400:
                raise ProviderError(f"eastmoney {kind} http {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise _RetryableRequestError(
                    f"non-JSON response (empty reply/anti-bot?): {response.text[:120]!r}"
                ) from exc
            if not isinstance(payload, dict):
                raise ProviderError(f"eastmoney {kind} returned a non-object payload")
            return self._checked_payload(kind, request, payload)

        policy = self.retry_policy or RetryPolicy(attempts=3, base_delay=0.5, max_delay=4.0)
        try:
            return retry_call(attempt, policy, retry_on=(_RetryableRequestError,))
        except _RetryableRequestError as exc:
            raise ProviderError(
                f"eastmoney {kind} request failed after {policy.attempts} attempts: {exc}"
            ) from exc

    @staticmethod
    def _kline_params(secid: str, start: int, end: int, fqt: int) -> dict[str, Any]:
        return {
            "secid": secid,
            "fields1": KLINE_FIELDS1,
            "fields2": KLINE_FIELDS2,
            "klt": 101,
            "fqt": fqt,
            "beg": str(start),
            "end": str(end),
        }

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        start_i, end_i = to_date_int(start), to_date_int(end)
        payload = self._request_json(
            "index_kline", self._kline_params(self.index_secid, start_i, end_i, 0)
        )
        frame = parse_kline_payload(payload, str(self.index_secid).split(".")[-1])
        if frame.empty:
            raise ProviderError(
                f"eastmoney index kline returned no trading days for {start_i}-{end_i}"
            )
        return TradingCalendar.from_dates(frame["date"].tolist()).slice(start_i, end_i)

    def fetch_security_master(self) -> pd.DataFrame:
        if self._master is not None:
            return self._master.copy()
        self.ensure_available()
        rows: list[dict[str, Any]] = []
        total = 0
        page = 1
        while page <= 500:
            payload = self._request_json(
                "clist",
                {
                    "ut": PUBLIC_UT,
                    "pn": page,
                    "pz": self.page_size,
                    "po": 0,
                    "np": 1,
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f12",
                    "fs": UNIVERSE_FS,
                    "fields": UNIVERSE_FIELDS,
                },
            )
            data = payload.get("data") or {}
            total = int(data.get("total") or total or 0)
            page_rows = universe_rows(payload)
            if not page_rows:
                break
            rows.extend(page_rows)
            if total and len(rows) >= total:
                break
            if self.limit is not None and not self.codes and len(rows) >= self.limit:
                break
            page += 1
        frame = normalize_eastmoney_universe({"data": {"total": total, "diff": rows}})
        if self.codes:
            frame = frame[frame["code"].isin(set(self.codes))]
        if self.limit is not None:
            frame = frame.head(self.limit)
        frame = frame.reset_index(drop=True)
        if frame.empty:
            raise ProviderError(
                f"eastmoney universe contains none of the requested codes (codes={self.codes})"
            )
        self._master = frame
        self._st_by_sec = {
            str(sec): "ST" in str(name).upper()
            for sec, name in zip(frame["sec_id"], frame["name"], strict=False)
        }
        return frame.copy()

    def _resolve_codes(self, codes: Iterable[str] | None) -> list[str]:
        if codes is not None:
            values = [normalize_code(value) for value in codes]
            if values:
                return values
        if self.codes:
            return list(self.codes)
        master = self.fetch_security_master()
        return [str(value) for value in master["code"].tolist()]

    def _parallel_map[T](self, codes: list[str], fn: Callable[[str], T]) -> list[T]:
        workers = min(self.max_workers, len(codes))
        if workers <= 1:
            return [fn(code) for code in codes]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, code) for code in codes]
            return [future.result() for future in futures]

    def _raw_kline(self, code: str, start: int, end: int, fqt: int) -> pd.DataFrame:
        payload = self._request_json(
            "kline", self._kline_params(secid_for_code(code), start, end, fqt)
        )
        return normalize_eastmoney_kline(payload, code)

    def _actions_for_code(self, code: str, start: int, end: int) -> pd.DataFrame:
        key = (normalize_code(code), int(start), int(end))
        cached = self._action_cache.get(key)
        if cached is not None:
            return cached
        raw = self._raw_kline(code, start, end, 0)
        if raw.empty:
            actions = empty_corporate_actions()
        else:
            _, actions = derive_adjustment(
                raw, self._raw_kline(code, start, end, 1), source="EASTMONEY_APPROX"
            )
        self._action_cache[key] = actions
        return actions

    def _bars_for_code(self, code: str, start: int, end: int) -> pd.DataFrame:
        raw = self._raw_kline(code, start, end, 0)
        if raw.empty:
            self._action_cache[(normalize_code(code), int(start), int(end))] = (
                empty_corporate_actions()
            )
            return empty_public_bars()
        factor, actions = derive_adjustment(
            raw, self._raw_kline(code, start, end, 1), source="EASTMONEY_APPROX"
        )
        self._action_cache[(normalize_code(code), int(start), int(end))] = actions
        sec_id = code_to_sec_id(code)[0]
        bars = build_canonical_bars(
            raw,
            factor,
            board=infer_board(code),
            st=self._st_by_sec.get(sec_id, False),
            source="EASTMONEY",
        )
        return bars[(bars["date"] >= start) & (bars["date"] <= end)].reset_index(drop=True)

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        start_i, end_i = to_date_int(start), to_date_int(end)
        code_list = self._resolve_codes(codes)
        frames = [
            frame
            for frame in self._parallel_map(
                code_list, lambda code: self._bars_for_code(code, start_i, end_i)
            )
            if not frame.empty
        ]
        if not frames:
            return empty_public_bars()
        combined = normalize_bars(pd.concat(frames, ignore_index=True))
        return combined[(combined["date"] >= start_i) & (combined["date"] <= end_i)].reset_index(
            drop=True
        )

    def fetch_corporate_actions(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("corporate_actions")
        start_i, end_i = to_date_int(start), to_date_int(end)
        code_list = self._resolve_codes(codes)
        frames = [
            frame
            for frame in self._parallel_map(
                code_list, lambda code: self._actions_for_code(code, start_i, end_i)
            )
            if not frame.empty
        ]
        if not frames:
            return empty_corporate_actions()
        actions = normalize_corporate_actions(pd.concat(frames, ignore_index=True))
        return actions[(actions["ex_date"] >= start_i) & (actions["ex_date"] <= end_i)].reset_index(
            drop=True
        )
