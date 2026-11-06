"""A new research run must reuse recorded inputs rather than regenerate lookalike data."""

from pathlib import Path

import numpy as np
import pytest

from quantcore.experiments import ExperimentStore, run_experiment
from quantcore.server.runner import run_backtest_job
from quantcore.server.schemas import BacktestRequest
from quantcore.strategy.spec import StrategySpec


@pytest.mark.parametrize("use_snapshot", [False, True])
def test_source_run_reuses_data_config_and_preserves_original(
    tmp_path: Path, synthetic_snapshot, small_panel, use_snapshot: bool
) -> None:
    from quantcore.backtest.config import BacktestConfig

    store = ExperimentStore(tmp_path / "experiments")
    config = BacktestConfig.model_validate(
        {
            "initial_cash": 250_000,
            "annual_days": 250,
            "exec": {"slippage_bps": 7},
            "costs": {"min_commission": 9},
        }
    )
    source = run_experiment(
        store,
        StrategySpec(
            name="recorded", template="buy_and_hold", rebalance="monthly", universe={"min_price": 3}
        ),
        snapshot=synthetic_snapshot if use_snapshot else None,
        panel=None if use_snapshot else small_panel,
        config=config,
    )
    original = (source.directory / "metadata.json").read_bytes()
    copied = run_backtest_job({"source_run_id": source.run_id, "experiments_root": str(store.root)})
    record = store.get(copied["run_id"])
    assert record.metadata["parent_run_id"] == source.run_id
    assert record.metadata["config"] == source.metadata["config"]
    assert (
        record.metadata["snapshot"]["content_hash"] == source.metadata["snapshot"]["content_hash"]
    )
    assert np.array_equal(
        store.load_result(source.run_id).equity, store.load_result(record.run_id).equity
    )

    changed = run_backtest_job(
        {
            "source_run_id": source.run_id,
            "experiments_root": str(store.root),
            "template": "buy_and_hold",
            "params": {"rebalance": "weekly"},
            "config": {"costs": {"min_commission": 0}},
        }
    )
    child = store.get(changed["run_id"])
    assert child.metadata["config"]["costs"]["min_commission"] == 0
    assert child.metadata["config"]["exec"]["slippage_bps"] == 7
    assert child.metadata["config"]["annual_days"] == 250
    assert child.metadata["strategy"]["universe"]["min_price"] == 3
    assert (
        StrategySpec.model_validate(child.metadata["strategy"]).resolved_params()[1]["rebalance"]
        == "weekly"
    )
    assert child.metadata["snapshot"]["content_hash"] == source.metadata["snapshot"]["content_hash"]
    assert (source.directory / "metadata.json").read_bytes() == original


def test_source_request_cannot_silently_switch_data() -> None:
    from pydantic import ValidationError

    assert BacktestRequest(source_run_id="recorded").source_run_id == "recorded"
    with pytest.raises(ValidationError, match="reuses recorded data"):
        BacktestRequest(source_run_id="recorded", snapshot="other")


def test_source_validation_uses_custom_experiment_root(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from quantcore.server import create_app

    store = ExperimentStore(tmp_path / "custom")
    source = store.create("backtest", {}, run_id="recorded")
    app = create_app(
        token="test-token",
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        experiments_root=tmp_path / "default",
        start_worker=False,
    )
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer test-token"}
    ) as client:
        response = client.post(
            "/api/backtest", json={"source_run_id": source, "experiments_root": str(store.root)}
        )
        assert response.status_code == 202
        assert app.state.jobs.status(response.json()["job_id"])["status"] == "pending"
