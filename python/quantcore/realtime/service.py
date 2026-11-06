"""Live quote service: bounded polling, in-memory cache and honest offline mode.

The service only talks to the network when explicitly enabled (QC_ALLOW_NETWORK=1).
When disabled it still answers status/quote requests with an explicit "off" state so the
UI can render an offline snapshot instead of failing.  Nothing here mutates the warehouse
or places orders: quotes are display data only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clock import SHANGHAI_TZ, market_clock, market_phase, now_shanghai
from .history import DailyHistory
from .quotes import (
    INDEX_SPECS,
    HttpxQuoteHttp,
    Quote,
    QuoteHttp,
    QuoteSourceError,
    fetch_eastmoney_quotes,
    fetch_sina_quotes,
    normalize_code,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3.0
MIN_INTERVAL_SECONDS = 2.0
MAX_INTERVAL_SECONDS = 30.0
OFFLINE_NOTICE = (
    "实时行情未开启: 设置 QC_ALLOW_NETWORK=1 后重启 qc serve; 默认完全离线, 仅使用本地快照"
)
OFFLINE_STATE_NOTICE = "离线模式: 行情来自本地快照, 非实时"

LiveStatusSnapshot = dict[str, Any]


@dataclass(frozen=True)
class LiveConfig:
    """Runtime configuration for the live quote service."""

    enabled: bool = False
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    max_codes: int = 50


def config_from_env(env: dict[str, str] | None = None) -> LiveConfig:
    """Read QC_ALLOW_NETWORK / QC_LIVE_INTERVAL (defaults: off, 3s)."""
    values = os.environ if env is None else env
    enabled = str(values.get("QC_ALLOW_NETWORK", "")).strip() == "1"
    try:
        interval = float(values.get("QC_LIVE_INTERVAL", DEFAULT_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_SECONDS
    interval = min(max(interval, MIN_INTERVAL_SECONDS), MAX_INTERVAL_SECONDS)
    return LiveConfig(enabled=enabled, interval_seconds=interval)


class LiveQuoteService:
    """Polls a small symbol set while the market is open; never writes to disk."""

    def __init__(
        self,
        *,
        state: Any = None,
        http: QuoteHttp | None = None,
        config: LiveConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.state = state
        self.http = http or HttpxQuoteHttp()
        self.config = config or config_from_env()
        self.clock = clock or now_shanghai
        self.history = DailyHistory(self.http, self.clock)
        self._cache: dict[str, Quote] = {}
        self._received: dict[str, datetime] = {}
        self._as_of: datetime | None = None
        self._source = "none"
        self._latency_ms: float | None = None
        self._error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._index_targets = [f"idx:{item['code']}" for item in INDEX_SPECS]

    # -- lifecycle -----------------------------------------------------
    async def start(self) -> None:
        if not self.config.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="qc-live-quotes")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _run(self) -> None:
        while not self._stop.is_set():
            phase = "closed"
            try:
                phase = market_phase(self.clock())
                if phase in {"pre_open", "open", "lunch"} or self._as_of is None:
                    await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # surfaced through status instead of crashing
                self._error = f"{type(exc).__name__}: {exc}"[:300]
                LOGGER.warning("live refresh failed: %s", exc)
            delay = self.config.interval_seconds
            if phase in {"closed", "holiday"}:
                # Polling without network during the closed/holiday phase: slow down from
                # the 2-3s intraday cadence (the status still updates last_trade_date).
                delay = max(delay, 15.0)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except TimeoutError:
                continue

    # -- watchlist -----------------------------------------------------
    def watchlist(self) -> list[str]:
        if self.state is None:
            return []
        try:
            raw = self.state.get_meta("watchlist", []) or []
        except Exception:  # pragma: no cover - defensive
            return []
        codes: list[str] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                code = normalize_code(str(item))
            except ValueError:
                continue
            if code not in codes:
                codes.append(code)
        return codes[: self.config.max_codes]

    # -- fetching ------------------------------------------------------
    async def _fetch_group(
        self, stocks: list[str], indexes: list[str], *, now: datetime, source: str
    ) -> list[Quote]:
        fetcher = fetch_eastmoney_quotes if source == "eastmoney" else fetch_sina_quotes
        quotes: list[Quote] = []
        errors: list[str] = []
        for targets, as_index in ((indexes, True), (stocks, False)):
            if not targets:
                continue
            try:
                quotes.extend(await fetcher(self.http, targets, now=now, as_index=as_index))
            except Exception as exc:
                errors.append(str(exc))
        if errors and not quotes:
            raise QuoteSourceError("; ".join(errors))
        return quotes

    async def _fetch(self, stocks: list[str], indexes: list[str]) -> None:
        now = self.clock()
        started = time.perf_counter()
        requested = set(stocks + indexes)
        primary_error: Exception | None = None
        try:
            quotes = await self._fetch_group(stocks, indexes, now=now, source="eastmoney")
        except Exception as exc:
            primary_error = exc
            quotes = []
        found = {quote.code: quote for quote in quotes if quote.code in requested}
        missing = requested - found.keys()
        for code, quote in found.items():
            age = self._source_age(quote, now)
            if age is None or (market_phase(now) == "open" and age > self._freshness_seconds()):
                missing.add(code)
        if missing:
            LOGGER.info("live primary source omitted %s, trying sina: %s", missing, primary_error)
            try:
                fallback = await self._fetch_group(
                    [code for code in stocks if code in missing],
                    [code for code in indexes if code in missing],
                    now=now,
                    source="sina",
                )
                found.update({quote.code: quote for quote in fallback if quote.code in missing})
            except Exception as secondary:
                if not found:
                    raise QuoteSourceError(
                        f"eastmoney failed ({primary_error}); sina failed ({secondary})"
                    ) from secondary
        if not found:
            raise QuoteSourceError("quote sources returned no requested quotes")
        self._latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
        self._source = next(iter(found.values())).source
        self._as_of = now
        self._error = None
        for quote in found.values():
            self._cache[quote.code] = quote
            self._received[quote.code] = now

    def _stale(self, code: str) -> bool:
        received = self._received.get(code)
        now = self.clock()
        source_age = self._source_age(self._cache.get(code), now)
        return (
            received is None
            or source_age is None
            or max((now - received).total_seconds(), source_age) > self._freshness_seconds()
        )

    def _freshness_seconds(self) -> float:
        return max(10.0, self.config.interval_seconds * 4)

    @staticmethod
    def _source_age(quote: Quote | None, now: datetime) -> float | None:
        if quote is None or not quote.timestamp:
            return None
        try:
            stamp = datetime.fromisoformat(quote.timestamp)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=SHANGHAI_TZ)
            age = (now - stamp).total_seconds()
            return age if age >= -5 else None
        except ValueError:
            return None

    async def refresh(self, codes: list[str] | None = None) -> None:
        """Fetch the requested stock codes (plus indices/watchlist by default)."""
        if not self.config.enabled:
            return
        stocks: list[str] = []
        for code in list(codes or []) + self.watchlist():
            try:
                normalized = normalize_code(code)
            except ValueError:
                continue
            if normalized not in stocks:
                stocks.append(normalized)
        stocks = stocks[: self.config.max_codes]
        indexes = list(self._index_targets)
        if not stocks and not indexes:
            return
        async with self._lock:
            try:
                await self._fetch(stocks, indexes)
            except QuoteSourceError as exc:
                self._error = str(exc)
                raise

    # -- read views ----------------------------------------------------
    def _market(self) -> dict[str, Any]:
        return market_clock(self.clock())

    def _state(self) -> str:
        if not self.config.enabled:
            return "off"
        phase = self._market()["phase"]
        if phase in {"closed", "holiday"}:
            return "closed"
        if self._error:
            return "error"
        if self._as_of is None:
            return "connecting"
        if not any(not self._stale(code) for code in self._cache):
            return "idle"
        age = (self.clock() - self._as_of).total_seconds()
        if age > max(10.0, self.config.interval_seconds * 4):
            return "idle"
        return "live"

    def _notice(self, state: str) -> str:
        if state == "off":
            return OFFLINE_NOTICE
        if state == "closed":
            return "已收盘: 展示最近收盘数据(如有)"
        if state == "error":
            return f"行情源异常: {self._error or 'unknown'}"
        if state == "connecting":
            return "正在连接行情源..."
        if state == "idle":
            return "行情数据暂停更新(网络或行情源异常)"
        return OFFLINE_STATE_NOTICE if self._as_of is None else "实时行情"

    async def status(self) -> LiveStatusSnapshot:
        state = self._state()
        stamps = [quote.timestamp for quote in self._cache.values() if quote.timestamp]
        return {
            "enabled": self.config.enabled,
            "source": self._source,
            "state": state,
            "market": self._market(),
            "as_of": max(stamps) if stamps else None,
            "latency_ms": self._latency_ms,
            "subscribed": len(self._cache),
            "error": self._error,
            "notice": self._notice(state),
        }

    def _payload(self, quotes: list[Quote]) -> LiveStatusSnapshot:
        stamps = [quote.timestamp for quote in quotes if quote.timestamp]
        stale = not quotes or any(self._stale(quote.code) for quote in quotes)
        display: list[dict[str, Any]] = []
        for quote in quotes:
            item = quote.to_dict()
            item["stale"] = self._stale(quote.code)
            received_at = self._received.get(quote.code)
            item["received_at"] = (
                None if received_at is None else received_at.isoformat(timespec="seconds")
            )
            if item["code"].startswith("idx:"):
                item["code"] = item["code"][4:]
            display.append(item)
        return {
            "as_of": min(stamps) if stamps else None,
            "source": quotes[0].source if quotes else "none",
            "stale": stale,
            "quotes": display,
        }

    async def _ensure_cached(self, codes: list[str]) -> None:
        if not self.config.enabled:
            return
        missing = [code for code in codes if code not in self._cache]
        phase = self._market()["phase"]
        stale = any(self._stale(code) for code in codes)
        if not missing and not (stale and phase in {"pre_open", "open", "lunch"}):
            return
        try:
            # Always refresh the requested codes: refresh() merges them with the watchlist,
            # so a stale non-watchlist quote must not fall back to a watchlist-only refresh.
            await self.refresh(codes)
        except QuoteSourceError:
            return  # status carries the error; keep serving whatever is cached

    async def _ensure_indices(self) -> None:
        if not self.config.enabled:
            return
        missing = [target for target in self._index_targets if target not in self._cache]
        phase = self._market()["phase"]
        stale = any(self._stale(code) for code in self._index_targets)
        if not missing and not (stale and phase in {"pre_open", "open", "lunch"}):
            return
        try:
            await self.refresh(None)
        except QuoteSourceError:
            return

    async def indices(self) -> LiveStatusSnapshot:
        await self._ensure_indices()
        return self._payload(
            [self._cache[target] for target in self._index_targets if target in self._cache]
        )

    async def quotes(self, codes: list[str] | None = None) -> LiveStatusSnapshot:
        requested = list(codes) if codes else self.watchlist()
        normalized: list[str] = []
        for code in requested:
            try:
                code6 = normalize_code(code)
            except ValueError:
                continue
            if code6 not in normalized:
                normalized.append(code6)
        normalized = normalized[: self.config.max_codes]
        await self._ensure_cached(normalized)
        return self._payload([self._cache[code] for code in normalized if code in self._cache])

    async def websocket_payload(self, codes: list[str] | None = None) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "status": await self.status(),
            "indices": await self.indices(),
            "quotes": await self.quotes(codes),
        }

    async def bars(self, code: str, limit: int = 600) -> dict[str, Any]:
        if not self.config.enabled:
            raise QuoteSourceError(OFFLINE_NOTICE)
        return await self.history.bars(normalize_code(code), limit)


__all__ = [
    "OFFLINE_NOTICE",
    "LiveConfig",
    "LiveQuoteService",
    "LiveStatusSnapshot",
    "config_from_env",
]
