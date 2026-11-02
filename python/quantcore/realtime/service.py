"""Live quote service: bounded polling, in-memory cache and honest offline mode.

The service only talks to the network when explicitly enabled (QC_ALLOW_NETWORK=1).
When disabled it still answers status/quote requests with an explicit "off" state so the
UI can render an offline snapshot instead of failing.  Nothing here mutates the warehouse
or places orders: quotes are display data only.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clock import market_clock, market_phase, now_shanghai
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
        self._cache: dict[str, Quote] = {}
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
            try:
                phase = market_phase(self.clock())
                if phase in {"pre_open", "open", "lunch"} or self._as_of is None:
                    await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # surfaced through status instead of crashing
                self._error = f"{type(exc).__name__}: {exc}"[:300]
            delay = self.config.interval_seconds
            if self._as_of is None and phase in {"closed", "holiday"}:
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
        if indexes:
            quotes.extend(await fetcher(self.http, indexes, now=now, as_index=True))
        if stocks:
            quotes.extend(await fetcher(self.http, stocks, now=now))
        return quotes

    async def _fetch(self, stocks: list[str], indexes: list[str]) -> None:
        now = self.clock()
        started = time.perf_counter()
        try:
            quotes = await self._fetch_group(stocks, indexes, now=now, source="eastmoney")
            source = "eastmoney"
            if not quotes:
                raise QuoteSourceError("eastmoney returned no quotes")
        except Exception as primary:  # fallback source
            try:
                quotes = await self._fetch_group(stocks, indexes, now=now, source="sina")
                source = "sina"
            except Exception as secondary:  # report both sources in the error
                raise QuoteSourceError(
                    f"eastmoney failed ({primary}); sina failed ({secondary})"
                ) from secondary
            if not quotes:
                raise QuoteSourceError("sina returned no quotes") from primary
        self._latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
        self._source = source
        self._as_of = now
        self._error = None
        for quote in quotes:
            self._cache[quote.code] = quote

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
        if self._error and self._as_of is None:
            return "error"
        if self._as_of is None:
            return "connecting"
        age = (self.clock() - self._as_of).total_seconds()
        if age > max(10.0, self.config.interval_seconds * 4):
            return "idle"
        return "live"

    def _notice(self, state: str) -> str:
        if state == "off":
            return OFFLINE_NOTICE
        if state == "holiday":
            return "今日休市: 展示最近交易日数据"
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
        return {
            "enabled": self.config.enabled,
            "source": self._source,
            "state": state,
            "market": self._market(),
            "as_of": None if self._as_of is None else self._as_of.isoformat(timespec="seconds"),
            "latency_ms": self._latency_ms,
            "subscribed": len(self._cache),
            "error": self._error,
            "notice": self._notice(state),
        }

    def _payload(self, quotes: list[Quote]) -> LiveStatusSnapshot:
        now = self.clock()
        stale = True
        if self._as_of is not None:
            age = (now - self._as_of).total_seconds()
            stale = age > max(10.0, self.config.interval_seconds * 4)
        display: list[dict[str, Any]] = []
        for quote in quotes:
            item = quote.to_dict()
            if item["code"].startswith("idx:"):
                item["code"] = item["code"][4:]
            display.append(item)
        return {
            "as_of": None if self._as_of is None else self._as_of.isoformat(timespec="seconds"),
            "source": self._source,
            "stale": stale,
            "quotes": display,
        }

    async def _ensure_cached(self, codes: list[str]) -> None:
        if not self.config.enabled:
            return
        missing = [code for code in codes if code not in self._cache]
        phase = self._market()["phase"]
        stale = self._as_of is None or (
            (self.clock() - self._as_of).total_seconds()
            > max(10.0, self.config.interval_seconds * 4)
        )
        if not missing and not (stale and phase in {"pre_open", "open", "lunch"}):
            return
        try:
            await self.refresh(codes if missing else None)
        except QuoteSourceError:
            return  # status carries the error; keep serving whatever is cached

    async def _ensure_indices(self) -> None:
        if not self.config.enabled:
            return
        missing = [target for target in self._index_targets if target not in self._cache]
        phase = self._market()["phase"]
        stale = self._as_of is None or (
            (self.clock() - self._as_of).total_seconds()
            > max(10.0, self.config.interval_seconds * 4)
        )
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


__all__ = [
    "OFFLINE_NOTICE",
    "LiveConfig",
    "LiveQuoteService",
    "LiveStatusSnapshot",
    "config_from_env",
]
