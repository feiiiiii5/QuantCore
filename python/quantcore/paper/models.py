"""Persistent paper-trading session models (JSON-serialisable dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1


def _round_money(value: float) -> float:
    return round(float(value), 4)


def _side_int(value: Any) -> int:
    """Accept both persisted ints and the API's ``buy``/``sell`` strings."""
    if isinstance(value, str):
        return 1 if value.strip().lower() == "sell" else 0
    return int(value)


@dataclass
class PaperPosition:
    """One simulated holding (board-lot quantities, A-share T+1 availability)."""

    sec_id: str
    code: str
    name: str
    board: str
    qty: int
    available: int
    avg_cost: float
    last: float

    def market_value(self) -> float:
        return _round_money(self.qty * self.last)

    def pnl(self) -> float:
        return _round_money((self.last - self.avg_cost) * self.qty)

    def pnl_pct(self) -> float:
        if self.avg_cost <= 0:
            return 0.0
        return round(self.last / self.avg_cost - 1.0, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sec_id": self.sec_id,
            "code": self.code,
            "name": self.name,
            "board": self.board,
            "qty": int(self.qty),
            "available": int(self.available),
            "avg_cost": _round_money(self.avg_cost),
            "last": _round_money(self.last),
            "market_value": self.market_value(),
            "pnl": self.pnl(),
            "pnl_pct": self.pnl_pct(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperPosition:
        return cls(
            sec_id=str(payload["sec_id"]),
            code=str(payload.get("code", "")),
            name=str(payload.get("name", "")),
            board=str(payload.get("board", "MAIN")),
            qty=int(payload.get("qty", 0)),
            available=int(payload.get("available", 0)),
            avg_cost=float(payload.get("avg_cost", 0.0)),
            last=float(payload.get("last", 0.0)),
        )


@dataclass
class PaperOrder:
    """A simulated order; ``side`` is 0=buy, 1=sell. No broker/network involvement."""

    id: str
    date: int
    code: str
    sec_id: str
    name: str
    side: int
    qty: int
    order_type: str
    created_at: str
    limit_price: float | None = None
    status: str = "pending"
    filled_qty: int = 0
    fill_price: float | None = None
    fill_date: int | None = None
    fees: dict[str, float] | None = None
    reason: str | None = None

    @property
    def side_name(self) -> str:
        return "buy" if self.side == 0 else "sell"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": int(self.date),
            "code": self.code,
            "sec_id": self.sec_id,
            "name": self.name,
            "side": self.side_name,
            "qty": int(self.qty),
            "order_type": self.order_type,
            "limit_price": None if self.limit_price is None else _round_money(self.limit_price),
            "status": self.status,
            "filled_qty": int(self.filled_qty),
            "fill_price": None if self.fill_price is None else _round_money(self.fill_price),
            "fill_date": None if self.fill_date is None else int(self.fill_date),
            "fees": dict(self.fees) if self.fees else None,
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperOrder:
        return cls(
            id=str(payload["id"]),
            date=int(payload["date"]),
            code=str(payload.get("code", "")),
            sec_id=str(payload.get("sec_id", "")),
            name=str(payload.get("name", "")),
            side=_side_int(payload.get("side", 0)),
            qty=int(payload["qty"]),
            order_type=str(payload.get("order_type", "market")),
            created_at=str(payload.get("created_at", "")),
            limit_price=payload.get("limit_price"),
            status=str(payload.get("status", "pending")),
            filled_qty=int(payload.get("filled_qty", 0)),
            fill_price=payload.get("fill_price"),
            fill_date=payload.get("fill_date"),
            fees=dict(payload["fees"]) if payload.get("fees") else None,
            reason=payload.get("reason"),
        )


@dataclass
class PaperTrade:
    """A simulated fill (fees included; amount is CNY not fixed point)."""

    id: str
    order_id: str
    date: int
    code: str
    sec_id: str
    name: str
    side: int
    qty: int
    price: float
    amount: float
    fees: dict[str, float]
    created_at: str

    @property
    def side_name(self) -> str:
        return "buy" if self.side == 0 else "sell"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "date": int(self.date),
            "code": self.code,
            "sec_id": self.sec_id,
            "name": self.name,
            "side": self.side_name,
            "qty": int(self.qty),
            "price": _round_money(self.price),
            "amount": _round_money(self.amount),
            "fee_total": _round_money(self.fees.get("fee_total", 0.0)),
            "fees": {key: _round_money(value) for key, value in self.fees.items()},
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperTrade:
        fees = payload.get("fees") or {
            "commission": payload.get("commission", 0.0),
            "stamp_duty": payload.get("stamp_duty", 0.0),
            "transfer_fee": payload.get("transfer_fee", 0.0),
            "other_fee": payload.get("other_fee", 0.0),
            "fee_total": payload.get("fee_total", 0.0),
        }
        return cls(
            id=str(payload["id"]),
            order_id=str(payload.get("order_id", "")),
            date=int(payload["date"]),
            code=str(payload.get("code", "")),
            sec_id=str(payload.get("sec_id", "")),
            name=str(payload.get("name", "")),
            side=_side_int(payload.get("side", 0)),
            qty=int(payload["qty"]),
            price=float(payload.get("price", 0.0)),
            amount=float(payload.get("amount", 0.0)),
            fees={str(key): float(value) for key, value in fees.items()},
            created_at=str(payload.get("created_at", "")),
        )


@dataclass
class PaperSession:
    """Complete, self-contained simulated account state persisted as one JSON file."""

    id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    snapshot: dict[str, Any]
    start_date: int
    end_date: int
    current_date: int
    initial_cash: float
    cash: float
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    orders: list[PaperOrder] = field(default_factory=list)
    trades: list[PaperTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    next_order_seq: int = 1
    next_trade_seq: int = 1
    schema_version: int = SCHEMA_VERSION

    # -- derived views -----------------------------------------------------
    def market_value(self) -> float:
        return _round_money(
            sum(position.qty * position.last for position in self.positions.values())
        )

    def equity(self) -> float:
        return _round_money(self.cash + self.market_value())

    def account_view(self) -> dict[str, Any]:
        equity = self.equity()
        pnl = equity - float(self.initial_cash)
        return {
            "cash": _round_money(self.cash),
            "market_value": self.market_value(),
            "equity": equity,
            "pnl": _round_money(pnl),
            "pnl_pct": round(pnl / float(self.initial_cash), 6) if self.initial_cash else 0.0,
        }

    def session_view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "snapshot": self.snapshot.get("id"),
            "snapshot_meta": self.snapshot,
            "current_date": int(self.current_date),
            "start_date": int(self.start_date),
            "end_date": int(self.end_date),
            "cash": _round_money(self.cash),
            "equity": self.equity(),
            "starting_cash": _round_money(self.initial_cash),
            "position_count": len(self.positions),
            "pending_orders": sum(1 for order in self.orders if order.status == "pending"),
            "synthetic": bool(self.snapshot.get("synthetic", False)),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "snapshot": dict(self.snapshot),
            "start_date": int(self.start_date),
            "end_date": int(self.end_date),
            "current_date": int(self.current_date),
            "initial_cash": _round_money(self.initial_cash),
            "cash": _round_money(self.cash),
            "positions": {key: value.to_dict() for key, value in self.positions.items()},
            "orders": [order.to_dict() for order in self.orders],
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": [
                {"date": int(point["date"]), "equity": _round_money(float(point["equity"]))}
                for point in self.equity_curve
            ],
            "config": dict(self.config),
            "next_order_seq": int(self.next_order_seq),
            "next_trade_seq": int(self.next_trade_seq),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperSession:
        positions = {
            str(key): PaperPosition.from_dict(value)
            for key, value in (payload.get("positions") or {}).items()
        }
        return cls(
            id=str(payload["id"]),
            name=str(payload.get("name", "paper session")),
            status=str(payload.get("status", "active")),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            snapshot=dict(payload.get("snapshot") or {}),
            start_date=int(payload["start_date"]),
            end_date=int(payload["end_date"]),
            current_date=int(payload["current_date"]),
            initial_cash=float(payload["initial_cash"]),
            cash=float(payload["cash"]),
            positions=positions,
            orders=[PaperOrder.from_dict(item) for item in payload.get("orders") or []],
            trades=[PaperTrade.from_dict(item) for item in payload.get("trades") or []],
            equity_curve=[
                {"date": int(point["date"]), "equity": float(point["equity"])}
                for point in payload.get("equity_curve") or []
            ],
            config=dict(payload.get("config") or {}),
            next_order_seq=int(payload.get("next_order_seq", 1)),
            next_trade_seq=int(payload.get("next_trade_seq", 1)),
            schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
        )


__all__ = [
    "SCHEMA_VERSION",
    "PaperOrder",
    "PaperPosition",
    "PaperSession",
    "PaperTrade",
]
