"""CLI end-to-end tests: data -> snapshot -> backtest -> replay -> checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quantcore
from quantcore.cli import app, main

runner = CliRunner()


def _run(*args: str, exit_code: int = 0):
    result = runner.invoke(app, list(args))
    assert result.exit_code == exit_code, (result.output, result.exception)
    return result


def _json(result) -> dict:
    return json.loads(result.stdout)


def test_version_command() -> None:
    payload = _json(_run("version"))
    assert payload["quantcore"] == quantcore.__version__
    assert payload["engine_backend"] == "cpp"
    assert payload["engine_available"] is True


def test_help_and_unknown_command() -> None:
    assert main(["--help"]) == 0
    assert main(["definitely-not-a-command"]) == 2
    missing_required = runner.invoke(app, ["sweep", "run"])
    assert missing_required.exit_code != 0


def test_data_update_and_status(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    update = _json(
        _run(
            "data",
            "update",
            "--provider",
            "synthetic",
            "--data-root",
            str(data_root),
            "--start",
            "2023-01-03",
            "--end",
            "2023-12-29",
            "--n-sec",
            "12",
        )
    )
    assert update["quality_passed"] is True
    assert update["datasets"]["bars"] > 0
    assert update["synthetic"] is True
    status = _json(_run("data", "status", "--data-root", str(data_root)))
    assert status["manifest_hash"] == update["manifest_hash"]
    assert "bars" in status["datasets"]
    quality = _json(_run("check", "data", "--data-root", str(data_root)))
    assert quality["passed"] is True


@pytest.mark.skipif(not quantcore.panel_available(), reason="C++ .qpanel unavailable")
def test_snapshot_commands(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    snapshots_root = tmp_path / "snapshots"
    _run(
        "data",
        "update",
        "--data-root",
        str(data_root),
        "--start",
        "2023-01-03",
        "--end",
        "2023-12-29",
        "--n-sec",
        "10",
    )
    built = _json(
        _run(
            "snapshot",
            "build",
            "--data-root",
            str(data_root),
            "--snapshots-root",
            str(snapshots_root),
        )
    )
    assert built["snapshot_id"].startswith("snap_")
    assert built["qpanel"]["available"] is True
    assert Path(built["path"]).is_dir()
    listed = _json(_run("snapshot", "list", "--snapshots-root", str(snapshots_root)))
    assert listed["count"] == 1
    verified = _json(
        _run(
            "snapshot",
            "verify",
            built["snapshot_id"],
            "--snapshots-root",
            str(snapshots_root),
        )
    )
    assert verified["problems"] == []


@pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")
def test_backtest_run_replay_and_list(tmp_path: Path) -> None:
    experiments = tmp_path / "experiments"
    payload = _json(
        _run(
            "backtest",
            "run",
            "--template",
            "momentum",
            "--params",
            '{"top_n": 5, "lookback": 60}',
            "--n-sec",
            "25",
            "--experiments-root",
            str(experiments),
        )
    )
    assert payload["engine_backend"] == "cpp"
    assert payload["trade_count"] >= 0
    assert "metrics" in payload and "total_return" in payload["metrics"]
    assert payload["synthetic"] is True
    assert Path(payload["report"]).exists()
    run_id = payload["run_id"]
    listed = _json(_run("backtest", "list", "--experiments-root", str(experiments)))
    assert listed["experiments"][0]["run_id"] == run_id
    replay = _json(_run("replay", run_id, "--experiments-root", str(experiments)))
    assert replay["matched"] is True


@pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")
def test_check_lookahead_command() -> None:
    payload = _json(_run("check", "lookahead", "--template", "momentum", "--n-sec", "25"))
    assert payload["passed"] is True
    assert payload["engine_backend"] == "cpp"
    assert payload["cuts"]


@pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")
def test_sweep_command(tmp_path: Path) -> None:
    payload = _json(
        _run(
            "sweep",
            "run",
            "--template",
            "momentum",
            "--grid",
            '{"top_n": [2, 4]}',
            "--n-sec",
            "25",
            "--workers",
            "2",
            "--experiments-root",
            str(tmp_path / "experiments"),
        )
    )
    assert payload["engine_backend"] == "cpp"
    assert payload["points"] == 2
    assert payload["failures"] == 0
    assert Path(payload["table"]).exists()


def test_bench_command() -> None:
    payload = _json(_run("bench", "--n-sec", "12"))
    assert payload["engine_backend"] == "cpp"
    assert "qpanel_write_ms" in payload
    assert payload["checks"]["engine_run_under_1000ms"] is True


def test_serve_documents_security_and_ui_options() -> None:
    import inspect

    from quantcore.cli_serve import serve_command

    parameters = inspect.signature(serve_command).parameters
    for option in ("token", "ui_dir", "open_browser", "port", "data_root", "start_worker"):
        assert option in parameters, option
