"""Basic walk-forward evaluation: split the sample into contiguous out-of-sample folds."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..data.panel import PanelData
from ..errors import StrategyValidationError
from ..snapshot.reader import Snapshot
from ..strategy.spec import StrategySpec


def _fold_windows(
    panel: PanelData, folds: int, start: int | None, end: int | None
) -> list[tuple[int, int]]:
    dates = list(panel.calendar.dates)
    lo = 0
    hi = len(dates) - 1
    if start is not None:
        from ..calendar import to_date_int

        lo = max(lo, panel.calendar.index_of(to_date_int(start)))
    if end is not None:
        from ..calendar import to_date_int

        hi = min(hi, panel.calendar.index_of(to_date_int(end)))
    if lo >= hi:
        raise StrategyValidationError("walk-forward window has no trading days")
    total = hi - lo + 1
    if folds < 2 or folds > total:
        raise StrategyValidationError(f"folds must be in [2, {total}]")
    windows: list[tuple[int, int]] = []
    base = total // folds
    remainder = total % folds
    cursor = lo
    for index in range(folds):
        size = base + (1 if index < remainder else 0)
        windows.append((cursor, min(cursor + size - 1, hi)))
        cursor += size
    return windows


def run_walk_forward(
    panel: PanelData,
    template: str,
    params: dict[str, Any] | None = None,
    *,
    folds: int = 3,
    start: int | None = None,
    end: int | None = None,
    initial_cash: float = 1_000_000.0,
    snapshot: Snapshot | None = None,
) -> dict[str, Any]:
    """Run each fold independently with the same fixed parameters (basic walk-forward)."""
    spec = StrategySpec(name=template, template=template, params=dict(params or {}))
    strategy = spec.load()
    weights = strategy.generate_targets(panel)
    windows = _fold_windows(panel, int(folds), start, end)
    target: PanelData | Snapshot = snapshot if snapshot is not None else panel
    fold_rows: list[dict[str, Any]] = []
    for index, (lo, hi) in enumerate(windows, start=1):
        config = BacktestConfig(
            start=int(panel.calendar.dates[lo]),
            end=int(panel.calendar.dates[hi]),
            initial_cash=float(initial_cash),
        )
        result = run_backtest(
            target,
            weights,
            config,
            strategy_metadata=strategy.metadata(),
            snapshot_metadata=(
                snapshot.describe() if snapshot is not None else {"synthetic": True}
            ),
        )
        fold_rows.append(
            {
                "fold": index,
                "start": int(panel.calendar.dates[lo]),
                "end": int(panel.calendar.dates[hi]),
                "trading_days": int(result.metrics.get("trading_days", 0)),
                "trade_count": len(result.trades),
                "metrics": result.metrics,
            }
        )
    sharpes = np.asarray(
        [float(row["metrics"].get("sharpe", 0.0)) for row in fold_rows], dtype=np.float64
    )
    returns = np.asarray(
        [float(row["metrics"].get("total_return", 0.0)) for row in fold_rows],
        dtype=np.float64,
    )
    drawdowns = np.asarray(
        [float(row["metrics"].get("max_drawdown", 0.0)) for row in fold_rows], dtype=np.float64
    )
    trades = np.asarray([int(row["trade_count"]) for row in fold_rows], dtype=np.float64)
    aggregate: dict[str, Any] = {
        "mean_sharpe": round(float(sharpes.mean()), 6),
        "std_sharpe": round(float(sharpes.std(ddof=1)), 6) if sharpes.size > 1 else 0.0,
        "mean_return": round(float(returns.mean()), 6),
        "positive_folds": int((returns > 0).sum()),
        "folds": len(fold_rows),
        # Metrics-shaped aliases so UI metric cards can render the aggregate directly.
        "total_return": round(float(returns.mean()), 6),
        "sharpe": round(float(sharpes.mean()), 6),
        "max_drawdown": round(float(drawdowns.mean()), 6),
        "trade_count": int(trades.sum()),
        "trading_days": int(sum(int(row["trading_days"]) for row in fold_rows)),
    }
    return {
        "template": template,
        "params": dict(params or {}),
        "engine_backend": "cpp",
        "folds": fold_rows,
        "aggregate": aggregate,
    }


__all__ = ["run_walk_forward"]
