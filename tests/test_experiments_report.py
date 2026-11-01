"""Experiments, replay, HTML report and provenance tests (C++ engine required)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import quantcore
from quantcore.backtest.config import BacktestConfig
from quantcore.data.synthetic import generate_quick_panel
from quantcore.errors import ExperimentError
from quantcore.experiments import ExperimentStore, replay_experiment, run_experiment
from quantcore.report import render_html_report
from quantcore.strategy.spec import StrategySpec

pytestmark = pytest.mark.skipif(
    not quantcore.engine_available(), reason="C++ backtest engine is unavailable"
)


def _spec(template: str = "momentum", **params) -> StrategySpec:
    return StrategySpec(name=f"{template}_test", template=template, params=params)


def test_run_experiment_with_snapshot(synthetic_snapshot, tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    spec = _spec("momentum", top_n=5, lookback=60)
    record = run_experiment(
        store,
        spec,
        snapshot=synthetic_snapshot,
        config=BacktestConfig(initial_cash=1_000_000.0),
        report=True,
    )
    metadata = record.metadata
    assert metadata["engine_backend"] == "cpp"
    assert metadata["engine_version"]
    assert metadata["seed"] == 42
    assert metadata["snapshot"]["snapshot_id"] == synthetic_snapshot.snapshot_id
    assert metadata["strategy_hash"]
    assert metadata["environment"]["python"]
    assert metadata["synthetic"] is True
    assert (record.directory / "result" / "equity.parquet").exists()
    assert (record.directory / "result" / "trades.parquet").exists()
    assert (record.directory / "strategy.yaml").exists()
    report_path = record.directory / "report.html"
    assert report_path.exists()
    html = report_path.read_text(encoding="utf-8")
    assert "SYNTHETIC" in html
    assert "Historical performance does not guarantee future results" in html
    assert "<svg" in html
    result = store.load_result(record.run_id)
    assert result.engine_backend == "cpp"
    assert len(result.equity) == synthetic_snapshot.manifest.metadata["n_time"]
    assert isinstance(result.metrics, dict) and "total_return" in result.metrics


def test_experiments_list_and_get(synthetic_snapshot, tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    spec = _spec("low_vol", top_n=4)
    first = run_experiment(store, spec, snapshot=synthetic_snapshot)
    second = run_experiment(store, spec, snapshot=synthetic_snapshot)
    assert first.run_id != second.run_id
    listed = store.list(kind="backtest")
    assert {record.run_id for record in listed} >= {first.run_id, second.run_id}
    assert store.get(first.run_id).metadata["strategy_name"] == spec.name
    with pytest.raises(ExperimentError):
        store.get("does_not_exist")


def test_replay_is_bit_for_bit(synthetic_snapshot, tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    record = run_experiment(store, _spec("multi_factor", top_n=5), snapshot=synthetic_snapshot)
    first = store.load_result(record.run_id)
    replay = replay_experiment(store, record.run_id)
    assert replay.matched is True
    assert replay.equity_match and replay.trades_match and replay.metrics_match
    assert replay.differences == []
    fresh = store.load_result(record.run_id)
    assert np.array_equal(first.equity, fresh.equity)


def test_run_experiment_without_snapshot_can_replay(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    panel = generate_quick_panel(n_sec=20, seed=3)
    spec = _spec("buy_and_hold")
    record = run_experiment(store, spec, panel=panel)
    assert record.metadata["snapshot"]["snapshot_id"] is None
    replay = replay_experiment(store, record.run_id)
    assert replay.matched is True
    # Missing persisted panel data must fail loudly instead of silently re-generating.
    panel_dir = record.directory / "panel"
    for path in panel_dir.glob("*.parquet"):
        path.unlink()
    with pytest.raises(ExperimentError):
        replay_experiment(store, record.run_id)


def test_html_report_standalone(synthetic_snapshot, tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    record = run_experiment(store, _spec("dual_ma"), snapshot=synthetic_snapshot)
    result = store.load_result(record.run_id)
    path = render_html_report(
        result,
        output_path=tmp_path / "report.html",
        strategy_metadata=record.metadata["strategy"],
        snapshot_metadata=record.metadata["snapshot"],
    )
    html = path.read_text(encoding="utf-8")
    assert "QuantCore backtest report" in html
    assert "engine_backend" in html
    assert "no CDN" not in html
    payload = json.loads((record.directory / "summary.json").read_text(encoding="utf-8"))
    assert payload["engine_backend"] == "cpp"
