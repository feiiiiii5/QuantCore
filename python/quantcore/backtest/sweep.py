"""Deterministic parameter sweeps over the C++ engine.

The Python layer expands the grid and dispatches engine runs; the heavy market-data and
execution work always goes through the C++ engine.  A C++-parallel sweep entry point can
be bound later without changing this API (see ``QC-SWEEP-TODO``).
"""

from __future__ import annotations

import itertools
import traceback
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.panel import PanelData
from ..errors import BacktestError
from ..snapshot.reader import Snapshot
from ..strategy.spec import StrategySpec
from .config import BacktestConfig
from .engine import run_backtest, run_backtest_batch
from .result import BacktestResult


def expand_grid(grid: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Expand a parameter grid deterministically (keys sorted, values in given order)."""
    if not grid:
        return [{}]
    keys = sorted(grid)
    values = [list(grid[key]) for key in keys]
    if any(len(items) == 0 for items in values):
        raise ValueError("parameter grid contains an empty value list")
    return [dict(zip(keys, combination, strict=True)) for combination in itertools.product(*values)]


@dataclass
class SweepPoint:
    index: int
    params: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    result: BacktestResult | None = None

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {f"param_{key}": value for key, value in self.params.items()}
        row["index"] = self.index
        if self.error is not None:
            row["error"] = self.error
        else:
            for key, value in self.metrics.items():
                row[key] = value
        return row


@dataclass
class SweepResult:
    points: list[SweepPoint]
    table: pd.DataFrame
    engine_backend: str = "cpp"

    @property
    def failures(self) -> list[SweepPoint]:
        return [point for point in self.points if point.error is not None]

    def to_parquet(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.table.to_parquet(target, index=False)
        return target

    def best(self, metric: str = "sharpe", *, ascending: bool = False) -> SweepPoint | None:
        valid = [point for point in self.points if point.error is None and metric in point.metrics]
        if not valid:
            return None
        return sorted(valid, key=lambda point: float(point.metrics[metric]), reverse=not ascending)[
            0
        ]


def _strategy_from_spec(
    spec: StrategySpec, params: dict[str, Any], base_dir: str | Path | None
) -> Any:
    payload = spec.model_dump(mode="python")
    payload["params"] = {**spec.params, **params}
    point_spec = StrategySpec.model_validate(payload)
    return point_spec.load(base_dir)


def _run_point(
    index: int,
    params: dict[str, Any],
    spec: StrategySpec,
    panel: PanelData,
    config: BacktestConfig,
    base_dir: str | Path | None,
    keep_results: bool,
) -> SweepPoint:
    point = SweepPoint(index=index, params=params)
    try:
        strategy = _strategy_from_spec(spec, params, base_dir)
        weights = strategy.generate_targets(panel)
        result = run_backtest(
            panel,
            weights,
            config,
            strategy_metadata=strategy.metadata(),
            snapshot_metadata={"synthetic": bool(panel.meta.get("synthetic", False))},
        )
        point.metrics = {
            key: (float(value) if isinstance(value, (int, float)) else value)
            for key, value in result.metrics.items()
        }
        point.metrics["total_fees"] = float(result.metrics.get("total_fees", 0))
        if keep_results:
            point.result = result
    except Exception as exc:
        point.error = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, BacktestError):
            point.error += "\n" + traceback.format_exc(limit=1)
    return point


def run_sweep(
    panel: PanelData | Snapshot,
    spec: StrategySpec,
    grid: Mapping[str, Sequence[Any]],
    config: BacktestConfig | None = None,
    *,
    base_dir: str | Path | None = None,
    max_workers: int = 1,
    keep_results: bool = False,
    cpp_parallel: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> SweepResult:
    """Run one backtest per grid point through the C++ engine.

    ``max_workers > 1`` dispatches independent engine runs on a thread pool; the C++
    engine releases the GIL during ``run``.  Results are returned in grid order.
    """
    panel_data = panel.to_panel_data() if isinstance(panel, Snapshot) else panel
    combinations = expand_grid(grid)
    cfg = config or BacktestConfig()
    points: list[SweepPoint] = []
    if cpp_parallel and max_workers > 1 and combinations:
        points = _run_cpp_batch(
            combinations, spec, panel_data, cfg, base_dir, keep_results, max_workers, progress
        )
    elif max_workers <= 1:
        for index, params in enumerate(combinations):
            points.append(_run_point(index, params, spec, panel_data, cfg, base_dir, keep_results))
            if progress is not None:
                progress(index + 1, len(combinations))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _run_point,
                    index,
                    params,
                    spec,
                    panel_data,
                    cfg,
                    base_dir,
                    keep_results,
                )
                for index, params in enumerate(combinations)
            ]
            for done, future in enumerate(futures):
                points.append(future.result())
                if progress is not None:
                    progress(done + 1, len(combinations))
    table = pd.DataFrame([point.to_row() for point in points])
    if "index" in table.columns and len(table) > 1:
        table = table.sort_values("index").reset_index(drop=True)
    return SweepResult(points=points, table=table)


def _run_cpp_batch(
    combinations: list[dict[str, Any]],
    spec: StrategySpec,
    panel: PanelData,
    config: BacktestConfig,
    base_dir: str | Path | None,
    keep_results: bool,
    workers: int,
    progress: Callable[[int, int], None] | None,
) -> list[SweepPoint]:
    """Generate weights in Python, execute groups of runs through C++ ``parallel_sweep``."""
    points: list[SweepPoint] = []
    entries: list[tuple[int, dict[str, Any], Any]] = []
    for index, params in enumerate(combinations):
        point = SweepPoint(index=index, params=dict(params))
        points.append(point)
        try:
            strategy = _strategy_from_spec(spec, params, base_dir)
            entries.append((index, dict(params), strategy.generate_targets(panel)))
        except Exception as exc:
            point.error = f"{type(exc).__name__}: {exc}"
    chunk_size = max(1, int(workers))
    for start in range(0, len(entries), chunk_size):
        chunk = entries[start : start + chunk_size]
        try:
            results = run_backtest_batch(
                panel,
                [entry[2] for entry in chunk],
                config,
                threads=chunk_size,
                strategy_metadata=spec.specification(base_dir),
                snapshot_metadata={"synthetic": bool(panel.meta.get("synthetic", False))},
            )
        except Exception as exc:
            for index, _, _ in chunk:
                points[index].error = f"{type(exc).__name__}: {exc}"
            continue
        for (index, _, _), result in zip(chunk, results, strict=True):
            point = points[index]
            point.metrics = {
                key: (float(value) if isinstance(value, (int, float)) else value)
                for key, value in result.metrics.items()
            }
            point.metrics["total_fees"] = float(result.metrics.get("total_fees", 0))
            if keep_results:
                point.result = result
        if progress is not None:
            progress(min(start + chunk_size, len(combinations)), len(combinations))
    return points


def sweep_metric_columns(table: pd.DataFrame) -> list[str]:
    """Metric columns present in a sweep table (excluding parameters/errors)."""
    return [
        column
        for column in table.columns
        if not column.startswith("param_") and column not in {"index", "error"}
    ]


__all__ = [
    "SweepPoint",
    "SweepResult",
    "expand_grid",
    "run_sweep",
    "sweep_metric_columns",
]
