"""M4-011 C++ parallel engine batch path used by parameter sweep."""

from __future__ import annotations

import numpy as np

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.engine import run_backtest, run_backtest_batch
from quantcore.backtest.sweep import run_sweep
from quantcore.strategy.spec import StrategySpec


def test_batch_matches_sequential(small_panel) -> None:
    weights = []
    for fraction in (0.2, 0.5):
        matrix = np.full((small_panel.n_time, small_panel.n_sec), np.nan)
        matrix[::20] = fraction / 3
        weights.append(matrix)
    batch = run_backtest_batch(small_panel, weights, BacktestConfig(), threads=2)
    sequential = [run_backtest(small_panel, matrix, BacktestConfig()) for matrix in weights]
    assert len(batch) == 2
    for left, right in zip(batch, sequential, strict=True):
        assert left.engine_backend == "cpp"
        assert left.metrics["total_return"] == right.metrics["total_return"]
        assert left.metrics["sharpe"] == right.metrics["sharpe"]


def test_sweep_cpp_parallel_matches_sequential(small_panel) -> None:
    spec = StrategySpec(name="momentum", template="momentum")
    grid = {"top_n": [3, 5], "lookback": [20]}
    parallel = run_sweep(
        small_panel, spec, grid, BacktestConfig(), max_workers=2, cpp_parallel=True
    )
    sequential = run_sweep(small_panel, spec, grid, BacktestConfig(), max_workers=1)
    assert len(parallel.points) == len(sequential.points) == 2
    for left, right in zip(parallel.points, sequential.points, strict=True):
        assert left.error is None and right.error is None
        assert left.metrics["total_return"] == right.metrics["total_return"]
