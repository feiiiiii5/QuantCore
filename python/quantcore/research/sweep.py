"""API-facing parameter sweep: bounded full grid or deterministic random sampling.

Grid mode keeps the historical behaviour (``run_sweep`` over the whole product of
``param_grid``, rejected above 200 points).  Random mode samples without replacement from
the same product with a fixed seed, which lets large grids run within the synchronous API
budget while staying reproducible.
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..backtest.sweep import expand_grid, run_sweep
from ..data.panel import PanelData
from ..errors import StrategyValidationError
from ..strategy.spec import StrategySpec

MAX_SWEEP_POINTS = 200
#: Safety cap for materialising a random-sampled grid (no need to expand 10^9 combos).
MAX_RANDOM_GRID = 200_000
VALID_MODES = ("grid", "random")


def run_api_sweep(
    panel: PanelData,
    template: str,
    param_grid: dict[str, list[Any]],
    *,
    config: BacktestConfig | None = None,
    workers: int = 1,
    max_points: int = MAX_SWEEP_POINTS,
    sample_size: int = 0,
    mode: str = "grid",
    seed: int = 42,
) -> dict[str, Any]:
    """Run a bounded, deterministic sweep and shape it for the UI."""
    if not param_grid:
        raise StrategyValidationError("param_grid must not be empty")
    sweep_mode = str(mode).lower()
    if sweep_mode not in VALID_MODES:
        raise StrategyValidationError(f"mode must be one of {VALID_MODES}")
    combinations = expand_grid(param_grid)
    grid_size = len(combinations)
    if grid_size == 0:
        raise StrategyValidationError("param_grid expands to zero combinations")
    effective_workers = max(1, min(int(workers), 16))

    if sweep_mode == "grid":
        if int(sample_size) != 0:
            raise StrategyValidationError(
                "sample_size is only valid with mode='random'; omit it for a full grid"
            )
        if grid_size > max_points:
            raise StrategyValidationError(
                f"param grid expands to {grid_size} points; the synchronous API is "
                f"bounded to {max_points}. Use mode='random' with sample_size to sample it."
            )
        points, backend = _run_grid(
            panel, template, param_grid, config or BacktestConfig(), effective_workers
        )
        requested = grid_size
    else:
        size = int(sample_size)
        if not 1 <= size <= max_points:
            raise StrategyValidationError(
                f"random mode requires sample_size between 1 and {max_points}"
            )
        if grid_size > MAX_RANDOM_GRID:
            raise StrategyValidationError(
                f"param grid expands to {grid_size} points; random sampling is capped at "
                f"{MAX_RANDOM_GRID} combinations"
            )
        rng = random.Random(int(seed))
        sampled = rng.sample(combinations, min(size, grid_size))
        points, backend = _run_combinations(
            panel, template, sampled, config or BacktestConfig(), effective_workers
        )
        requested = size

    payload: dict[str, Any] = {
        "template": template,
        "points": points,
        "best": _best(points),
        "grid_size": grid_size,
        "engine_backend": backend,
        "sampling": {
            "mode": sweep_mode,
            "requested": requested,
            "returned": len(points),
            "seed": int(seed),
        },
    }
    heatmap = _heatmap(param_grid, points, metric="sharpe")
    if heatmap is not None:
        payload["heatmap"] = heatmap
    return payload


def _run_grid(
    panel: PanelData,
    template: str,
    param_grid: dict[str, list[Any]],
    config: BacktestConfig,
    workers: int,
) -> tuple[list[dict[str, Any]], str]:
    spec = StrategySpec(name=template, template=template)
    result = run_sweep(panel, spec, param_grid, config, max_workers=workers)
    points = [
        {"params": point.params, "metrics": point.metrics, "error": point.error}
        for point in result.points
    ]
    return points, result.engine_backend


def _run_combinations(
    panel: PanelData,
    template: str,
    combinations: list[dict[str, Any]],
    config: BacktestConfig,
    workers: int,
) -> tuple[list[dict[str, Any]], str]:
    """Run an arbitrary (sampled) set of parameter combinations with a stable order."""
    snapshot_meta = {
        "synthetic": bool(panel.meta.get("synthetic", False)),
        "source": panel.meta.get("source", "unknown"),
        "label": "sweep-random",
    }

    def run_one(params: dict[str, Any]) -> dict[str, Any]:
        try:
            spec = StrategySpec(name=template, template=template, params=dict(params))
            strategy = spec.load()
            weights = strategy.generate_targets(panel)
            result = run_backtest(
                panel,
                weights,
                config,
                strategy_metadata=strategy.metadata(),
                snapshot_metadata=snapshot_meta,
            )
            return {
                "params": dict(params),
                "metrics": dict(result.metrics),
                "error": None,
                "backend": result.engine_backend,
            }
        except Exception as exc:  # one bad combination must not break the sample
            return {
                "params": dict(params),
                "metrics": {},
                "error": f"{type(exc).__name__}: {exc}",
                "backend": None,
            }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(run_one, combinations))
    backends = [str(row.pop("backend")) for row in rows if row.get("backend")]
    backend = backends[0] if backends else "cpp"
    return rows, backend


def _best(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [point for point in points if point.get("metrics")]
    if not valid:
        return None

    def _sharpe(point: dict[str, Any]) -> float:
        value = (point.get("metrics") or {}).get("sharpe", float("-inf"))
        try:
            return float(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return float("-inf")

    best = max(valid, key=_sharpe)
    return {"params": best["params"], "metrics": best["metrics"], "metric": "sharpe"}


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


__all__ = ["MAX_RANDOM_GRID", "MAX_SWEEP_POINTS", "run_api_sweep"]
