"""Basic performance attribution: FIFO realized/unrealized PnL grouped by industry."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..backtest.result import BacktestResult
from ..data.panel import PanelData


def _industry_map(panel: PanelData) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for record in panel.securities.to_dict(orient="records"):
        industry = str(record.get("industry") or "").strip() or "未分类"
        mapping[str(record["sec_id"])] = industry
    return mapping


def attribute_by_industry(
    result: BacktestResult,
    panel: PanelData,
) -> dict[str, Any]:
    """Approximate per-industry contribution from FIFO trade reconstruction.

    Realized PnL comes from closed lots (fees included); open positions are marked at the
    last close.  This is a research summary, not an accounting statement.
    """
    industry = _industry_map(panel)
    close = panel.matrix("close")
    last_close: dict[str, float] = {}
    if close.shape[0]:
        for index, sec in enumerate(panel.sec_id_list):
            value = close[-1, index]
            if np.isfinite(value) and value > 0:
                last_close[sec] = float(value)

    lots: dict[str, list[list[float]]] = defaultdict(list)  # sec -> [qty, total_cost_1e4]
    realized: dict[str, float] = defaultdict(float)
    for trade in result.trades.sort_values(["date", "sec_index"]).to_dict(orient="records"):
        sec = str(trade.get("sec_id") or "")
        qty = int(trade.get("qty", 0))
        if not sec or qty <= 0:
            continue
        amount = float(trade.get("amount", 0))
        fees = float(trade.get("fee_total", 0))
        if int(trade.get("side", 0)) == 0:  # buy
            lots[sec].append([float(qty), amount + fees])
        else:  # sell
            remaining = float(qty)
            proceeds = amount - fees
            removed_cost = 0.0
            book = lots[sec]
            while remaining > 0 and book:
                lot_qty, lot_cost = book[0]
                take = min(lot_qty, remaining)
                ratio = take / lot_qty
                removed_cost += lot_cost * ratio
                remaining -= take
                if take >= lot_qty:
                    book.pop(0)
                else:
                    book[0] = [lot_qty - take, lot_cost * (1.0 - ratio)]
            realized[sec] += proceeds - removed_cost

    unrealized: dict[str, float] = defaultdict(float)
    market_value: dict[str, float] = defaultdict(float)
    for sec, book in lots.items():
        remaining_qty = sum(lot[0] for lot in book)
        remaining_cost = sum(lot[1] for lot in book)
        if remaining_qty <= 0:
            continue
        mark = last_close.get(sec)
        if mark is None:
            continue
        value = remaining_qty * mark
        market_value[industry.get(sec, "未分类")] += value
        unrealized[industry.get(sec, "未分类")] += value - remaining_cost

    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {"realized": 0.0, "unrealized": 0.0, "market_value": 0.0, "securities": 0.0}
    )
    for sec, pnl in realized.items():
        name = industry.get(sec, "未分类")
        grouped[name]["realized"] += pnl
        grouped[name]["securities"] += 1
    for name, pnl in unrealized.items():
        grouped[name]["unrealized"] += pnl
        grouped[name]["market_value"] += market_value.get(name, 0.0)

    final_equity = float(result.equity_yuan[-1]) if len(result.equity) else 0.0
    rows: list[dict[str, Any]] = []
    for name, values in grouped.items():
        pnl = values["realized"] + values["unrealized"]
        rows.append(
            {
                "industry": name,
                "pnl": round(pnl / 10000.0, 2),
                "realized": round(values["realized"] / 10000.0, 2),
                "unrealized": round(values["unrealized"] / 10000.0, 2),
                "market_value": round(values["market_value"] / 10000.0, 2),
                "weight": round(values["market_value"] / 10000.0 / final_equity, 6)
                if final_equity > 0
                else 0.0,
                "securities": int(values["securities"]),
            }
        )
    rows.sort(key=lambda row: row["pnl"], reverse=True)
    total_pnl = sum(row["pnl"] for row in rows)
    return {
        "industries": rows,
        "total_pnl": round(total_pnl, 2),
        "final_equity": round(final_equity, 2),
        "trade_count": len(result.trades),
        "note": "basic FIFO attribution from trades and final marks; research summary only",
    }


__all__ = ["attribute_by_industry"]
