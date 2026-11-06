"""Sina Finance public quote provider: full A-share universe + daily bars.

Research and simulation only: no broker connection or order routing. The adapter reads
Sina's public quote endpoints (no token) and is not an official API: personal research
use, self-imposed rate limits, fetched data must not be redistributed
(see docs/DATA-LICENSES.md).

Endpoints
* universe: vip.stock.finance.sina.com.cn Market_Center.getHQNodeData, node=hs_a,
  paginated (80 per page, about 70 pages for the full A-share market).
* daily bars: money.finance.sina.com.cn CN_MarketData.getKLineData, scale=240 (daily).
  The endpoint returns the latest datalen bars (no start/end parameters), so the provider
  sizes datalen from the requested start and filters to [start, end]; history is capped
  at about 2000 bars (roughly 2018-07 onward) by upstream.
* forward-adjusted closes (corporate-action derivation): Tencent fqkline qfq, one
  request per security, only when derive_actions=True.

Units (verified against recorded live samples)
* Sina kline volume is in shares (股) and used as-is for canonical volume.
* Sina kline has no amount field: amount is ESTIMATED as volume x mean(open, high, low,
  close) and only usable for magnitude / capacity-style screening, not as the real traded
  value (TODO(verify), see docs/data-dictionary.md).
* Tencent qfq volume is in lots but only the adjusted close is consumed.

Corporate actions are approximate: the ratio of Tencent qfq close to Sina raw close gives
a factor series; a jump above the rounding-noise bound marks an ex-date and the jump size
estimates cash_per_share (or split_ratio for large jumps). Derived rows are labelled
SINA_APPROX and must be re-verified before a research conclusion relies on them.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, ClassVar

import httpx
import pandas as pd

from ..calendar import TradingCalendar, date_str, from_date_int, to_date_int
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
    normalize_sina_universe,
    parse_public_json,
    parse_sina_daily,
    parse_tencent_qfq,
    sina_symbol,
)

SINA_UNIVERSE_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)
SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
)
TENCENT_QFQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
INDEX_SYMBOL = "sh000001"
_SHANGHAI_TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")


def _today_shanghai() -> date:
    """Today in Asia/Shanghai (the data vendor's trading-day timezone)."""
    return dt.datetime.now(tz=_SHANGHAI_TZ).date()


MAX_HISTORY_BARS = 2000
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "application/json,text/plain,*/*",
}


class _RetryableRequestError(ProviderError):
    """Transient transport failure (timeout/throttle/empty reply) worth retrying."""


class SinaProvider(DataProvider):
    """Full A-share universe + daily bars from Sina's public quote endpoints."""

    name: ClassVar[str] = "sina"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        financials=False, corporate_actions=True, realtime=False
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=200,
        window_seconds=60.0,
        min_interval_seconds=0.25,
        tier="public-web",
        notes=(
            "Unofficial public Sina/Tencent web endpoints; no token. Self-imposed limit: "
            "<=2 concurrent requests, >=0.25s between request starts, 2 retries with "
            "exponential backoff. Full market (~5500 stocks): universe ~70 pages plus one "
            "kline request per stock (~30-45 min at this pacing) and one optional Tencent "
            "qfq request per stock when derive_actions=True (roughly double). Use "
            "--limit/--codes for samples. Fetched data must not be redistributed."
        ),
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission(
        requires_credentials=False,
        license_note=(
            "Sina Finance / Tencent public quote endpoints (unofficial, no service-level "
            "guarantee); personal research use only, rate-limited, fetched data must not be "
            "redistributed. Network access must be enabled explicitly (QC_ALLOW_NETWORK=1)."
        ),
    )

    def __init__(
        self,
        *,
        transport: Callable[[str, Mapping[str, Any]], Any] | None = None,
        codes: Iterable[str] | None = None,
        limit: int | None = None,
        max_workers: int = 2,
        page_size: int = 80,
        derive_actions: bool = True,
        index_symbol: str = INDEX_SYMBOL,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
        allow_network: bool = False,
    ) -> None:
        super().__init__(limiter=limiter, retry=retry, allow_network=allow_network)
        self._transport = transport
        self.codes = [normalize_code(value) for value in codes] if codes else None
        self.limit = int(limit) if limit is not None else None
        # The declared quota promises <=2 concurrent requests; never exceed it.
        self.max_workers = max(1, min(2, int(max_workers)))
        self.page_size = max(1, int(page_size))
        self.derive_actions = bool(derive_actions)
        self.index_symbol = index_symbol
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
            "sina network access is disabled; set QC_ALLOW_NETWORK=1 or pass "
            "allow_network=True (public endpoints, no token; personal research use only)"
        )

    def _acquire(self) -> None:
        with self._limiter_lock:
            self.limiter.acquire()
            self._request_count += 1

    def _get_text(self, kind: str, params: Mapping[str, Any], url: str) -> str:
        request = dict(params)
        if self._transport is not None:
            self._acquire()
            text = self._transport(kind, request)
            if not isinstance(text, str):
                raise ProviderError(
                    f"sina {kind} transport returned {type(text).__name__}, expected text"
                )
            return text
        self.ensure_available()

        def attempt() -> str:
            self._acquire()
            try:
                response = httpx.get(
                    url,
                    params=request,
                    headers=REQUEST_HEADERS,
                    timeout=25.0,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                raise _RetryableRequestError(f"network error: {exc}") from exc
            if response.status_code == 429 or response.status_code >= 500:
                raise _RetryableRequestError(f"http {response.status_code} (throttled)")
            if response.status_code >= 400:
                raise ProviderError(
                    f"sina {kind} http {response.status_code}: {response.text[:160]}"
                )
            if not response.text.strip():
                raise _RetryableRequestError("empty response body")
            return response.text

        policy = self.retry_policy or RetryPolicy(attempts=3, base_delay=0.5, max_delay=4.0)
        try:
            return retry_call(attempt, policy, retry_on=(_RetryableRequestError,))
        except _RetryableRequestError as exc:
            raise ProviderError(
                f"sina {kind} request failed after {policy.attempts} attempts: {exc}"
            ) from exc

    @staticmethod
    def _history_bars(start: int) -> int:
        """datalen covering [start, today] for the latest-N kline endpoint."""
        span_days = max(0, (_today_shanghai() - from_date_int(start)).days)
        estimate = int(span_days * 5 / 7) + 40
        return max(40, min(MAX_HISTORY_BARS, estimate))

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        start_i, end_i = to_date_int(start), to_date_int(end)
        text = self._get_text(
            "index_kline",
            {
                "symbol": self.index_symbol,
                "scale": 240,
                "ma": "no",
                "datalen": self._history_bars(start_i),
            },
            SINA_KLINE_URL,
        )
        frame = parse_sina_daily(parse_public_json(text), "000001")
        if frame.empty:
            raise ProviderError(
                f"sina index kline returned no trading days for {self.index_symbol}"
            )
        calendar = TradingCalendar.from_dates(frame["date"].tolist())
        if start_i < calendar.dates[0] - 10:
            raise ProviderError(
                f"sina history is limited to about {MAX_HISTORY_BARS} bars; requested start "
                f"{start_i} is older than the earliest available date {calendar.dates[0]}"
            )
        return calendar.slice(start_i, end_i)

    def fetch_security_master(self) -> pd.DataFrame:
        if self._master is not None:
            return self._master.copy()
        self.ensure_available()
        rows: list[dict[str, Any]] = []
        page = 1
        while page <= 500:
            text = self._get_text(
                "universe",
                {
                    "page": page,
                    "num": self.page_size,
                    "sort": "symbol",
                    "asc": 1,
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "page",
                },
                SINA_UNIVERSE_URL,
            )
            payload = parse_public_json(text)
            if payload is None:
                break
            if not isinstance(payload, list):
                raise ProviderError("sina universe response is not a list")
            if not payload:
                break
            rows.extend(dict(item) for item in payload if isinstance(item, Mapping))
            if self.codes and set(self.codes) <= {str(item.get("code")) for item in rows}:
                break
            if self.limit is not None and not self.codes and len(rows) >= self.limit:
                break
            page += 1
        frame = normalize_sina_universe(rows)
        if self.codes:
            frame = frame[frame["code"].isin(set(self.codes))]
        if self.limit is not None:
            frame = frame.head(self.limit)
        frame = frame.reset_index(drop=True)
        if frame.empty:
            raise ProviderError(
                "sina universe contains none of the requested codes "
                f"(codes={self.codes}, limit={self.limit})"
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

    def _raw_daily(self, code: str, start: int, end: int) -> pd.DataFrame:
        text = self._get_text(
            "kline",
            {
                "symbol": sina_symbol(code),
                "scale": 240,
                "ma": "no",
                "datalen": self._history_bars(start),
            },
            SINA_KLINE_URL,
        )
        return parse_sina_daily(parse_public_json(text), code)

    def _qfq_closes(self, code: str, start: int, end: int) -> pd.DataFrame:
        symbol = sina_symbol(code)
        today = to_date_int(_today_shanghai())
        last = min(int(end), today)
        count = min(MAX_HISTORY_BARS, self._history_bars(start) + 5)
        text = self._get_text(
            "qfq",
            {"param": f"{symbol},day,{date_str(start)},{date_str(last)},{count},qfq"},
            TENCENT_QFQ_URL,
        )
        return parse_tencent_qfq(parse_public_json(text), symbol)

    def _qfq_for_raw(self, code: str, raw: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
        """QFQ series covering the full raw window so pre_close has the prior factor."""
        qfq_start = int(raw["date"].min()) if not raw.empty else int(start)
        return self._qfq_closes(code, min(qfq_start, int(start)), end)

    def _actions_for_code(self, code: str, start: int, end: int) -> pd.DataFrame:
        key = (normalize_code(code), int(start), int(end))
        cached = self._action_cache.get(key)
        if cached is not None:
            return cached
        if not self.derive_actions:
            actions = empty_corporate_actions()
        else:
            raw = self._raw_daily(code, start, end)
            if raw.empty:
                actions = empty_corporate_actions()
            else:
                _, _, actions = self._verified_adjustment(code, raw, start, end)
        self._action_cache[key] = actions
        return actions

    def _verified_adjustment(
        self, code: str, raw: pd.DataFrame, start: int, end: int
    ) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
        qfq = self._qfq_for_raw(code, raw, start, end)
        requested = raw[(raw["date"] >= start) & (raw["date"] <= end)]
        missing = sorted(set(requested["date"]) - set(qfq["date"]))
        if missing:
            first = int(qfq["date"].min()) if not qfq.empty else "none"
            raise ProviderError(
                f"qfq coverage starts {first}; requested date {missing[0]} is not covered"
            )
        if qfq.empty or requested.empty:
            raw = requested
        else:
            raw = raw[(raw["date"] >= int(qfq["date"].min())) & (raw["date"] <= end)].copy()
        factor, actions = derive_adjustment(raw, qfq, source="SINA_APPROX")
        return raw, factor, actions

    def _bars_for_code(self, code: str, start: int, end: int) -> pd.DataFrame:
        raw = self._raw_daily(code, start, end)
        if raw.empty:
            self._action_cache[(normalize_code(code), int(start), int(end))] = (
                empty_corporate_actions()
            )
            return empty_public_bars()
        if self.derive_actions:
            raw, factor, actions = self._verified_adjustment(code, raw, start, end)
        else:
            factor = pd.Series(1.0, index=raw.index, dtype="float64")
            actions = empty_corporate_actions()
        self._action_cache[(normalize_code(code), int(start), int(end))] = actions
        sec_id = code_to_sec_id(code)[0]
        bars = build_canonical_bars(
            raw,
            factor,
            board=infer_board(code),
            st=self._st_by_sec.get(sec_id, False),
            source="SINA",
            actions=actions,
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
