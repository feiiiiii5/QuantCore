"""Pure-Python reference backtest engine used only by differential tests.

This module lives under ``tests/reference`` on purpose: production code must always go
through the C++ engine.  It mirrors the documented semantics in
``docs/engine-semantics.md`` and the implementation choices visible in
``cpp/src/sim`` closely enough to detect regressions:

- decisions at T close execute at T+1 with the configured execution price
  (``next_open`` by default),
- target sizing uses the execution reference price and board-specific lot rules
  (MAIN/GEM 100-share multiples; STAR/BSE minimum lot then 1-share increments),
- sells before buys, cash checked with a binary search over affordable quantities,
- T+1 availability, suspension / limit / one-line-board rejection codes,
- fees rounded per component to 1e-4 CNY and summed, commission floored at the minimum,
- participation cap from next-day volume, ``min_rebalance_value`` skip,
- delisted positions force-liquidated at the last mark price.

Money is fixed-point 1e-4 CNY (``int``) exactly like the C++ engine.  pytest-only.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from quantcore.data.panel import PanelData

from .engine_ref_primitives import (
    BOARD_CODES,
    REASONS,
    RefConfig,
    RefResult,
    _px,
    apply_slippage,
    canon_buy_qty,
    compute_costs,
    llround,
)


def run_reference(
    panel: PanelData, weights: np.ndarray, config: RefConfig | None = None
) -> RefResult:
    """Run the reference engine on ``panel`` with a ``(n_time, n_sec)`` target matrix."""
    cfg = config or RefConfig()
    matrix = np.asarray(weights, dtype=np.float64)
    n_time, n_sec = panel.n_time, panel.n_sec
    if matrix.shape != (n_time, n_sec):
        raise ValueError(f"weights shape {matrix.shape} != {(n_time, n_sec)}")
    prices = {
        name: panel.matrix(name)
        for name in (
            "open",
            "high",
            "low",
            "close",
            "limit_up",
            "limit_down",
            "suspended",
            "volume",
        )
    }
    securities = panel.securities.to_dict(orient="records")
    boards = [BOARD_CODES.get(str(record.get("board", "MAIN")), 0) for record in securities]
    shanghai = [str(record.get("exchange", "")).upper() == "SH" for record in securities]
    delist_dates = [int(record.get("delist_date") or 0) for record in securities]
    dates = [int(value) for value in panel.calendar.dates]

    cash = int(cfg.initial_cash)
    lots: dict[int, list[list[int]]] = {}
    last_px: dict[int, int] = {}
    trades: list[dict[str, Any]] = []
    reasons: Counter[int] = Counter()
    equity: list[int] = []
    cash_hist: list[int] = []
    mv_hist: list[int] = []
    prev_close = [0] * n_sec
    pending: np.ndarray | None = None
    pending_equity = 0
    actions: dict[tuple[int, int], dict[str, Any]] = {}
    if cfg.use_panel_corporate_actions:
        indices = panel.sec_index()
        for action in panel.corporate_actions.to_dict(orient="records"):
            if action["sec_id"] in indices and int(action["ex_date"]) > 0:
                actions[indices[action["sec_id"]], int(action["ex_date"])] = action
    for action in cfg.corporate_actions:
        actions[int(action["sec"]), int(action["ex_date"])] = action

    def position_qty(sec: int) -> int:
        return sum(lot[0] for lot in lots.get(sec, []))

    def sellable(sec: int, day: int) -> int:
        return sum(qty for qty, buy_day in lots.get(sec, []) if not cfg.t_plus_one or buy_day < day)

    def consume(sec: int, qty: int, day: int) -> None:
        remaining = qty
        kept: list[list[int]] = []
        for lot_qty, buy_day in lots.get(sec, []):
            if remaining <= 0 or (cfg.t_plus_one and buy_day >= day):
                kept.append([lot_qty, buy_day])
                continue
            take = min(lot_qty, remaining)
            remaining -= take
            if lot_qty - take > 0:
                kept.append([lot_qty - take, buy_day])
        if kept:
            lots[sec] = kept
        else:
            lots.pop(sec, None)

    def market_value() -> int:
        return sum(position_qty(sec) * last_px.get(sec, 0) for sec in lots)

    def mark_to_market(day: int) -> None:
        for sec in range(n_sec):
            if prices["suspended"][day, sec] > 0.5:
                continue
            close_px = prices["close"][day, sec]
            if np.isfinite(close_px) and close_px > 0:
                last_px[sec] = _px(close_px)
                prev_close[sec] = last_px[sec]
        del day

    def fill_price(day: int, sec: int, side: int) -> int:
        ref = _px(prices["open"][day, sec])
        fill = apply_slippage(ref, side, cfg)
        low = _px(prices["low"][day, sec])
        high = _px(prices["high"][day, sec])
        limit_up = _px(prices["limit_up"][day, sec])
        limit_down = _px(prices["limit_down"][day, sec])
        if low > 0 and fill < low:
            fill = low
        if high > 0 and fill > high:
            fill = high
        if limit_up > 0 and fill > limit_up:
            fill = limit_up
        if limit_down > 0 and fill < limit_down:
            fill = limit_down
        return fill

    def prepare(day: int, sec: int, side: int) -> tuple[int, int]:
        if bool(prices["suspended"][day, sec] > 0.5):
            return REASONS["suspended"], -1
        if delist_dates[sec] and dates[day] >= delist_dates[sec]:
            return REASONS["no_quote"], -1
        volume = prices["volume"][day, sec]
        if np.isfinite(volume) and volume <= 0:
            return REASONS["suspended"], -1
        open_px = _px(prices["open"][day, sec])
        high = _px(prices["high"][day, sec])
        low = _px(prices["low"][day, sec])
        close_px = _px(prices["close"][day, sec])
        if high <= 0 or low <= 0 or close_px <= 0 or high < low or open_px <= 0:
            return REASONS["no_quote"], -1
        limit_up = _px(prices["limit_up"][day, sec])
        limit_down = _px(prices["limit_down"][day, sec])
        if side == 0 and limit_up > 0 and open_px >= limit_up:
            return REASONS["limit_up"], -1
        if side == 1 and limit_down > 0 and open_px <= limit_down:
            return REASONS["limit_down"], -1
        if high == low:  # one-line board: no continuous trading
            if side == 0 and limit_up > 0 and high >= limit_up:
                return REASONS["limit_up"], -1
            if side == 1 and limit_down > 0 and low <= limit_down:
                return REASONS["limit_down"], -1
            return REASONS["no_quote"], -1
        cap = -1
        if np.isfinite(volume):
            cap_value = math.floor(float(volume) * cfg.max_participation)
            if cap_value < 1:
                return REASONS["no_quote"], -1
            cap = int(cap_value)
        return 0, cap

    def affordable(sec: int, want: int, price: int) -> int:
        if want <= 0 or price <= 0:
            return 0
        board = boards[sec]

        def cost_of(qty: int) -> int:
            amount = price * qty
            return amount + compute_costs(cfg, 0, amount, shanghai[sec])["fee_total"]

        if board == 2 or board == 3:
            minimum = cfg.star_lot if board == 2 else cfg.bse_lot
            if want < minimum or cost_of(minimum) > cash:
                return 0
            low_qty, high_qty = minimum, want
            while low_qty < high_qty:
                middle = low_qty + (high_qty - low_qty + 1) // 2
                if cost_of(middle) <= cash:
                    low_qty = middle
                else:
                    high_qty = middle - 1
            return low_qty
        lot = cfg.main_lot if cfg.main_lot > 0 else 100
        units = want // lot
        if units <= 0:
            return 0
        low_units, high_units = 0, units
        while low_units < high_units:
            middle = low_units + (high_units - low_units + 1) // 2
            if cost_of(middle * lot) <= cash:
                low_units = middle
            else:
                high_units = middle - 1
        return low_units * lot

    def execute_one(day: int, sec: int, side: int, want: int, cap: int) -> None:
        nonlocal cash
        reason, volume_cap = prepare(day, sec, side)
        if reason:
            reasons[reason] += 1
            return
        qty = want
        cap_value = volume_cap if volume_cap >= 0 else cap
        if side == 1:
            available = sellable(sec, day)
            if available <= 0:
                reasons[REASONS["t_plus_one"]] += 1
                return
            if cap_value >= 0 and qty > cap_value:
                qty = cap_value
            qty = min(qty, available)
            if qty <= 0:
                reasons[REASONS["no_quote"]] += 1
                return
        else:
            if cap_value >= 0 and qty > cap_value:
                qty = cap_value
            qty = canon_buy_qty(cfg, boards[sec], qty)
            if qty <= 0:
                reasons[REASONS["no_quote"]] += 1
                return
            qty = affordable(sec, qty, fill_price(day, sec, side))
            if qty <= 0:
                reasons[REASONS["insufficient_cash"]] += 1
                return
        price = fill_price(day, sec, side)
        amount = price * qty
        costs = compute_costs(cfg, side, amount, shanghai[sec])
        if side == 0:
            cash -= amount + costs["fee_total"]
            lots.setdefault(sec, []).append([qty, day])
        else:
            cash += amount - costs["fee_total"]
            consume(sec, qty, day)
        trades.append(
            {
                "date": dates[day],
                "sec": sec,
                "side": side,
                "px": price,
                "qty": qty,
                "amount": amount,
                **costs,
                "reason": 0,
            }
        )

    def execute(day: int) -> None:
        assert pending is not None
        intents: list[tuple[int, int, int]] = []
        for sec in range(n_sec):
            weight = float(pending[sec])
            if np.isnan(weight):
                continue
            held = position_qty(sec)
            if weight <= 0.0 and held == 0:
                continue
            reference = _px(prices["open"][day, sec])
            if reference <= 0:
                reasons[
                    REASONS["suspended"]
                    if prices["suspended"][day, sec] > 0.5
                    else REASONS["no_quote"]
                ] += 1
                continue
            target_value = llround(weight * pending_equity) if weight > 0 else 0
            desired = (
                canon_buy_qty(cfg, boards[sec], target_value // reference) if weight > 0 else 0
            )
            if desired == held:
                continue
            side = 0 if desired > held else 1
            delta = target_value - reference * held
            if abs(delta) < cfg.min_rebalance_value:
                reasons[REASONS["min_rebalance"]] += 1
                continue
            intents.append((sec, side, abs(desired - held)))
        for sec, side, qty in intents:
            if side == 1:
                execute_one(day, sec, side, qty, -1)
        for sec, side, qty in intents:
            if side == 0:
                execute_one(day, sec, side, qty, -1)

    def liquidate_delisted(day: int) -> None:
        nonlocal cash
        for sec in range(n_sec):
            if not delist_dates[sec] or dates[day] < delist_dates[sec]:
                continue
            qty = position_qty(sec)
            if qty <= 0 or qty > sellable(sec, day):
                continue
            px = last_px.get(sec, 0)
            amount = px * qty
            costs = (
                compute_costs(cfg, 1, amount, shanghai[sec])
                if px > 0
                else {
                    "commission": 0,
                    "stamp_duty": 0,
                    "transfer_fee": 0,
                    "other_fee": 0,
                    "fee_total": 0,
                }
            )
            cash += amount - costs["fee_total"]
            consume(sec, qty, day)
            trades.append(
                {
                    "date": dates[day],
                    "sec": sec,
                    "side": 1,
                    "px": px,
                    "qty": qty,
                    "amount": amount,
                    **costs,
                    "reason": 0,
                }
            )

    for day in range(n_time):
        for sec in range(n_sec):
            action = actions.get((sec, dates[day]))
            if action is None:
                continue
            cash_per_share = _px(float(action.get("cash_per_share", 0.0)))
            cash += position_qty(sec) * cash_per_share
            split = float(action.get("split_ratio", 1.0))
            for lot in lots.get(sec, []):
                lot[0] = llround(lot[0] * split)
            if prev_close[sec] > 0:
                prev_close[sec] = llround((prev_close[sec] - cash_per_share) / split)
                if prev_close[sec] > 0:
                    last_px[sec] = prev_close[sec]
        if pending is not None:
            execute(day)
            pending = None
        liquidate_delisted(day)
        mark_to_market(day)
        mv = market_value()
        equity.append(cash + mv)
        cash_hist.append(cash)
        mv_hist.append(mv)
        if day + 1 < n_time:
            row = matrix[day]
            if np.any(~np.isnan(row)):
                pending = row
                pending_equity = cash + mv

    metrics = _metrics(np.asarray(equity, dtype=np.int64), trades, cfg)
    return RefResult(
        dates=dates,
        equity=equity,
        cash=cash_hist,
        market_value=mv_hist,
        trades=trades,
        metrics=metrics,
        reasons=dict(reasons),
        final_qty={sec: position_qty(sec) for sec in lots},
    )


def _metrics(equity: np.ndarray, trades: list[dict[str, Any]], cfg: RefConfig) -> dict[str, float]:
    values = equity.astype(np.float64)
    n = len(values)
    total_fees = float(sum(trade["fee_total"] for trade in trades))
    if n < 2:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "turnover": 0.0,
            "total_fees": total_fees,
            "trade_count": float(len(trades)),
            "trading_days": float(n),
        }
    initial = float(cfg.initial_cash)
    returns = np.empty(n)
    returns[0] = values[0] / initial - 1.0
    returns[1:] = values[1:] / values[:-1] - 1.0
    total_return = float(values[-1] / initial - 1.0)
    years = (n - 1) / cfg.annual_days
    annualized = (
        float((1.0 + total_return) ** (1.0 / years) - 1.0)
        if years > 0 and total_return > -1
        else 0.0
    )
    volatility = float(np.std(returns, ddof=1) * math.sqrt(cfg.annual_days)) if n > 2 else 0.0
    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1)) if n > 2 else 0.0
    sharpe = mean / std * math.sqrt(cfg.annual_days) if std > 0 else 0.0
    peaks = np.maximum.accumulate(values)
    max_drawdown = float(np.max(1.0 - values / peaks)) if n else 0.0
    calmar = annualized / max_drawdown if max_drawdown > 0 else 0.0
    mean_equity = float(np.mean(np.concatenate(([initial], values))))
    turnover = (
        float(sum(abs(trade["amount"]) for trade in trades) / mean_equity)
        if mean_equity > 0
        else 0.0
    )
    return {
        "total_return": total_return,
        "annualized_return": annualized,
        "volatility": volatility,
        "sharpe": float(sharpe),
        "sortino": 0.0,
        "max_drawdown": max_drawdown,
        "calmar": float(calmar),
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "turnover": turnover,
        "total_fees": total_fees,
        "trade_count": float(len(trades)),
        "trading_days": float(n),
    }
