"""Local environment self-check for 'qc doctor': read-only, offline, no server start.

The public contract (DoctorCheck, DoctorReport, run_doctor) is also consumed by the local
API (/api/doctor) and the UI settings page, so the keys returned by
DoctorReport.to_dict() are frozen.  Individual probes live in doctor_checks.py and are
imported lazily so 'qc --help' stays fast.
"""

# ruff: noqa: B008 -- typer's documented API uses function calls in argument defaults

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

import quantcore

DEFAULT_PORT = 8000

__all__ = [
    "DEFAULT_PORT",
    "DoctorCheck",
    "DoctorReport",
    "doctor_command",
    "run_doctor",
]


@dataclass(frozen=True)
class DoctorCheck:
    """One environment probe with a human-readable detail and an actionable hint."""

    id: str
    title: str
    status: str
    detail: str
    hint: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "hint": self.hint,
            "required": bool(self.required),
        }


@dataclass(frozen=True)
class DoctorReport:
    """Aggregated environment report (status is 'ok' / 'warn' / 'fail')."""

    status: str
    checks: list[DoctorCheck]
    version: str
    engine_backend: str
    engine_available: bool
    panel_available: bool
    generated_at: str
    root: str

    def counts(self) -> dict[str, int]:
        counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def failures(self) -> list[DoctorCheck]:
        return [check for check in self.checks if check.status == "fail"]

    def warnings(self) -> list[DoctorCheck]:
        return [check for check in self.checks if check.status == "warn"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "version": self.version,
            "engine_backend": self.engine_backend,
            "engine_available": bool(self.engine_available),
            "panel_available": bool(self.panel_available),
            "root": self.root,
            "counts": self.counts(),
            "checks": [check.to_dict() for check in self.checks],
        }


def _overall_status(checks: list[DoctorCheck]) -> str:
    """'fail' for a required failure, else 'warn' for any warning, else 'ok'."""
    if any(check.status == "fail" and check.required for check in checks):
        return "fail"
    if any(
        check.status == "warn" or (check.status == "fail" and not check.required)
        for check in checks
    ):
        return "warn"
    return "ok"


def run_doctor(
    root: str | Path | None = None,
    *,
    check_port: int | None = DEFAULT_PORT,
    include_optional: bool = True,
    data_root: str | Path | None = None,
    snapshots_root: str | Path | None = None,
) -> DoctorReport:
    """Probe the local environment; fully read-only, offline and fast (<2s)."""
    from . import doctor_checks

    root_path = Path(root).expanduser() if root is not None else Path.cwd()
    with contextlib.suppress(OSError):  # pragma: no cover - defensive
        root_path = root_path.resolve()
    data_path = Path(data_root).expanduser() if data_root is not None else root_path / "data"
    snapshots_path = (
        Path(snapshots_root).expanduser() if snapshots_root is not None else data_path / "snapshots"
    )

    backend = quantcore.engine_backend()
    engine_ok = quantcore.engine_available()
    panel_ok = quantcore.panel_available()
    checks = [
        doctor_checks.check_python(root_path),
        doctor_checks.check_engine(backend, engine_ok),
        doctor_checks.check_panel(panel_ok, engine_ok),
        doctor_checks.check_data(data_path),
        doctor_checks.check_snapshots(snapshots_path),
        doctor_checks.check_ui(root_path),
        doctor_checks.check_node(include_optional),
        doctor_checks.check_pnpm(include_optional),
        doctor_checks.check_port(check_port),
        doctor_checks.check_disk(root_path),
        doctor_checks.check_git(root_path),
        doctor_checks.check_token(),
        doctor_checks.check_chrome(include_optional),
        doctor_checks.check_tests(root_path),
    ]
    return DoctorReport(
        status=_overall_status(checks),
        checks=checks,
        version=quantcore.__version__,
        engine_backend=backend,
        engine_available=engine_ok,
        panel_available=panel_ok,
        generated_at=datetime.now(UTC).isoformat(),
        root=str(root_path),
    )


def doctor_command(
    json_output: bool = typer.Option(True, help="emit the JSON report"),
    strict: bool = typer.Option(False, help="treat warnings as failures (exit code 1)"),
    data_root: Path | None = typer.Option(None, help="data directory (default: <root>/data)"),
    snapshots_root: Path | None = typer.Option(
        None, help="snapshots directory (default: <data-root>/snapshots)"
    ),
    port: int = typer.Option(
        DEFAULT_PORT, min=0, max=65535, help="loopback port to probe (0 disables)"
    ),
) -> None:
    """Check the local environment: Python, engine, data, UI, port (read-only, offline)."""
    from .doctor_checks import render_text

    report = run_doctor(
        check_port=None if port == 0 else port,
        data_root=data_root,
        snapshots_root=snapshots_root,
    )
    if json_output:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(render_text(report))
    if report.status == "fail" or (strict and report.status != "ok"):
        raise typer.Exit(code=1)
