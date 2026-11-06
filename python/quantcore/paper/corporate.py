"""Historical paper ex-date settlement, matching the native pre-tax approximation.

Cash is credited on ex-date, irrespective of the recorded payment date. Splits
round each recorded purchase lot to the nearest share (positive ties upward),
as the native ledger does; fractional cash entitlements are not fabricated.
Older positions without purchase lots migrate as one aggregate quantity.
"""

from __future__ import annotations

import math
from typing import Any

from ..backtest.config import BacktestConfig, CostModelConfig
from ..backtest.engine import _corporate_actions
from ..errors import BacktestError
from .errors import PaperValidationError
from .market import PaperMarketData
from .models import PaperPosition, PaperSession


def purchase_lots(position: PaperPosition) -> list[int]:
    lots = list(position.lots) if position.lots else [position.qty]
    if any(lot <= 0 for lot in lots) or sum(lots) != position.qty:
        raise PaperValidationError("purchase lots do not match the paper position")
    return lots


def sell_lots(position: PaperPosition, qty: int) -> None:
    """Retain purchase quantities in FIFO order for later split rounding."""
    remaining, lots = qty, []
    for lot in purchase_lots(position):
        removed = min(lot, remaining)
        remaining -= removed
        if lot > removed:
            lots.append(lot - removed)
    position.lots = lots


def _money(value: float) -> float:
    return math.floor(value * 10_000 + 0.5) / 10_000


class PaperCorporateActions:
    def __init__(
        self, market: PaperMarketData, session: PaperSession, costs: CostModelConfig
    ) -> None:
        self.market, self.session = market, session
        self.events: dict[int, list[dict[str, Any]]] = {}
        try:
            events = _corporate_actions(
                market.panel,
                BacktestConfig(start=session.start_date, end=session.end_date, costs=costs),
                market.sec_ids,
            )
        except (BacktestError, ValueError) as exc:
            raise PaperValidationError(str(exc)) from exc
        for event in events:
            day = int(event["ex_date"])
            if not session.start_date < day <= session.end_date:
                continue
            cash, split = float(event["cash_per_share"]), float(event["split_ratio"])
            if not math.isfinite(cash) or cash < 0 or not math.isfinite(split) or split <= 0:
                raise PaperValidationError(
                    "corporate action requires finite cash >= 0 and split > 0"
                )
            rights = float(event.get("rights_ratio", 0))
            if not math.isfinite(rights) or rights != 0:
                raise PaperValidationError(
                    "rights subscriptions are not supported by paper accounts"
                )
            if costs.enable_dividend_tax and cash > 0:
                raise PaperValidationError("dividend tax is not implemented; use the pre-tax model")
            if cash or split != 1:
                self.events.setdefault(day, []).append(event)

    def apply(self, index: int) -> None:
        day = self.market.dates[index]
        applied = {(event["date"], event["sec_id"]) for event in self.session.corporate_events}
        plans = []
        for event in self.events.get(day, []):
            sec = int(event["sec"])
            sec_id = self.market.sec_ids[sec]
            if (day, sec_id) in applied:
                continue
            holding = self.session.positions.get(sec_id)
            qty = holding.qty if holding else 0
            cash, ratio = _money(float(event["cash_per_share"])), float(event["split_ratio"])
            lots = (
                [math.floor(lot * ratio + 0.5) for lot in purchase_lots(holding)] if holding else []
            )
            new_qty = sum(lots)
            mark = (holding.last - cash) / ratio if holding else 0
            if holding and (new_qty <= 0 or not math.isfinite(mark) or mark <= 0):
                raise PaperValidationError(
                    "corporate action produces unsupported zero shares or price"
                )
            plans.append((sec, sec_id, holding, qty, cash, lots, new_qty, mark))
        # Validate all holdings before mutating any ledger or order on this date.
        for sec, sec_id, holding, qty, cash, lots, new_qty, mark in plans:
            credited = _money(qty * cash)
            self.session.cash = _money(self.session.cash + credited)
            if holding:
                cost = holding.avg_cost * qty
                holding.qty, holding.lots = new_qty, [lot for lot in lots if lot > 0]
                holding.avg_cost = round(cost / new_qty, 6)
                holding.last = _money(mark)
            cancelled = []
            for order in self.session.orders:
                if order.sec_id == sec_id and order.is_open and order.date < day:
                    order.status = "cancelled"
                    order.reason = "corporate action: resubmit using ex-date prices and quantities"
                    cancelled.append(order.id)
            self.session.corporate_events.append(
                {
                    "date": day,
                    "code": self.market.code(sec),
                    "sec_id": sec_id,
                    "cash": credited,
                    "qty_before": qty,
                    "qty_after": new_qty,
                    "cancelled_order_ids": cancelled,
                    "reason": "Pre-tax cash credited on ex-date; pre-action orders must be resubmitted. Payment delay and fractional cash are not modeled.",
                    "model": "pre_tax_ex_date_approximation",
                }
            )
