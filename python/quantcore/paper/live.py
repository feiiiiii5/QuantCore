# ruff: noqa: RUF001 -- user-facing Chinese status messages use Chinese punctuation.
"""Quote-driven local paper accounts; public quotes never route real orders."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from ..backtest.config import CostModelConfig, RuleSetConfig
from ..calendar import to_date_int
from ..errors import ProviderError
from ..providers.public_web import code_to_sec_id, infer_board, normalize_code
from ..realtime.clock import SHANGHAI_TZ, now_shanghai
from .engine import PaperSessionEngine
from .errors import PaperValidationError
from .market import PaperMarketData
from .models import PaperOrder, PaperSession
from .rules import (
    canonical_buy_qty,
    participation_cap,
    participation_rate,
    price_limit_pct,
    round_buy_qty,
    round_to_tick,
)
from .util import _now

MAX_QUOTE_AGE = 15.0


def _timestamp(value: Any) -> datetime | None:
    text = str(value)
    if len(text) < 19 or ("T" not in text and " " not in text):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    return (
        moment.replace(tzinfo=SHANGHAI_TZ)
        if moment.tzinfo is None
        else moment.astimezone(SHANGHAI_TZ)
    )


class LivePaperMarket(PaperMarketData):
    """Security metadata needed by the shared paper settlement code, without a snapshot."""

    def __init__(self, session: PaperSession) -> None:
        self.sec_ids = []
        self.sec_index = {}
        self.meta = []
        for position in session.positions.values():
            self.security(position.code, position.name)
        for order in session.orders:
            self.security(order.code, order.name)

    def security(self, code: str, name: str = "") -> int:
        sec_id, exchange = code_to_sec_id(code)
        existing = self.sec_index.get(sec_id)
        if existing is not None:
            if name:
                self.meta[existing]["name"] = name
            return existing
        index = len(self.sec_ids)
        self.sec_ids.append(sec_id)
        self.sec_index[sec_id] = index
        self.meta.append(
            {
                "sec_id": sec_id,
                "code": code,
                "name": name or code,
                "exchange": exchange,
                "board": infer_board(code),
                "sec_type": "STOCK",
            }
        )
        return index


class LivePaperSessionEngine(PaperSessionEngine):
    """Match future fresh quote updates, using observed incremental volume as a budget."""

    market: LivePaperMarket

    def __init__(self, session: PaperSession) -> None:
        self.session = session
        self.market = LivePaperMarket(session)
        self.costs = CostModelConfig(**dict(session.config.get("costs") or {}))
        self.rules = RuleSetConfig(**dict(session.config.get("rules") or {}))
        self.participation = participation_rate(
            session.config.get("execution", {}).get("participation")
        )
        self.live = session.config.setdefault("live", {"observations": {}})
        self.live.setdefault("observations", {})

    @classmethod
    def create_live(
        cls,
        *,
        initial_cash: float = 1_000_000,
        name: str | None = None,
        now: datetime | None = None,
    ) -> PaperSession:
        if not math.isfinite(initial_cash) or initial_cash <= 0:
            raise PaperValidationError("initial_cash must be positive")
        day = to_date_int((now or now_shanghai()).date())
        return PaperSession(
            id=f"paper_{uuid.uuid4().hex[:12]}",
            name=name or "实时行情模拟账户",
            status="active",
            created_at=_now(),
            updated_at=_now(),
            snapshot={"source": "LIVE_QUOTES", "synthetic": False},
            start_date=day,
            end_date=29991231,
            current_date=day,
            initial_cash=initial_cash,
            cash=initial_cash,
            equity_curve=[{"date": day, "equity": initial_cash}],
            config={
                "mode": "live",
                "costs": CostModelConfig().model_dump(mode="json"),
                "rules": RuleSetConfig().model_dump(mode="json"),
                "execution": {"participation": 0.1},
                "live": {"observations": {}},
            },
        )

    def detail(self) -> dict[str, Any]:
        result = super().detail()
        result["live"] = dict(
            self.live.get("status")
            or {
                "state": "waiting",
                "as_of": None,
                "notice": "刷新有效行情后更新估值与虚拟成交。",
                "quotes": [],
            }
        )
        observations = self.live["observations"]
        for position in result["positions"]:
            position["quote_timestamp"] = observations.get(position["code"], {}).get("timestamp")
        return result

    def submit_order(
        self,
        *,
        code: str,
        side: str,
        qty: int,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> PaperOrder:
        self._require_active()
        try:
            code = normalize_code(code)
            sec = self.market.security(code)
        except (ValueError, ProviderError) as exc:
            raise PaperValidationError(f"invalid A-share security: {code}") from exc
        active = {p.code for p in self.session.positions.values()} | {
            o.code for o in self.session.orders if o.is_open
        }
        if code not in active and len(active) >= 50:
            raise PaperValidationError("a live paper account supports at most 50 securities")
        if side not in {"buy", "sell"} or order_type not in {"market", "limit"} or qty <= 0:
            raise PaperValidationError("invalid side, order type or quantity")
        if order_type == "limit":
            if limit_price is None or not math.isfinite(limit_price) or limit_price <= 0:
                raise PaperValidationError("limit orders require a positive limit_price")
            limit_price = round_to_tick(limit_price, self.rules.min_price_tick)
        elif limit_price is not None:
            raise PaperValidationError("limit_price is only valid for limit orders")
        if side == "buy":
            canonical_buy_qty(self.market.board(sec), qty, self.rules)
        else:
            position = self.session.positions.get(self.market.sec_ids[sec])
            if position is None or qty > position.available:
                raise PaperValidationError("T+1: insufficient shares available to sell today")
        order = PaperOrder(
            id=f"ord_{self.session.next_order_seq:06d}",
            date=self.session.current_date,
            code=code,
            sec_id=self.market.sec_ids[sec],
            name=self.market.name(sec),
            side=0 if side == "buy" else 1,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            created_at=_now(),
        )
        self.session.next_order_seq += 1
        self.session.orders.append(order)
        self.session.updated_at = _now()
        return order

    def step(self, *, days: int = 1, to_date: int | str | None = None) -> dict[str, Any]:
        raise PaperValidationError("live paper accounts use quote refresh, not historical steps")

    def reset(self) -> dict[str, Any]:
        fresh = self.create_live(initial_cash=self.session.initial_cash, name=self.session.name)
        self.session.cash = fresh.cash
        self.session.positions.clear()
        self.session.orders.clear()
        self.session.trades.clear()
        self.session.current_date = fresh.current_date
        self.session.start_date = fresh.start_date
        self.session.equity_curve = fresh.equity_curve
        self.session.next_order_seq = self.session.next_trade_seq = 1
        self.session.status = "active"
        self.session.config["live"] = {"observations": {}}
        self.live = self.session.config["live"]
        self.session.updated_at = _now()
        return self.detail()

    def refresh(
        self, payload: dict[str, Any], status: dict[str, Any], *, now: datetime
    ) -> dict[str, Any]:
        now = now.replace(tzinfo=SHANGHAI_TZ) if now.tzinfo is None else now.astimezone(SHANGHAI_TZ)
        day = to_date_int(now.date())
        phase = (status.get("market") or {}).get("phase")
        enabled = bool(status.get("enabled"))
        if phase == "open" and day > self.session.current_date:
            for position in self.session.positions.values():
                position.available = position.qty
            self.session.current_date = day
        fills: list[dict[str, Any]] = []
        quotes: list[dict[str, Any]] = []
        for quote in payload.get("quotes") or []:
            code = str(quote.get("code", ""))
            stamp = _timestamp(quote.get("timestamp"))
            price = float(quote.get("price") or 0)
            volume = float(quote.get("volume") or 0)
            age = (now - stamp).total_seconds() if stamp is not None else float("inf")
            reason = None
            if not enabled:
                reason = "实时行情未开启"
            elif quote.get("stale") or stamp is None or age < -2 or age > MAX_QUOTE_AGE:
                reason = "报价缺少有效时间戳或已陈旧"
            elif quote.get("suspended") or not math.isfinite(price) or price <= 0:
                reason = "停牌或无有效价格"
            elif not math.isfinite(volume) or volume < 0:
                reason = "无有效成交量"
            previous = self.live["observations"].get(code)
            previous_stamp = _timestamp(previous.get("timestamp")) if previous else None
            if (
                reason is None
                and stamp is not None
                and previous_stamp is not None
                and stamp <= previous_stamp
            ):
                reason = "等待下一条行情更新"
            quotes.append(
                {
                    "code": code,
                    "timestamp": quote.get("timestamp"),
                    "price": price,
                    "reason": reason,
                }
            )
            if reason is not None or stamp is None:
                continue
            sec = self.market.security(code, str(quote.get("name") or code))
            budget = 0
            source = quote.get("source")
            prior_volume = 0.0
            if (
                previous is not None
                and previous_stamp is not None
                and previous_stamp.date() == stamp.date()
            ):
                # Both normalized feeds count shares in the same security/day. Migrate
                # legacy per-source counters by their maximum, never the current source.
                prior_volume = max(
                    float(previous.get("volume") or 0),
                    max(
                        (
                            float(value or 0)
                            for value in (previous.get("source_volumes") or {}).values()
                        ),
                        default=0.0,
                    ),
                )
            # Advance even when a source switch or gap cannot fund a fill. Persist the
            # shared high-water mark so a lagging/corrected source cannot reuse volume.
            counter_volume = max(volume, prior_volume)
            if (
                previous is not None
                and previous_stamp is not None
                and previous.get("source") == source
                and previous_stamp.date() == stamp.date()
                and 0 < (stamp - previous_stamp).total_seconds() <= 30
            ):
                budget = participation_cap(max(0, volume - prior_volume), self.participation)
            self.live["observations"][code] = {
                "timestamp": stamp.isoformat(),
                "volume": counter_volume,
                "price": price,
                "source": source,
            }
            holding = self.session.positions.get(self.market.sec_ids[sec])
            if holding is not None:
                holding.last = price
                holding.name = self.market.name(sec)
            if phase != "open":
                continue
            bounds: dict[int, float | None] = {}
            previous_close = float(quote.get("prev_close") or 0)
            is_st = bool(quote.get("st")) or self.market.name(sec).strip().upper().startswith(
                ("ST", "*ST")
            )
            pct = price_limit_pct(self.market.board(sec), is_st, day, self.rules)
            for side, field in ((0, "limit_up"), (1, "limit_down")):
                value = float(quote.get(field) or 0)
                if not math.isfinite(value) or value <= 0:
                    value = (
                        round_to_tick(
                            previous_close * (1 + pct if side == 0 else 1 - pct),
                            self.rules.min_price_tick,
                        )
                        if math.isfinite(previous_close) and previous_close > 0
                        else 0
                    )
                bounds[side] = value if value > 0 else None
            for order in self.session.orders:
                created = _timestamp(order.created_at)
                if not order.is_open or order.code != code or created is None or stamp <= created:
                    continue
                if previous_stamp is None or previous_stamp < created:
                    order.reason = "等待下单后的成交量基线"
                    continue
                if budget <= 0:
                    order.reason = "等待新增成交量；首次刷新只建立行情基线"
                    continue
                if (
                    order.order_type == "limit"
                    and order.limit_price is not None
                    and (
                        (order.side == 0 and price > order.limit_price)
                        or (order.side == 1 and price < order.limit_price)
                    )
                ):
                    order.reason = "最新价格尚未触及限价"
                    continue
                bound = bounds[order.side]
                if bound is None:
                    order.reason = "缺少涨跌停边界与前收盘价，等待有效报价"
                    continue
                if (order.side == 0 and price >= bound) or (order.side == 1 and price <= bound):
                    order.reason = "涨跌停报价不假设能成交"
                    continue
                qty = min(order.remaining_qty, budget)
                if order.side == 0:
                    qty = round_buy_qty(self.market.board(sec), qty, self.rules)
                else:
                    holding = self.session.positions.get(order.sec_id)
                    qty = min(qty, holding.available if holding else 0)
                if qty <= 0:
                    continue
                order.name = self.market.name(sec)
                trade = self._settle(order, sec, price, qty)
                if trade is not None:
                    budget -= qty
                    order.reason = None
                    fills.append(trade.to_dict())
        notice = "使用新鲜报价与新增成交量模拟；不模拟盘口排队、公司行为或税费差异。"
        if not enabled:
            notice = "实时行情未开启；启用行情后刷新，当前不会模拟成交。"
        elif phase != "open":
            notice = "当前不在连续交易时段，委托保留等待有效行情。"
        self.live["status"] = {
            "state": "open" if enabled and phase == "open" else "waiting",
            "as_of": now.isoformat(),
            "notice": notice,
            "quotes": quotes,
        }
        point = {"date": self.session.current_date, "equity": self.session.equity()}
        if self.session.equity_curve and self.session.equity_curve[-1]["date"] == point["date"]:
            self.session.equity_curve[-1] = point
        else:
            self.session.equity_curve.append(point)
        self.session.updated_at = _now()
        result = self.detail()
        result["fills"] = fills
        return result
