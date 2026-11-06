"""Read-only daily candles for a selected security; never change research data."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import numpy as np

from ..providers.eastmoney import KLINE_FIELDS1, KLINE_FIELDS2, KLINE_URL, normalize_eastmoney_kline
from ..providers.public_web import infer_board, parse_public_json, parse_sina_daily
from ..providers.sina import SINA_KLINE_URL
from .clock import market_phase
from .quotes import (
    EASTMONEY_REFERER,
    SINA_REFERER,
    USER_AGENT,
    QuoteHttp,
    QuoteSourceError,
    secid,
    sina_symbol,
)


class DailyHistory:
    """Bounded, short-lived display cache with the same fixture transport as quotes."""

    def __init__(self, http: QuoteHttp, clock: Callable[[], datetime]) -> None:
        self.http = http
        self.clock = clock
        self._cache: OrderedDict[tuple[str, int], tuple[datetime, dict[str, Any]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def bars(self, code: str, limit: int) -> dict[str, Any]:
        key = (code, limit)
        async with self._lock:
            now = self.clock()
            cached = self._cache.get(key)
            ttl = 60 if market_phase(now) in {"pre_open", "open", "lunch"} else 300
            if cached and (now - cached[0]).total_seconds() < ttl:
                self._cache.move_to_end(key)
                return cached[1]
            payload = await self._fetch(code, limit, now)
            self._cache[key] = (now, payload)
            self._cache.move_to_end(key)
            while len(self._cache) > 32:
                self._cache.popitem(last=False)
            return payload

    async def _fetch(self, code: str, limit: int, now: datetime) -> dict[str, Any]:
        count = min(2000, limit + 20)
        name = code
        try:
            url = (
                KLINE_URL
                + "?"
                + urlencode(
                    {
                        "secid": secid(code),
                        "klt": 101,
                        "fqt": 0,
                        "beg": 0,
                        "end": 20500101,
                        "lmt": count,
                        "fields1": KLINE_FIELDS1,
                        "fields2": KLINE_FIELDS2,
                    }
                )
            )
            raw = await self.http.get_json(
                url, headers={"User-Agent": USER_AGENT, "Referer": EASTMONEY_REFERER}
            )
            frame = normalize_eastmoney_kline(raw, code)
            if frame.empty:
                raise QuoteSourceError("eastmoney returned no daily candles")
            name = str((raw.get("data") or {}).get("name") or code)
            source = "eastmoney"
            note = "公开日线 · 不复权 · 仅用于行情展示, 不改变本地研究快照"
        except Exception as primary:
            try:
                url = (
                    SINA_KLINE_URL
                    + "?"
                    + urlencode(
                        {"symbol": sina_symbol(code), "scale": 240, "ma": "no", "datalen": count}
                    )
                )
                text = await self.http.get_text(
                    url, headers={"User-Agent": USER_AGENT, "Referer": SINA_REFERER}
                )
                frame = parse_sina_daily(parse_public_json(text), code)
                if frame.empty:
                    raise QuoteSourceError("sina returned no daily candles")
                source = "sina"
                note = "公开日线 · 不复权 · 新浪未提供成交额和换手率; 仅用于行情展示"
            except Exception as secondary:
                raise QuoteSourceError(
                    f"daily candles unavailable: eastmoney ({primary}); sina ({secondary})"
                ) from secondary
        valid = np.isfinite(frame[["open", "high", "low", "close"]].astype(float)).all(axis=1)
        valid &= frame["low"].astype(float) > 0
        valid &= frame["high"].astype(float) >= frame[["open", "close", "low"]].astype(float).max(
            axis=1
        )
        valid &= frame["low"].astype(float) <= frame[["open", "close"]].astype(float).min(axis=1)
        frame = frame.loc[valid].copy()
        if frame.empty:
            raise QuoteSourceError("daily source returned no valid candles")
        close = frame["close"].astype(float)
        ma5, ma20 = close.rolling(5).mean(), close.rolling(20).mean()
        frame = frame.tail(limit)
        positions = close.index.get_indexer(frame.index)
        dates = [str(int(day)) for day in frame["date"]]
        return {
            "code": code,
            "name": name,
            "board": infer_board(code),
            "dates": [f"{day[:4]}-{day[4:6]}-{day[6:]}" for day in dates],
            **{
                field: frame[field].astype(float).tolist()
                for field in ("open", "high", "low", "close", "volume")
            },
            "amount": frame["amount"].astype(float).tolist()
            if "amount" in frame
            else [None] * len(frame),
            "turnover": (frame["turnover"].astype(float) * 100).tolist()
            if "turnover" in frame
            else [None] * len(frame),
            "ma5": [float(value) if np.isfinite(value) else None for value in ma5.iloc[positions]],
            "ma20": [
                float(value) if np.isfinite(value) else None for value in ma20.iloc[positions]
            ],
            "limit_up": [],
            "limit_down": [],
            "suspended": [],
            "synthetic": False,
            "source": source,
            "as_of": now.isoformat(timespec="seconds"),
            "note": note,
        }
