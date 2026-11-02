"""Tests for the local environment doctor (qc doctor / run_doctor)."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quantcore
import quantcore.doctor as doctor_module
import quantcore.doctor_checks as checks_module
from quantcore.cli import app
from quantcore.doctor import DoctorCheck, DoctorReport, _overall_status, run_doctor

runner = CliRunner()

EXPECTED_CHECK_IDS = [
    "python",
    "engine",
    "panel",
    "data",
    "snapshots",
    "ui",
    "node",
    "pnpm",
    "port",
    "disk",
    "git",
    "token",
    "chrome",
    "tests",
]
REPORT_KEYS = {
    "status",
    "generated_at",
    "version",
    "engine_backend",
    "engine_available",
    "panel_available",
    "root",
    "counts",
    "checks",
}
CHECK_KEYS = {"id", "title", "status", "detail", "hint", "required"}


def _check(check_id: str, status: str = "pass", required: bool = True) -> DoctorCheck:
    return DoctorCheck(
        id=check_id,
        title=check_id.title(),
        status=status,
        detail=f"{check_id} detail",
        required=required,
    )


def _report(status: str = "ok", checks: list[DoctorCheck] | None = None) -> DoctorReport:
    return DoctorReport(
        status=status,
        checks=checks if checks is not None else [_check("python")],
        version=quantcore.__version__,
        engine_backend="cpp",
        engine_available=True,
        panel_available=True,
        generated_at="2026-01-01T00:00:00+00:00",
        root="/repo",
    )


def _make_repo(tmp_path: Path) -> Path:
    """Fabricated healthy checkout: warehouse, snapshot, built UI and C++ tests."""
    root = tmp_path / "repo"
    (root / ".venv").mkdir(parents=True)
    warehouse = root / "data" / "warehouse"
    (warehouse / "dataset=bars").mkdir(parents=True)
    (warehouse / "dataset=calendar").mkdir()
    (warehouse / "warehouse_manifest.json").write_text(
        json.dumps({"datasets": {"bars": {"rows": 10}, "calendar": {"rows": 3}}}),
        encoding="utf-8",
    )
    snapshot = root / "data" / "snapshots" / ("snap_" + "a" * 16)
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "snap_" + "a" * 16,
                "synthetic": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    ui = root / "ui" / "dist"
    ui.mkdir(parents=True)
    (ui / "index.html").write_text("<html></html>", encoding="utf-8")
    build = root / "build" / "cmake"
    build.mkdir(parents=True)
    (build / "qcore_tests").write_text("", encoding="utf-8")
    return root


def _patch_available_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quantcore, "engine_backend", lambda: "cpp")
    monkeypatch.setattr(quantcore, "engine_available", lambda: True)
    monkeypatch.setattr(quantcore, "panel_available", lambda: True)


def _patch_host_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin host-dependent probes so the report is deterministic."""
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token-for-tests")
    monkeypatch.setattr(checks_module, "in_project_venv", lambda root: True)
    monkeypatch.setattr(checks_module, "probe_port", lambda port: (True, "free"))
    monkeypatch.setattr(checks_module, "find_chrome", lambda: "/usr/bin/google-chrome")
    monkeypatch.setattr(checks_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        checks_module,
        "check_git",
        lambda root: DoctorCheck(
            "git", "Git repository", "pass", "branch=main dirty_files=0", required=False
        ),
    )
    monkeypatch.setattr(
        checks_module.shutil,
        "disk_usage",
        lambda path: types.SimpleNamespace(total=0, used=0, free=10 * 1024**3),
    )


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------
def test_report_to_dict_contract_and_counts() -> None:
    checks = [
        _check("python", "pass"),
        _check("engine", "pass"),
        _check("data", "warn", required=False),
        _check("port", "skip", required=False),
    ]
    report = _report("warn", checks)
    payload = report.to_dict()
    assert set(payload) == REPORT_KEYS
    assert payload["counts"] == {"pass": 2, "warn": 1, "fail": 0, "skip": 1}
    assert all(set(item) == CHECK_KEYS for item in payload["checks"])
    assert payload["version"] == quantcore.__version__
    assert payload["engine_backend"] == "cpp"
    assert payload["generated_at"] == "2026-01-01T00:00:00+00:00"
    json.dumps(payload)  # must be JSON serialisable
    assert report.counts() == {"pass": 2, "warn": 1, "fail": 0, "skip": 1}
    assert [item.id for item in report.warnings()] == ["data"]
    assert report.failures() == []


def test_overall_status_rules() -> None:
    assert _overall_status([_check("a", "pass"), _check("b", "skip", required=False)]) == "ok"
    assert _overall_status([_check("a", "warn", required=False)]) == "warn"
    assert _overall_status([_check("a", "fail", required=False)]) == "warn"
    assert _overall_status([_check("a", "fail", required=True)]) == "fail"


def test_check_required_flags_are_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_repo(tmp_path)
    _patch_available_engine(monkeypatch)
    _patch_host_checks(monkeypatch)
    report = run_doctor(root, check_port=8000)
    required = {check.id for check in report.checks if check.required}
    assert required == {"python", "engine", "panel"}
    assert report.status == "ok"
    assert report.counts() == {"pass": 14, "warn": 0, "fail": 0, "skip": 0}


# ---------------------------------------------------------------------------
# run_doctor end-to-end on fabricated roots
# ---------------------------------------------------------------------------
def test_run_doctor_healthy_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_repo(tmp_path)
    _patch_available_engine(monkeypatch)
    _patch_host_checks(monkeypatch)
    report = run_doctor(root, check_port=8000)
    assert report.status == "ok", [check.to_dict() for check in report.checks]
    assert [check.id for check in report.checks] == EXPECTED_CHECK_IDS
    assert report.root == str(root.resolve())
    data = next(check for check in report.checks if check.id == "data")
    assert data.status == "pass" and "bars rows=10" in data.detail
    snapshots = next(check for check in report.checks if check.id == "snapshots")
    assert snapshots.status == "pass" and "synthetic=True" in snapshots.detail
    assert all(isinstance(check.detail, str) for check in report.checks)
    assert all(isinstance(check.hint, str) for check in report.checks)


def test_run_doctor_optional_checks_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_repo(tmp_path)
    _patch_available_engine(monkeypatch)
    _patch_host_checks(monkeypatch)
    report = run_doctor(root, check_port=None, include_optional=False)
    by_id = {check.id: check for check in report.checks}
    assert by_id["node"].status == "skip"
    assert by_id["pnpm"].status == "skip"
    assert by_id["chrome"].status == "skip"
    assert by_id["port"].status == "skip"
    assert report.status == "ok"


def test_run_doctor_fails_without_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    monkeypatch.setattr(quantcore, "engine_backend", lambda: "missing")
    monkeypatch.setattr(quantcore, "engine_available", lambda: False)
    monkeypatch.setattr(quantcore, "panel_available", lambda: False)
    report = run_doctor(root, check_port=None, include_optional=False)
    assert report.status == "fail"
    assert [check.id for check in report.failures()] == ["engine"]
    by_id = {check.id: check for check in report.checks}
    assert by_id["panel"].status == "warn"
    assert by_id["panel"].required is True
    assert by_id["python"].status == "warn"  # no .venv in the fabricated root
    for check_id in ("data", "snapshots", "ui", "tests"):
        assert by_id[check_id].status == "warn", check_id
    assert by_id["token"].status == "skip"
    assert by_id["node"].status == "skip"


def test_run_doctor_warns_without_failing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    _patch_available_engine(monkeypatch)
    report = run_doctor(root, check_port=None, include_optional=False)
    assert report.status == "warn"
    assert report.failures() == []
    assert {check.id for check in report.warnings()} >= {"data", "snapshots", "ui", "tests"}


def test_run_doctor_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_repo(tmp_path)
    _patch_available_engine(monkeypatch)
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    run_doctor(root, check_port=None, include_optional=False)
    after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    assert after == before


# ---------------------------------------------------------------------------
# focused probes
# ---------------------------------------------------------------------------
def test_port_check_detects_busy_port() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = int(listener.getsockname()[1])
        busy = checks_module.check_port(port)
        assert busy.status == "warn"
        assert f"127.0.0.1:{port}" in busy.detail
    finally:
        listener.close()
    assert checks_module.check_port(port).status == "pass"
    assert checks_module.check_port(None).status == "skip"


def test_token_check_never_leaks_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "super-secret-token")
    check = checks_module.check_token()
    assert check.status == "pass"
    assert "super-secret-token" not in json.dumps(check.to_dict())
    monkeypatch.delenv("TUSHARE_TOKEN")
    assert checks_module.check_token().status == "skip"


def test_disk_check_warns_when_low(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        checks_module.shutil,
        "disk_usage",
        lambda path: types.SimpleNamespace(total=0, used=0, free=1024),
    )
    assert checks_module.check_disk(Path.cwd()).status == "warn"


def test_git_check_outside_repository(tmp_path: Path) -> None:
    check = checks_module.check_git(tmp_path)
    assert check.status == "warn"
    assert "not a git repository" in check.detail


def test_git_check_repository(tmp_path: Path) -> None:
    init = subprocess.run(
        ["git", "init", "-q", str(tmp_path)], capture_output=True, text=True, check=False
    )
    if init.returncode != 0:  # pragma: no cover - git is present in CI
        pytest.skip("git is unavailable")
    check = checks_module.check_git(tmp_path)
    assert check.status == "pass"
    assert "branch=" in check.detail


def test_snapshot_check_reads_manifest(tmp_path: Path) -> None:
    empty = checks_module.check_snapshots(tmp_path / "snapshots")
    assert empty.status == "warn"
    snapshot = tmp_path / "snapshots" / ("snap_" + "b" * 16)
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "snap_" + "b" * 16,
                "synthetic": False,
                "created_at": "2026-02-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    found = checks_module.check_snapshots(tmp_path / "snapshots")
    assert found.status == "pass"
    assert "snap_" + "b" * 16 in found.detail
    assert "synthetic=False" in found.detail


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_doctor_cli_json_and_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor_module, "run_doctor", lambda **kwargs: _report("ok"))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert set(payload) == REPORT_KEYS
    assert payload["status"] == "ok"

    monkeypatch.setattr(
        doctor_module, "run_doctor", lambda **kwargs: _report("warn", [_check("data", "warn")])
    )
    assert runner.invoke(app, ["doctor"]).exit_code == 0
    strict = runner.invoke(app, ["doctor", "--strict"])
    assert strict.exit_code == 1

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        lambda **kwargs: _report("fail", [_check("engine", "fail")]),
    )
    failed = runner.invoke(app, ["doctor"])
    assert failed.exit_code == 1


def test_doctor_cli_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _report("warn", [_check("python", "pass"), _check("data", "warn", required=False)])
    monkeypatch.setattr(doctor_module, "run_doctor", lambda **kwargs: report)
    result = runner.invoke(app, ["doctor", "--no-json-output"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert "[PASS] python" in result.stdout
    assert "[WARN] data" in result.stdout
    assert "summary: warn" in result.stdout
    assert "hint:" in result.stdout


def test_doctor_cli_real_environment() -> None:
    result = runner.invoke(app, ["doctor", "--port", "0"])
    assert result.exit_code == 0, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert payload["status"] in {"ok", "warn"}
    assert [item["id"] for item in payload["checks"]] == EXPECTED_CHECK_IDS
    assert payload["counts"]["fail"] == 0


def test_doctor_cli_custom_roots_and_strict(tmp_path: Path) -> None:
    args = [
        "doctor",
        "--port",
        "0",
        "--data-root",
        str(tmp_path / "data"),
        "--snapshots-root",
        str(tmp_path / "snapshots"),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert payload["status"] == "warn"
    by_id = {item["id"]: item for item in payload["checks"]}
    assert by_id["data"]["status"] == "warn"
    assert by_id["snapshots"]["status"] == "warn"
    assert by_id["engine"]["status"] == "pass"
    strict = runner.invoke(app, [*args, "--strict"])
    assert strict.exit_code == 1


def test_doctor_cli_help_lists_options() -> None:
    from typer.main import get_command

    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    # Inspect the declared options instead of parsing rich help text: the rendered
    # help wraps/hides option names on narrow terminals (e.g. some CI runners).
    doctor_cmd = get_command(app).commands["doctor"]
    options = {
        opt
        for param in doctor_cmd.params
        for opt in (*getattr(param, "opts", ()), *getattr(param, "secondary_opts", ()))
    }
    for option in (
        "--json-output",
        "--no-json-output",
        "--strict",
        "--data-root",
        "--snapshots-root",
        "--port",
    ):
        assert option in options, option


def test_doctor_import_surface() -> None:
    assert sys.version_info >= (3, 12)
    assert callable(doctor_module.run_doctor)
    assert callable(doctor_module.doctor_command)
