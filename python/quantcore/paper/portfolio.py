"""Read-only multi-session paper portfolio aggregation (M9-004).

Combines already-persisted paper sessions into one comparison view: each session's equity
curve is normalised by its own starting cash, aligned on the strict intersection of trading
dates, weighted and rebased to ``initial_cash``.  Nothing is written back, no order is placed
and no network access happens.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .errors import PaperValidationError
from .models import PaperSession

MIN_SESSIONS = 2
MAX_SESSIONS = 10
WEIGHT_TOLERANCE = 1e-6
MIN_COMMON_DATES = 2
PERIODS_PER_YEAR = 244


def build_portfolio(
    sessions: list[PaperSession],
    weights: list[float],
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    """Aggregate sessions into a rebased equity curve, metrics and contributions."""
    if len(sessions) < MIN_SESSIONS:
        raise PaperValidationError("a portfolio needs at least two paper sessions")
    if len(sessions) > MAX_SESSIONS:
        raise PaperValidationError("a portfolio supports at most ten paper sessions")
    if len(sessions) != len(weights):
        raise PaperValidationError("allocations and weights length mismatch")
    if len({session.id for session in sessions}) != len(sessions):
        raise PaperValidationError("duplicate paper session in portfolio allocations")
    if not float(initial_cash) > 0:
        raise PaperValidationError("initial_cash must be positive")

    weight_array = np.asarray([float(value) for value in weights], dtype=np.float64)
    if not np.all(np.isfinite(weight_array)) or np.any(weight_array <= 0):
        raise PaperValidationError("every allocation weight must be a positive finite number")
    if abs(float(weight_array.sum()) - 1.0) > WEIGHT_TOLERANCE:
        raise PaperValidationError(
            f"allocation weights must sum to 1.0 (got {float(weight_array.sum()):.8f})"
        )

    curves: list[dict[int, float]] = []
    for session in sessions:
        starting_cash = float(session.initial_cash)
        if starting_cash <= 0:
            raise PaperValidationError(f"session {session.id} has no starting cash")
        points: dict[int, float] = {}
        for point in session.equity_curve:
            try:
                date = int(point["date"])
                equity_value = float(point["equity"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PaperValidationError(
                    f"session {session.id} has a corrupt equity curve"
                ) from exc
            if math.isfinite(equity_value):
                points[date] = equity_value / starting_cash
        if not points:
            raise PaperValidationError(f"session {session.id} has no equity curve")
        curves.append(points)

    common_dates = sorted(set.intersection(*[set(curve) for curve in curves]))
    if len(common_dates) < MIN_COMMON_DATES:
        raise PaperValidationError(
            "sessions share fewer than "
            f"{MIN_COMMON_DATES} common equity-curve dates; step them to overlapping windows "
            "before aggregating"
        )
    normalized = np.asarray(
        [[curves[index][date] for date in common_dates] for index in range(len(sessions))],
        dtype=np.float64,
    )
    weighted = weight_array @ normalized
    base = float(weighted[0])
    if base <= 0:
        raise PaperValidationError("combined normalised equity at the first date is not positive")
    equity_values = float(initial_cash) * weighted / base
    normalized_equity = equity_values / float(initial_cash)
    metrics = _metrics(equity_values, PERIODS_PER_YEAR)

    contributions: list[dict[str, Any]] = []
    for index, session in enumerate(sessions):
        first = float(normalized[index, 0])
        last = float(normalized[index, -1])
        total = last / first - 1.0 if first > 0 else 0.0
        contributions.append(
            {
                "session_id": session.id,
                "name": session.name,
                "weight": round(float(weight_array[index]), 6),
                "total_return": round(total, 6),
                "contribution": round(float(weight_array[index]) * total, 6),
            }
        )
    allocations = [
        {
            "session_id": session.id,
            "name": session.name,
            "snapshot": session.snapshot.get("id"),
            "synthetic": bool(session.snapshot.get("synthetic", False)),
            "weight": round(float(weight_array[index]), 6),
        }
        for index, session in enumerate(sessions)
    ]
    return {
        "allocations": allocations,
        "dates": [int(date) for date in common_dates],
        "equity": [round(float(value), 4) for value in equity_values],
        "normalized_equity": [round(float(value), 6) for value in normalized_equity],
        "metrics": metrics,
        "contributions": contributions,
        "note": (
            "严格取各 paper session equity_curve 的交易日交集(不插值); 每个 session 按 "
            "starting_cash 归一化后按权重加总, 并在首个共同交易日重基到 initial_cash; "
            "指标按 244 交易日/年. 只读聚合, 不写回账户、不产生委托."
        ),
    }


def _metrics(equity: np.ndarray, periods_per_year: int) -> dict[str, float]:
    values = np.asarray(equity, dtype=np.float64)
    if values.size < 2 or values[0] <= 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }
    total_return = float(values[-1] / values[0] - 1.0)
    periods = max(int(values.size - 1), 1)
    if total_return > -1.0:
        annualized = (1.0 + total_return) ** (periods_per_year / periods) - 1.0
    else:
        annualized = -1.0
    returns = np.diff(values) / values[:-1]
    volatility = (
        float(np.std(returns, ddof=1) * math.sqrt(periods_per_year)) if returns.size > 1 else 0.0
    )
    std = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    sharpe = float(np.mean(returns) / std * math.sqrt(periods_per_year)) if std > 0 else 0.0
    peak = np.maximum.accumulate(values)
    drawdown = float(np.max(1.0 - values / peak)) if peak.size else 0.0
    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(float(annualized), 6),
        "volatility": round(volatility, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(drawdown, 6),
    }


__all__ = [
    "MAX_SESSIONS",
    "MIN_COMMON_DATES",
    "MIN_SESSIONS",
    "PERIODS_PER_YEAR",
    "WEIGHT_TOLERANCE",
    "build_portfolio",
]
