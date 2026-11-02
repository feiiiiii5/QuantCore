"""Tests for the one-command SYNTHETIC demo (qc demo / run_demo)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quantcore
from quantcore.cli import app
from quantcore.demo import DemoResult, run_demo
from quantcore.errors import DemoError

runner = CliRunner()

requires_engine = pytest.mark.skipif(
    not quantcore.engine_available(), reason="C++ backtest engine unavailable"
)

#: 137 synthetic trading days (the synthetic calendar subtracts fabricated holidays).
DEMO_OPTIONS: dict[str, object] = {
    "n_sec": 20,
    "start": "2023-01-03",
    "end": "2023-07-31",
    "seed": 7,
    "template": "dual_ma",
}
DEMO_RESULT_KEYS = {
    "snapshot_id",
    "run_id",
    "engine_backend",
    "metrics",
    "report",
    "data_root",
    "snapshots_root",
    "experiments_root",
    "steps",
    "warnings",
}
STEP_KEYS = {"name", "status", "seconds", "detail"}


@requires_engine
def test_run_demo_end_to_end(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    experiments_root = tmp_path / "experiments"
    result = run_demo(data_root=data_root, experiments_root=experiments_root, **DEMO_OPTIONS)

    assert isinstance(result, DemoResult)
    assert result.snapshot_id.startswith("snap_")
    assert result.run_id.startswith("backtest_")
    assert result.engine_backend == "cpp"
    assert result.metrics["trading_days"] > 0
    for key in ("total_return", "sharpe", "max_drawdown", "trade_count"):
        assert key in result.metrics, key

    # artefacts on disk
    assert (data_root / "warehouse" / "warehouse_manifest.json").is_file()
    assert Path(result.snapshots_root) == data_root / "snapshots"
    assert (Path(result.snapshots_root) / result.snapshot_id / "manifest.json").is_file()
    experiment_dir = experiments_root / result.run_id
    assert (experiment_dir / "metadata.json").is_file()
    assert (experiment_dir / "result" / "equity.parquet").is_file()
    assert (experiment_dir / "strategy.yaml").is_file()
    assert result.report is not None
    assert Path(result.report).is_file()
    assert Path(result.report) == experiment_dir / "report.html"

    payload = result.to_dict()
    assert set(payload) == DEMO_RESULT_KEYS
    assert json.loads(json.dumps(payload))["run_id"] == result.run_id
    assert [step["name"] for step in payload["steps"]] == [
        "preflight",
        "ingest",
        "snapshot",
        "experiment",
        "report",
    ]
    assert all(set(step) == STEP_KEYS for step in payload["steps"])
    assert all(step["status"] == "pass" for step in payload["steps"])
    assert all(step["seconds"] >= 0 for step in payload["steps"])
    assert any("SYNTHETIC" in warning for warning in payload["warnings"])


@requires_engine
def test_run_demo_is_repeatable(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    experiments_root = tmp_path / "experiments"
    first = run_demo(data_root=data_root, experiments_root=experiments_root, **DEMO_OPTIONS)
    second = run_demo(data_root=data_root, experiments_root=experiments_root, **DEMO_OPTIONS)
    assert second.snapshot_id == first.snapshot_id
    assert second.run_id != first.run_id
    assert second.report is not None and Path(second.report).is_file()


@requires_engine
def test_run_demo_defaults_stay_under_data_demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_demo(n_sec=20, start="2023-01-03", end="2023-07-31", seed=7)
    assert Path(result.data_root) == Path("data/demo")
    assert Path(result.snapshots_root) == Path("data/demo/snapshots")
    assert (tmp_path / "data" / "demo" / "warehouse" / "warehouse_manifest.json").is_file()
    assert (tmp_path / "data" / "demo" / "snapshots" / result.snapshot_id).is_dir()
    assert (tmp_path / "experiments" / result.run_id).is_dir()
    # the shared development warehouse must never be touched by the demo
    assert not (tmp_path / "data" / "warehouse").exists()


def test_run_demo_without_engine_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quantcore, "engine_backend", lambda: "missing")
    monkeypatch.setattr(quantcore, "engine_available", lambda: False)
    with pytest.raises(DemoError, match="make build"):
        run_demo(
            data_root=tmp_path / "data",
            experiments_root=tmp_path / "experiments",
            **DEMO_OPTIONS,
        )
    assert not (tmp_path / "data" / "warehouse").exists()


@requires_engine
def test_demo_cli_json_output(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "demo",
            "--n-sec",
            "20",
            "--start",
            "2023-01-03",
            "--end",
            "2023-07-31",
            "--seed",
            "7",
            "--template",
            "dual_ma",
            "--data-root",
            str(tmp_path / "data"),
            "--experiments-root",
            str(tmp_path / "experiments"),
            "--json-output",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert payload["engine_backend"] == "cpp"
    assert payload["steps"][0]["name"] == "preflight"
    assert (tmp_path / "experiments" / payload["run_id"] / "report.html").is_file()
    assert "uv run qc serve --port 8000 --open" in result.stderr


@requires_engine
def test_demo_cli_human_output(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "demo",
            "--n-sec",
            "20",
            "--start",
            "2023-01-03",
            "--end",
            "2023-07-31",
            "--data-root",
            str(tmp_path / "data"),
            "--experiments-root",
            str(tmp_path / "experiments"),
            "--no-json-output",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "QuantCore demo (SYNTHETIC" in result.stdout
    assert "snapshot: snap_" in result.stdout
    assert "metrics:" in result.stdout
    assert "next: uv run qc serve --port 8000 --open" in result.stdout


def test_demo_cli_rejects_invalid_dates(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "demo",
            "--n-sec",
            "20",
            "--start",
            "2023-07-31",
            "--end",
            "2023-01-03",
            "--data-root",
            str(tmp_path / "data"),
            "--experiments-root",
            str(tmp_path / "experiments"),
        ],
    )
    assert result.exit_code == 2
    assert "start" in result.output.lower()


def test_demo_cli_without_engine_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quantcore, "engine_backend", lambda: "missing")
    monkeypatch.setattr(quantcore, "engine_available", lambda: False)
    result = runner.invoke(
        app,
        [
            "demo",
            "--n-sec",
            "20",
            "--data-root",
            str(tmp_path / "data"),
            "--experiments-root",
            str(tmp_path / "experiments"),
        ],
    )
    assert result.exit_code == 1
    assert "make build" in result.output


def test_demo_cli_help_lists_options() -> None:
    import inspect

    from quantcore.demo import demo_command

    parameters = inspect.signature(demo_command).parameters
    for option in (
        "data_root",
        "experiments_root",
        "n_sec",
        "start",
        "end",
        "seed",
        "template",
        "json_output",
    ):
        assert option in parameters, option
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    for option in ("--data-root", "--n-sec", "--seed", "--template", "--json-output"):
        assert option in result.stdout, option
