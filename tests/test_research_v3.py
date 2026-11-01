"""M7 robustness API tests: overfitting, PBO, cost sensitivity, Monte Carlo, capacity."""

from __future__ import annotations

from typing import Any

import pytest

import quantcore
from quantcore.experiments import ExperimentStore, run_experiment
from quantcore.strategy.spec import StrategySpec

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def runs(synthetic_snapshot: Any, experiments_root: Any) -> list[Any]:
    """Three real persisted experiments sharing one snapshot (aligned trading calendar)."""
    store = ExperimentStore(experiments_root)
    specs = [
        StrategySpec(name="v3_mom3", template="momentum", params={"top_n": 3, "lookback": 60}),
        StrategySpec(name="v3_mom5", template="momentum", params={"top_n": 5, "lookback": 120}),
        StrategySpec(name="v3_dual", template="dual_ma"),
    ]
    return [run_experiment(store, spec, snapshot=synthetic_snapshot) for spec in specs]


def test_overfitting_contract(api_client: Any, runs: list[Any]) -> None:
    run_id = runs[0].run_id
    response = api_client.post("/api/research/overfitting", json={"run_id": run_id})
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in (
        "run_id",
        "observations",
        "periods_per_year",
        "sharpe",
        "deflated_sharpe",
        "expected_max_sharpe",
        "n_trials",
        "skew",
        "kurtosis",
        "verdict",
    ):
        assert key in payload, key
    assert payload["run_id"] == run_id
    assert payload["observations"] > 100
    assert payload["periods_per_year"] >= 200
    assert 0.0 <= payload["deflated_sharpe"] <= 1.0
    assert payload["expected_max_sharpe"] == 0.0
    assert payload["verdict"] in {"robust", "inconclusive", "likely_overfit"}
    assert isinstance(payload["skew"], float) and isinstance(payload["kurtosis"], float)

    many = api_client.post(
        "/api/research/overfitting", json={"run_id": run_id, "n_trials": 10}
    ).json()
    assert many["n_trials"] == 10
    assert many["expected_max_sharpe"] > 0.0
    assert many["deflated_sharpe"] <= payload["deflated_sharpe"] + 1e-9

    assert (
        api_client.post("/api/research/overfitting", json={"run_id": "does-not-exist"}).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/research/overfitting", json={"run_id": run_id, "n_trials": 0}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/research/overfitting",
            json={"run_id": run_id},
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code
        == 401
    )


def test_pbo_contract(api_client: Any, runs: list[Any]) -> None:
    run_ids = [record.run_id for record in runs]
    response = api_client.post("/api/research/pbo", json={"run_ids": run_ids, "n_splits": 4})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_ids"] == run_ids
    assert payload["n_splits"] == 4
    assert payload["combinations"] == 6
    assert 0.0 <= payload["pbo"] <= 1.0
    assert 1.0 <= payload["median_oos_rank"] <= len(run_ids)
    logits = payload["logits"]
    assert len(logits) == payload["combinations"]
    assert all(len(row) == len(run_ids) for row in logits)
    assert all(-20 < value < 20 for row in logits for value in row)

    again = api_client.post("/api/research/pbo", json={"run_ids": run_ids, "n_splits": 4}).json()
    assert again["pbo"] == payload["pbo"]
    assert again["median_oos_rank"] == payload["median_oos_rank"]
    assert again["logits"] == logits

    default_splits = api_client.post("/api/research/pbo", json={"run_ids": run_ids[:2]}).json()
    assert default_splits["n_splits"] == 8
    assert default_splits["combinations"] == 70
    assert len(default_splits["logits"]) == 70

    assert api_client.post("/api/research/pbo", json={"run_ids": [run_ids[0]]}).status_code == 400
    assert (
        api_client.post(
            "/api/research/pbo", json={"run_ids": [run_ids[0], "missing-run"]}
        ).status_code
        == 400
    )
    assert (
        api_client.post("/api/research/pbo", json={"run_ids": run_ids, "n_splits": 3}).status_code
        == 422
    )
    assert (
        api_client.post("/api/research/pbo", json={"run_ids": run_ids, "n_splits": 0}).status_code
        == 422
    )


def test_cost_sensitivity_contract(api_client: Any, runs: list[Any], experiments_root: Any) -> None:
    run_id = runs[0].run_id
    store = ExperimentStore(experiments_root)
    before = store.load_result(run_id).equity.copy()

    response = api_client.post("/api/research/cost_sensitivity", json={"run_id": run_id})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == run_id
    assert "breakeven_multiplier" in payload
    points = payload["points"]
    assert [point["multiplier"] for point in points] == [0.0, 0.5, 1.0, 2.0, 3.0]
    for point in points:
        for key in (
            "multiplier",
            "total_return",
            "annualized_return",
            "sharpe",
            "max_drawdown",
            "total_fees",
        ):
            assert key in point, key
    assert points[0]["total_fees"] == 0
    assert points[-1]["total_fees"] > 0
    assert points[0]["total_return"] >= points[-1]["total_return"] - 1e-9

    after = store.load_result(run_id).equity
    assert (before == after).all(), "cost sensitivity must not modify the original experiment"

    custom = api_client.post(
        "/api/research/cost_sensitivity",
        json={"run_id": run_id, "multipliers": [0.0, 1.0]},
    ).json()
    assert [point["multiplier"] for point in custom["points"]] == [0.0, 1.0]

    assert (
        api_client.post(
            "/api/research/cost_sensitivity", json={"run_id": "does-not-exist"}
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/research/cost_sensitivity", json={"run_id": run_id, "multipliers": [-1]}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/research/cost_sensitivity", json={"run_id": run_id, "multipliers": []}
        ).status_code
        == 422
    )


def test_monte_carlo_contract_and_determinism(api_client: Any, runs: list[Any]) -> None:
    run_id = runs[0].run_id
    body = {"run_id": run_id, "n_paths": 120, "horizon": 40}
    response = api_client.post("/api/research/monte_carlo", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == run_id
    assert payload["n_paths"] == 120 and payload["horizon"] == 40
    terminal = payload["terminal_return"]
    drawdown = payload["max_drawdown"]
    assert set(terminal) == {"p05", "p25", "p50", "p75", "p95"}
    assert set(drawdown) == {"p05", "p50", "p95"}
    assert (
        terminal["p05"] <= terminal["p25"] <= terminal["p50"] <= terminal["p75"] <= terminal["p95"]
    )
    assert 0.0 <= drawdown["p05"] <= drawdown["p50"] <= drawdown["p95"] <= 1.0
    paths = payload["paths"]
    assert len(paths) == 50  # capped at 50 sampled paths for the UI
    assert all(len(path) == 41 for path in paths)
    assert all(path[0] == 0.0 for path in paths)

    again = api_client.post("/api/research/monte_carlo", json=body).json()
    assert again["terminal_return"] == terminal
    assert again["max_drawdown"] == drawdown

    assert (
        api_client.post(
            "/api/research/monte_carlo",
            json={"run_id": run_id, "n_paths": 0},
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/research/monte_carlo",
            json={"run_id": run_id, "horizon": 0},
        ).status_code
        == 422
    )
    assert (
        api_client.post("/api/research/monte_carlo", json={"run_id": "does-not-exist"}).status_code
        == 400
    )


def test_capacity_contract(api_client: Any, runs: list[Any]) -> None:
    run_id = runs[0].run_id
    response = api_client.post(
        "/api/research/capacity", json={"run_id": run_id, "adv_participation": 0.2}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == run_id
    assert payload["participation"] == 0.2
    assert payload["capacity_cny"] > 0
    assert payload["avg_adv_cny"] > 0
    assert payload["avg_turnover"] > 0
    assert isinstance(payload["limiting_sec"], str) and payload["limiting_sec"]
    assert "approximate" in payload["notes"].lower()

    again = api_client.post(
        "/api/research/capacity", json={"run_id": run_id, "adv_participation": 0.2}
    ).json()
    assert again["capacity_cny"] == payload["capacity_cny"]
    assert again["limiting_sec"] == payload["limiting_sec"]

    assert (
        api_client.post("/api/research/capacity", json={"run_id": "does-not-exist"}).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/research/capacity", json={"run_id": run_id, "adv_participation": 0}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/research/capacity", json={"run_id": run_id, "adv_participation": 1.5}
        ).status_code
        == 422
    )
