"""Local paper-trading engine: simulated A-share orders against one immutable snapshot.

Only research simulation: no broker gateway, no network calls and no real order routing.
Sessions are advanced one trading day at a time: pending orders fill at the next open
(market orders) or when the day's range touches a limit price, then positions are marked
at the close.  Board lots, T+1, price limits, suspensions and the default backtest fee
model are reused from :mod:`quantcore.backtest.config`.
"""

from __future__ import annotations

import bisect
import uuid
from typing import Any

import numpy as np

from ..backtest.config import CostModelConfig, RuleSetConfig
from ..calendar import to_date_int
from .errors import (
    PaperConflictError,
    PaperNotFoundError,
    PaperValidationError,
)
from .market import PaperMarketData
from .models import PaperOrder, PaperPosition, PaperSession, PaperTrade
from .rules import (
    DEFAULT_PARTICIPATION,
    canonical_buy_qty,
    fee_breakdown,
    is_shanghai,
    participation_cap,
    participation_rate,
    price_limit_pct,
    round_buy_qty,
    round_to_tick,
)
from .util import _clip_index, _date_text, _now


class PaperSessionEngine:
    """Mutating operations for one :class:`PaperSession` (caller persists the session)."""

    def __init__(self, market: PaperMarketData, session: PaperSession) -> None:
        self.market = market
        self.session = session
        self.costs = CostModelConfig(**dict(session.config.get("costs") or {}))
        self.rules = RuleSetConfig(**dict(session.config.get("rules") or {}))
        execution = dict(session.config.get("execution") or {})
        self.participation = participation_rate(execution.get("participation"))
        try:
            self.start_idx = market.date_index[int(session.start_date)]
            self.end_idx = market.date_index[int(session.end_date)]
            self.cur_idx = market.date_index[int(session.current_date)]
        except KeyError as exc:  # pragma: no cover - corrupt/hand-edited session
            raise PaperConflictError(
                f"session dates are not on the snapshot calendar ({exc})"
            ) from exc
        self._rules = self.rules

    # -- construction ------------------------------------------------------
    @classmethod
    def create(
        cls,
        market: PaperMarketData,
        *,
        snapshot: dict[str, Any],
        initial_cash: float = 1_000_000.0,
        start: int | str | None = None,
        end: int | str | None = None,
        name: str | None = None,
    ) -> PaperSession:
        if not float(initial_cash) > 0:
            raise PaperValidationError("initial_cash must be positive")
        dates = market.dates
        start_idx = _clip_index(dates, start, 0, rounding="up")
        end_idx = _clip_index(dates, end, len(dates) - 1, rounding="down")
        if start_idx > end_idx:
            raise PaperValidationError("start date must not be after end date")
        costs = CostModelConfig()
        rules = RuleSetConfig()
        config: dict[str, Any] = {
            "costs": costs.model_dump(mode="json"),
            "rules": rules.model_dump(mode="json"),
            "execution": {"participation": DEFAULT_PARTICIPATION},
        }
        session = PaperSession(
            id=f"paper_{uuid.uuid4().hex[:12]}",
            name=(str(name).strip() if name else f"模拟交易 {_date_text(dates[start_idx])}"),
            status="active",
            created_at=_now(),
            updated_at=_now(),
            snapshot=dict(snapshot),
            start_date=int(dates[start_idx]),
            end_date=int(dates[end_idx]),
            current_date=int(dates[start_idx]),
            initial_cash=float(initial_cash),
            cash=float(initial_cash),
            equity_curve=[{"date": int(dates[start_idx]), "equity": round(float(initial_cash), 4)}],
            config=config,
        )
        return session

    # -- read views --------------------------------------------------------
    def detail(self) -> dict[str, Any]:
        positions = [
            position.to_dict()
            for position in sorted(self.session.positions.values(), key=lambda item: item.code)
        ]
        return {
            "session": self.session.session_view(),
            "snapshot": dict(self.session.snapshot),
            "account": self.session.account_view(),
            "positions": positions,
            "orders": [order.to_dict() for order in self.session.orders],
            "trades": [trade.to_dict() for trade in self.session.trades],
            "equity_curve": list(self.session.equity_curve),
        }

    # -- order lifecycle ---------------------------------------------------
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
        if self.cur_idx >= self.end_idx:
            raise PaperValidationError("session is at its end date; reset it before trading")
        sec = self._resolve_sec(code)
        side_int = {"buy": 0, "sell": 1}.get(str(side).lower())
        if side_int is None:
            raise PaperValidationError("side must be 'buy' or 'sell'")
        order_type = str(order_type or "market").lower()
        if order_type not in {"market", "limit"}:
            raise PaperValidationError("order_type must be 'market' or 'limit'")
        if int(qty) <= 0:
            raise PaperValidationError("qty must be positive")
        limit: float | None
        if order_type == "limit":
            if limit_price is None:
                raise PaperValidationError("limit orders require limit_price")
            limit = round_to_tick(float(limit_price), self.rules.min_price_tick)
            if limit <= 0:
                raise PaperValidationError("limit_price must be positive")
        else:
            if limit_price is not None:
                raise PaperValidationError("limit_price is only valid for limit orders")
            limit = None

        if side_int == 0:
            canonical_buy_qty(
                self.market.board(sec), int(qty), self.rules, self.market.sec_type(sec)
            )
        else:
            held = self.session.positions.get(self.market.sec_ids[sec])
            if held is None or held.qty <= 0:
                raise PaperValidationError("no position to sell")
            if int(qty) > held.available:
                raise PaperValidationError(
                    f"T+1: only {held.available} shares are available to sell today"
                )
            if int(qty) > held.qty:
                raise PaperValidationError("sell qty exceeds position qty")

        if self._is_suspended(self.cur_idx, sec):
            raise PaperValidationError("security is suspended on the current session date")

        if side_int == 0:
            reference = limit if limit is not None else self._reference_price(sec)
            if reference is None or reference <= 0:
                raise PaperValidationError("no quote available to estimate order cost")
            amount = reference * int(qty)
            fees = fee_breakdown(
                self.costs, 0, amount, is_shanghai_stock=is_shanghai(self.market.code(sec))
            )
            if amount + fees["fee_total"] > self.session.cash + 1e-6:
                raise PaperValidationError("insufficient cash for this order")

        order = PaperOrder(
            id=f"ord_{self.session.next_order_seq:06d}",
            date=int(self.session.current_date),
            code=self.market.code(sec),
            sec_id=self.market.sec_ids[sec],
            name=self.market.name(sec),
            side=side_int,
            qty=int(qty),
            order_type=order_type,
            created_at=_now(),
            limit_price=limit,
        )
        self.session.next_order_seq += 1
        self.session.orders.append(order)
        self.session.updated_at = _now()
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        for order in self.session.orders:
            if order.id == str(order_id):
                if not order.is_open:
                    raise PaperConflictError(f"order {order.id} is already {order.status}")
                order.status = "cancelled"
                order.reason = "cancelled by user"
                self.session.updated_at = _now()
                return order
        raise PaperNotFoundError(f"order not found: {order_id}")

    # -- session operations ------------------------------------------------
    def step(self, *, days: int = 1, to_date: int | str | None = None) -> dict[str, Any]:
        self._require_active()
        if self.cur_idx >= self.end_idx:
            raise PaperValidationError("session is already at its end date; reset first")
        if to_date is not None:
            target = to_date_int(to_date)
            if target <= self.session.current_date:
                raise PaperValidationError("to_date must be after the current session date")
            target_idx = min(bisect.bisect_left(self.market.dates, target), self.end_idx)
            count = max(1, target_idx - self.cur_idx)
        else:
            count = int(days)
            if count < 1:
                raise PaperValidationError("days must be >= 1")
        fills: list[dict[str, Any]] = []
        for _ in range(count):
            if self.cur_idx >= self.end_idx:
                break
            self.cur_idx += 1
            day = self.cur_idx
            self.session.current_date = int(self.market.dates[day])
            for position in self.session.positions.values():
                position.available = position.qty  # T+1: yesterday's buys become sellable
            for order in self.session.orders:
                if not order.is_open or order.date >= self.session.current_date:
                    continue
                trade = self._try_fill(order, day)
                if trade is not None:
                    fills.append(trade.to_dict())
            self._mark(day)
            self.session.equity_curve.append(
                {"date": int(self.market.dates[day]), "equity": self.session.equity()}
            )
            if day >= self.end_idx:
                self.session.status = "finished"
        self.session.updated_at = _now()
        payload = self.detail()
        payload["fills"] = fills
        return payload

    def reset(self) -> dict[str, Any]:
        start_idx = self.start_idx
        self.cur_idx = start_idx
        self.session.current_date = int(self.market.dates[start_idx])
        self.session.cash = float(self.session.initial_cash)
        self.session.positions = {}
        self.session.orders = []
        self.session.trades = []
        self.session.next_order_seq = 1
        self.session.next_trade_seq = 1
        self.session.status = "active"
        self.session.equity_curve = [
            {
                "date": int(self.market.dates[start_idx]),
                "equity": round(float(self.session.initial_cash), 4),
            }
        ]
        self.session.updated_at = _now()
        return self.detail()

    def signals_csv(self) -> str:
        """Signals CSV export (filled_qty is cumulative, fill_price the weighted average)."""
        return self.session.signals_csv()

    # -- internals ---------------------------------------------------------
    def _require_active(self) -> None:
        if self.session.status != "active":
            raise PaperValidationError("session is finished; reset it before trading further")

    def _resolve_sec(self, code: str) -> int:
        text = str(code).strip()
        sec = self.market.sec_index.get(text)
        if sec is not None:
            return sec
        for index, record in enumerate(self.market.meta):
            if str(record.get("code", "")) == text:
                return index
        raise PaperValidationError(f"security not found in snapshot: {code!r}")

    def _reference_price(self, sec: int) -> float | None:
        for field_name in ("close", "pre_close"):
            value = self.market.value(field_name, self.cur_idx, sec)
            if np.isfinite(value) and value > 0:
                return float(value)
        return None

    def _is_suspended(self, day: int, sec: int) -> bool:
        suspended = self.market.value("suspended", day, sec)
        if np.isfinite(suspended) and suspended > 0.5:
            return True
        volume = self.market.value("volume", day, sec)
        return bool(np.isfinite(volume) and volume <= 0)

    def _limits(self, day: int, sec: int) -> tuple[float, float]:
        limit_up = self.market.value("limit_up", day, sec)
        limit_down = self.market.value("limit_down", day, sec)
        if np.isfinite(limit_up) and np.isfinite(limit_down) and limit_up > 0 and limit_down > 0:
            return float(limit_up), float(limit_down)
        pre_close = self.market.value("pre_close", day, sec)
        if not (np.isfinite(pre_close) and pre_close > 0):
            return float("nan"), float("nan")
        st = self.market.value("st", day, sec)
        pct = price_limit_pct(
            self.market.board(sec),
            bool(np.isfinite(st) and st > 0.5),
            self.market.dates[day],
            self.rules,
        )
        return (
            round_to_tick(float(pre_close) * (1.0 + pct), self.rules.min_price_tick),
            round_to_tick(float(pre_close) * (1.0 - pct), self.rules.min_price_tick),
        )

    def _reject(self, order: PaperOrder, reason: str) -> None:
        order.status = "rejected"
        order.reason = reason
        order.fill_date = int(self.session.current_date)

    def _try_fill(self, order: PaperOrder, day: int) -> PaperTrade | None:
        sec = self.market.sec_index.get(order.sec_id)
        if sec is None:  # pragma: no cover - snapshot cannot lose securities mid-session
            self._reject(order, "security missing from snapshot")
            return None
        if self._is_suspended(day, sec):
            self._reject(order, "suspended")
            return None
        open_px = self.market.value("open", day, sec)
        high = self.market.value("high", day, sec)
        low = self.market.value("low", day, sec)
        close = self.market.value("close", day, sec)
        if not all(np.isfinite(v) and v > 0 for v in (open_px, high, low, close)) or high < low:
            self._reject(order, "no_quote")
            return None
        limit_up, limit_down = self._limits(day, sec)
        if order.side == 0 and np.isfinite(limit_up) and limit_up > 0 and open_px >= limit_up:
            self._reject(order, "limit_up")
            return None
        if order.side == 1 and np.isfinite(limit_down) and limit_down > 0 and open_px <= limit_down:
            self._reject(order, "limit_down")
            return None
        one_line = abs(high - low) <= 1e-9
        if one_line:
            if order.side == 0 and np.isfinite(limit_up) and limit_up > 0 and high >= limit_up:
                self._reject(order, "limit_up")
            elif (
                order.side == 1 and np.isfinite(limit_down) and limit_down > 0 and low <= limit_down
            ):
                self._reject(order, "limit_down")
            else:
                self._reject(order, "no_quote")
            return None
        if order.order_type == "limit" and order.limit_price is not None:
            limit = round_to_tick(order.limit_price, self.rules.min_price_tick)
            if order.side == 0:
                if low > limit:
                    return None  # not triggered yet, remains pending
                fill_raw = open_px if open_px <= limit else limit
            else:
                if high < limit:
                    return None
                fill_raw = open_px if open_px >= limit else limit
        else:
            fill_raw = open_px
        fill = float(fill_raw)
        fill = max(min(fill, high), low)
        if np.isfinite(limit_up) and limit_up > 0:
            fill = min(fill, float(limit_up))
        if np.isfinite(limit_down) and limit_down > 0:
            fill = max(fill, float(limit_down))
        fill = round_to_tick(fill, self.rules.min_price_tick)
        if fill <= 0:
            self._reject(order, "no_quote")
            return None

        qty = self._fill_qty(order, sec, day)
        if qty <= 0:
            return None
        return self._settle(order, sec, fill, qty)

    def _fill_qty(self, order: PaperOrder, sec: int, day: int) -> int:
        """Shares fillable today: participation cap, buy lot rounding and T+1 availability."""
        remaining = order.remaining_qty
        if remaining <= 0:
            return 0
        volume = self.market.value("volume", day, sec)
        qty = min(remaining, participation_cap(volume, self.participation))
        if order.side == 0:
            return round_buy_qty(self.market.board(sec), qty, self.rules, self.market.sec_type(sec))
        position = self.session.positions.get(order.sec_id)
        if position is None or position.available <= 0:
            self._reject(order, "insufficient_position")
            return 0
        return min(qty, position.available, position.qty)

    def _settle(self, order: PaperOrder, sec: int, fill: float, qty: int) -> PaperTrade | None:
        """Book one fill (cash, position, fees, order fills) and append the trade."""
        amount = fill * qty
        fees = fee_breakdown(
            self.costs,
            order.side,
            amount,
            is_shanghai_stock=is_shanghai(order.code),
        )
        fee_total = float(fees["fee_total"])
        if order.side == 0:
            total = amount + fee_total
            if total > self.session.cash + 1e-6:
                self._reject(order, "insufficient_cash")
                return None
            self.session.cash = round(self.session.cash - total, 4)
            position = self.session.positions.get(order.sec_id)
            if position is None:
                self.session.positions[order.sec_id] = PaperPosition(
                    sec_id=order.sec_id,
                    code=order.code,
                    name=order.name,
                    board=self.market.board(sec),
                    qty=qty,
                    available=0,
                    avg_cost=round(total / qty, 6),
                    last=fill,
                )
            else:
                old_cost = position.avg_cost * position.qty
                position.qty += qty
                position.avg_cost = round((old_cost + total) / position.qty, 6)
                position.last = fill
        else:
            position = self.session.positions.get(order.sec_id)
            if position is None or position.qty < qty or position.available < qty:
                self._reject(order, "insufficient_position")
                return None
            self.session.cash = round(self.session.cash + amount - fee_total, 4)
            position.qty -= qty
            position.available = max(0, position.available - qty)
            position.last = fill
            if position.qty <= 0:
                self.session.positions.pop(order.sec_id, None)
        order.record_fill(
            date=int(self.session.current_date), qty=qty, price=fill, amount=amount, fees=fees
        )
        trade = PaperTrade(
            id=f"trd_{self.session.next_trade_seq:06d}",
            order_id=order.id,
            date=int(self.session.current_date),
            code=order.code,
            sec_id=order.sec_id,
            name=order.name,
            side=order.side,
            qty=qty,
            price=fill,
            amount=round(amount, 4),
            fees=fees,
            created_at=_now(),
        )
        self.session.next_trade_seq += 1
        self.session.trades.append(trade)
        return trade

    def _mark(self, day: int) -> None:
        for position in self.session.positions.values():
            sec = self.market.sec_index.get(position.sec_id)
            if sec is None:
                continue
            close = self.market.value("close", day, sec)
            if np.isfinite(close) and close > 0:
                position.last = float(close)
