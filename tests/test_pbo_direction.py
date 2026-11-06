"""PBO must count out-of-sample failures, rather than persistent winners."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.result import BacktestResult
from quantcore.experiments import ExperimentStore
from quantcore.research.robustness import compute_pbo
from quantcore.server import create_app


def _save_synthetic_result(store: ExperimentStore, run_id: str, returns: np.ndarray) -> None:
    """Persist controlled SYNTHETIC equity via the production experiment format."""
    config = BacktestConfig().to_dict()
    equity = np.rint(config["initial_cash"] * 10000 * np.cumprod(np.r_[1.0, 1.0 + returns])).astype(
        np.int64
    )
    dates = np.array(
        pd.bdate_range("2024-01-02", periods=len(equity)).strftime("%Y%m%d"), dtype=np.int64
    )
    store.create(
        "backtest", {"config": config, "synthetic": True, "status": "completed"}, run_id=run_id
    )
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
            seed=42,
            config=config,
            snapshot={"synthetic": True, "source": "SYNTHETIC"},
        ),
    )


@pytest.mark.parametrize(
    "scenario,expected_pbo,expected_rank",
    [("persistent", 0.0, 1.0), ("reverses", 1.0, 2.0), ("tied", 1.0, 1.0)],
)
def test_pbo_distinguishes_persistent_winners_from_oos_failures(
    tmp_path: Path, scenario: str, expected_pbo: float, expected_rank: float
) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    high = np.tile([0.002, 0.001], 20)
    low = np.tile([0.0002, -0.0001], 20)
    first = np.r_[high[:20], low[20:]] if scenario == "reverses" else high
    second = np.r_[low[:20], high[20:]] if scenario == "reverses" else low
    if scenario == "tied":
        first = second = np.zeros(40)
    _save_synthetic_result(store, "first", first)
    _save_synthetic_result(store, "second", second)

    result = compute_pbo(store, ["first", "second"], n_splits=2)
    app = create_app(
        token="pbo-direction-test",
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        experiments_root=store.root,
        start_worker=False,
        serve_ui=False,
    )
    with TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer pbo-direction-test"},
    ) as client:
        response = client.post(
            "/api/research/pbo", json={"run_ids": ["first", "second"], "n_splits": 2}
        )
    assert response.status_code == 200
    assert response.json() == result
    assert result["pbo"] == expected_pbo
    assert result["median_oos_rank"] == expected_rank  # The public rank remains 1 = best.
    assert result["combinations"] == 2
    if scenario == "tied":
        assert result["logits"] == [[0.0, 0.0], [0.0, 0.0]]
