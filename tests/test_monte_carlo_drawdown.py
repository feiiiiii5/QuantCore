"""Monte Carlo drawdown includes losses from the initial unit of capital."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.result import BacktestResult
from quantcore.experiments import ExperimentStore
from quantcore.research.robustness import compute_monte_carlo


def test_one_day_loss_counts_as_drawdown_from_initial_capital(tmp_path: Path) -> None:
    config = BacktestConfig().to_dict()
    equity = np.rint(config["initial_cash"] * 10000 * 0.99 ** np.arange(41)).astype(np.int64)
    dates = np.array(pd.bdate_range("2024-01-02", periods=41).strftime("%Y%m%d"), dtype=np.int64)
    store = ExperimentStore(tmp_path / "experiments")
    run_id = store.create("backtest", {"config": config, "synthetic": True})
    store.save_result(
        run_id,
        BacktestResult(
            dates=dates,
            equity=equity,
            cash=equity.copy(),
            market_value=np.zeros_like(equity),
            trades=pd.DataFrame(),
            metrics={},
            reasons={},
            engine_backend="fixture",
            engine_version="SYNTHETIC",
            seed=9,
            config=config,
        ),
    )

    result = compute_monte_carlo(store, run_id, n_paths=8, horizon=1, seed=9)

    assert all(value == pytest.approx(-0.01) for value in result["terminal_return"].values())
    assert result["max_drawdown"] == pytest.approx({"p05": 0.01, "p50": 0.01, "p95": 0.01})
