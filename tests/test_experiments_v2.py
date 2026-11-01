"""Experiments API v2 tests: list/detail/result/replay/report/export/compare/delete."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

import quantcore

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")


@pytest.fixture(scope="session")
def other_experiment(synthetic_snapshot: object, experiments_root: Path) -> object:
    from quantcore.experiments import ExperimentStore, run_experiment
    from quantcore.strategy.spec import StrategySpec

    spec = StrategySpec(name="api_dual_ma", template="dual_ma")
    return run_experiment(
        ExperimentStore(experiments_root), spec, snapshot=synthetic_snapshot, report=True
    )


def test_experiment_list_and_detail(api_client: object, seeded_experiment: object) -> None:
    listed = api_client.get("/api/experiments").json()
    assert isinstance(listed, list) and listed
    entry = next(row for row in listed if row["run_id"] == seeded_experiment.run_id)
    for key in (
        "run_id",
        "created_at",
        "status",
        "kind",
        "strategy_name",
        "template",
        "snapshot_id",
        "metrics",
    ):
        assert key in entry, key
    assert entry["template"] == "momentum"

    detail = api_client.get(f"/api/experiments/{seeded_experiment.run_id}").json()
    assert detail["run_id"] == seeded_experiment.run_id
    assert "metadata" in detail and "summary" in detail and "metrics" in detail
    assert detail["result"]["equity"]
    assert detail["metadata"]["synthetic"] is True

    filtered = api_client.get("/api/experiments", params={"kind": "backtest"}).json()
    assert any(row["run_id"] == seeded_experiment.run_id for row in filtered)
    assert api_client.get("/api/experiments/nope").status_code == 404


def test_experiment_result_arrays(api_client: object, seeded_experiment: object) -> None:
    payload = api_client.get(f"/api/experiments/{seeded_experiment.run_id}/result").json()
    for key in ("dates", "equity", "cash", "market_value", "trades", "metrics", "reasons"):
        assert key in payload, key
    assert len(payload["dates"]) == len(payload["equity"]) == len(payload["cash"]) > 0
    assert payload["equity"][0] == pytest.approx(1_000_000.0, rel=0.01)
    assert payload["cash"][0] == pytest.approx(1_000_000.0, rel=0.01)
    assert payload["metrics"]["trading_days"] == len(payload["dates"])
    assert payload["engine_backend"] == "cpp"
    assert isinstance(payload["trades"], list)
    assert api_client.get("/api/experiments/nope/result").status_code == 404


def test_replay_contract(api_client: object, seeded_experiment: object) -> None:
    response = api_client.post(f"/api/experiments/{seeded_experiment.run_id}/replay")
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "run_id",
        "matched",
        "equity_matched",
        "trades_matched",
        "metrics_matched",
        "diffs",
    ):
        assert key in payload, key
    assert payload["matched"] is True
    assert payload["diffs"] == []
    assert payload["differences"] == payload["diffs"]
    alias = api_client.post("/api/backtest/replay", json={"run_id": seeded_experiment.run_id})
    assert alias.status_code == 200
    assert alias.json()["matched"] is True
    assert alias.json()["equity_matched"] is True
    assert api_client.post("/api/backtest/replay", json={"run_id": "nope"}).status_code == 404
    assert api_client.post("/api/experiments/nope/replay").status_code == 404


def test_report_and_export(api_client: object, seeded_experiment: object) -> None:
    report = api_client.get(f"/api/experiments/{seeded_experiment.run_id}/report")
    assert report.status_code == 200
    assert "text/html" in report.headers["content-type"]
    assert "<html" in report.text.lower()

    export = api_client.get(f"/api/experiments/{seeded_experiment.run_id}/export")
    assert export.status_code == 200
    assert export.content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        names = set(archive.namelist())
    assert "metadata.json" in names
    assert any(name.startswith("result/") for name in names)

    assert api_client.get("/api/experiments/nope/report").status_code == 404
    assert api_client.get("/api/experiments/nope/export").status_code == 404


def test_compare_experiments(
    api_client: object, seeded_experiment: object, other_experiment: object
) -> None:
    ids = f"{seeded_experiment.run_id},{other_experiment.run_id}"
    response = api_client.get("/api/experiments/compare", params={"ids": ids})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["ids"]) == {seeded_experiment.run_id, other_experiment.run_id}
    assert set(payload["metrics"]) == {seeded_experiment.run_id, other_experiment.run_id}
    assert len(payload["equity"]) == 2
    for series in payload["equity"]:
        assert len(series["dates"]) == len(series["equity"]) > 0

    assert (
        api_client.get(
            "/api/experiments/compare", params={"ids": seeded_experiment.run_id}
        ).status_code
        == 400
    )
    assert (
        api_client.get(
            "/api/experiments/compare",
            params={"ids": f"{seeded_experiment.run_id},does-not-exist"},
        ).status_code
        == 404
    )


def test_delete_experiment(
    api_client: object, synthetic_snapshot: object, experiments_root: Path
) -> None:
    from quantcore.experiments import ExperimentStore, run_experiment
    from quantcore.strategy.spec import StrategySpec

    spec = StrategySpec(name="api_discard", template="buy_and_hold")
    record = run_experiment(
        ExperimentStore(experiments_root), spec, snapshot=synthetic_snapshot, report=True
    )
    assert api_client.get(f"/api/experiments/{record.run_id}").status_code == 200
    deleted = api_client.delete(f"/api/experiments/{record.run_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert api_client.get(f"/api/experiments/{record.run_id}").status_code == 404
    assert api_client.delete(f"/api/experiments/{record.run_id}").status_code == 404


def test_experiment_metadata_json_is_valid(seeded_experiment: object) -> None:
    payload = json.loads((seeded_experiment.directory / "metadata.json").read_text("utf-8"))
    assert payload["engine_backend"] == "cpp"
    assert payload["snapshot"]["snapshot_id"]
