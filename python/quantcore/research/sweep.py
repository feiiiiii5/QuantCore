"""API-facing parameter sweep wrapper around :mod:`quantcore.backtest.sweep`."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..backtest.config import BacktestConfig
from ..backtest.sweep import expand_grid, run_sweep
from ..data.panel import PanelData
from ..errors import StrategyValidationError
from ..strategy.spec import StrategySpec

MAX_SWEEP_POINTS = 200


def run_api_sweep(
    panel: PanelData,
    template: str,
    param_grid: dict[str, list[Any]],
    *,
    config: BacktestConfig | None = None,
    workers: int = 1,
    max_points: int = MAX_SWEEP_POINTS,
) -> dict[str, Any]:
    """Run a bounded, deterministic sweep and shape it for the UI."""
    if not param_grid:
        raise StrategyValidationError("param_grid must not be empty")
    combinations = expand_grid(param_grid)
    if len(combinations) > max_points:
        raise StrategyValidationError(
            f"param grid expands to {len(combinations)} points; the synchronous API is "
            f"bounded to {max_points}"
        )
    spec = StrategySpec(name=template, template=template)
    result = run_sweep(
        panel,
        spec,
        param_grid,
        config or BacktestConfig(),
        max_workers=max(1, min(int(workers), 16)),
    )
    points: list[dict[str, Any]] = []
    for point in result.points:
        points.append(
            {
                "params": point.params,
                "metrics": point.metrics,
                "error": point.error,
            }
        )
    best_point = result.best("sharpe")
    best = (
        None
        if best_point is None
        else {
            "params": best_point.params,
            "metrics": best_point.metrics,
            "metric": "sharpe",
        }
    )
    payload: dict[str, Any] = {
        "template": template,
        "points": points,
        "best": best,
        "grid_size": len(combinations),
        "engine_backend": result.engine_backend,
    }
    heatmap = _heatmap(param_grid, points, metric="sharpe")
    if heatmap is not None:
        payload["heatmap"] = heatmap
    return payload


def _heatmap(
    param_grid: dict[str, list[Any]], points: list[dict[str, Any]], *, metric: str = "sharpe"
) -> dict[str, Any] | None:
    keys = sorted(param_grid)
    if len(keys) != 2:
        return None
    x_key, y_key = keys
    x_values = list(param_grid[x_key])
    y_values = list(param_grid[y_key])
    table = pd.DataFrame(
        [
            {
                x_key: point["params"].get(x_key),
                y_key: point["params"].get(y_key),
                metric: (point["metrics"] or {}).get(metric),
            }
            for point in points
        ]
    )
    if table.empty:
        return None
    pivot = table.pivot_table(index=y_key, columns=x_key, values=metric, aggfunc="mean")
    pivot = pivot.reindex(index=y_values, columns=x_values)
    return {
        "x_param": x_key,
        "y_param": y_key,
        "x_values": x_values,
        "y_values": y_values,
        "metric": metric,
        "z": [
            [None if pd.isna(value) else float(value) for value in row] for row in pivot.to_numpy()
        ],
    }


__all__ = ["MAX_SWEEP_POINTS", "run_api_sweep"]
