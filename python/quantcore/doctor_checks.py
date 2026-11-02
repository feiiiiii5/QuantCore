"""Read-only probes behind 'qc doctor' (imported lazily by quantcore.doctor).

Each probe returns a DoctorCheck; nothing here writes to disk, opens a network
connection (only an optional loopback bind probe) or starts a service.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from .doctor import DoctorCheck, DoctorReport

MIN_PYTHON = (3, 12)
MIN_FREE_BYTES = 2 * 1024**3
GIB = 1024.0**3
GIT_TIMEOUT_SECONDS = 3

CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
CHROME_COMMANDS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")

__all__ = [
    "check_chrome",
    "check_data",
    "check_disk",
    "check_engine",
    "check_git",
    "check_node",
    "check_panel",
    "check_pnpm",
    "check_port",
    "check_python",
    "check_snapshots",
    "check_tests",
    "check_token",
    "check_ui",
    "find_chrome",
    "in_project_venv",
    "probe_port",
    "render_text",
    "snapshot_manifests",
]


# ---------------------------------------------------------------------------
# individual probes (each is a pure read; tests monkeypatch these functions)
# ---------------------------------------------------------------------------
def in_project_venv(root: Path) -> bool:
    if sys.prefix == sys.base_prefix:
        return False
    try:
        return Path(sys.prefix).resolve() == (root / ".venv").resolve()
    except OSError:  # pragma: no cover - defensive
        return False


def check_python(root: Path) -> DoctorCheck:
    version = sys.version_info
    version_text = f"{version.major}.{version.minor}.{version.micro}"
    detail = f"Python {version_text} ({sys.executable})"
    if (version.major, version.minor) < MIN_PYTHON:
        return DoctorCheck(
            "python",
            "Python runtime",
            "fail",
            f"{detail}; requires Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            "run everything through 'uv run ...' (the project .venv is Python 3.12)",
            required=True,
        )
    if not in_project_venv(root):
        return DoctorCheck(
            "python",
            "Python runtime",
            "warn",
            f"{detail}; project .venv not detected",
            "run commands through 'uv run ...' so the 3.12 project venv is used",
            required=True,
        )
    return DoctorCheck(
        "python", "Python runtime", "pass", f"{detail}; project .venv", required=True
    )


def check_engine(backend: str, available: bool) -> DoctorCheck:
    detail = f"engine_backend={backend} engine_available={available}"
    if backend == "cpp" and available:
        return DoctorCheck("engine", "C++ backtest engine", "pass", detail, required=True)
    return DoctorCheck(
        "engine",
        "C++ backtest engine",
        "fail",
        detail,
        "run 'make build' to build the C++ extension",
        required=True,
    )


def check_panel(available: bool, engine_available: bool) -> DoctorCheck:
    detail = f"panel_available={available}"
    if available:
        return DoctorCheck("panel", "C++ panel (.qpanel)", "pass", detail, required=True)
    if engine_available:
        return DoctorCheck(
            "panel",
            "C++ panel (.qpanel)",
            "fail",
            f"{detail}; engine present but the .qpanel writer is not",
            "run 'make build' to rebuild the C++ extension",
            required=True,
        )
    return DoctorCheck(
        "panel",
        "C++ panel (.qpanel)",
        "warn",
        f"{detail}; snapshots fall back to Parquet",
        "run 'make build' to build the C++ extension",
        required=True,
    )


def check_data(data_root: Path) -> DoctorCheck:
    warehouse = data_root / "warehouse"
    hint = "uv run qc data update --provider synthetic"
    if not warehouse.is_dir():
        return DoctorCheck(
            "data", "Data warehouse", "warn", f"no warehouse at {warehouse}", hint, required=False
        )
    manifest_path = warehouse / "warehouse_manifest.json"
    if not manifest_path.is_file():
        return DoctorCheck(
            "data",
            "Data warehouse",
            "warn",
            f"{warehouse} has no warehouse_manifest.json",
            hint,
            required=False,
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DoctorCheck(
            "data",
            "Data warehouse",
            "warn",
            f"unreadable warehouse manifest: {exc}",
            hint,
            required=False,
        )
    datasets = payload.get("datasets") or {}
    if not isinstance(datasets, dict) or not datasets:
        return DoctorCheck(
            "data", "Data warehouse", "warn", f"{warehouse} has no datasets", hint, required=False
        )
    missing = sorted(name for name in datasets if not (warehouse / f"dataset={name}").is_dir())
    if missing:
        return DoctorCheck(
            "data",
            "Data warehouse",
            "warn",
            f"manifest lists missing datasets: {', '.join(missing)}",
            hint,
            required=False,
        )
    bars_rows = int((datasets.get("bars") or {}).get("rows", 0))
    detail = f"{len(datasets)} datasets, bars rows={bars_rows} ({warehouse})"
    return DoctorCheck("data", "Data warehouse", "pass", detail, required=False)


def snapshot_manifests(snapshots_root: Path) -> list[dict[str, Any]]:
    """Read snapshot manifests directly (no pandas import; newest first)."""
    if not snapshots_root.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for directory in snapshots_root.glob("snap_*"):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            manifests.append(payload)
    manifests.sort(
        key=lambda item: (str(item.get("created_at", "")), str(item.get("snapshot_id", ""))),
        reverse=True,
    )
    return manifests


def check_snapshots(snapshots_root: Path) -> DoctorCheck:
    manifests = snapshot_manifests(snapshots_root)
    if not manifests:
        return DoctorCheck(
            "snapshots",
            "Snapshots",
            "warn",
            f"no snapshots under {snapshots_root}",
            "uv run qc snapshot build",
            required=False,
        )
    latest = manifests[0]
    snapshot_id = str(latest.get("snapshot_id", "unknown"))
    synthetic = bool(latest.get("synthetic", False))
    detail = f"{len(manifests)} snapshot(s); latest={snapshot_id} synthetic={synthetic}"
    return DoctorCheck("snapshots", "Snapshots", "pass", detail, required=False)


def check_ui(root: Path) -> DoctorCheck:
    index = root / "ui" / "dist" / "index.html"
    if index.is_file():
        return DoctorCheck("ui", "Built UI", "pass", f"built UI: {index}", required=False)
    return DoctorCheck(
        "ui",
        "Built UI",
        "warn",
        f"missing {index}",
        "pnpm -C ui install && pnpm -C ui build",
        required=False,
    )


def check_node(include_optional: bool) -> DoctorCheck:
    if not include_optional:
        return DoctorCheck("node", "Node.js", "skip", "optional check disabled", required=False)
    found = shutil.which("node")
    if found is None:
        return DoctorCheck(
            "node",
            "Node.js",
            "warn",
            "node not found on PATH",
            "install Node.js 20+ for the UI build (see docs/DEV-SETUP.md)",
            required=False,
        )
    return DoctorCheck("node", "Node.js", "pass", f"node: {found}", required=False)


def check_pnpm(include_optional: bool) -> DoctorCheck:
    if not include_optional:
        return DoctorCheck("pnpm", "pnpm", "skip", "optional check disabled", required=False)
    found = shutil.which("pnpm")
    if found is None:
        return DoctorCheck(
            "pnpm",
            "pnpm",
            "warn",
            "pnpm not found on PATH",
            "enable pnpm (corepack enable pnpm) for the UI build",
            required=False,
        )
    return DoctorCheck("pnpm", "pnpm", "pass", f"pnpm: {found}", required=False)


def probe_port(port: int) -> tuple[bool, str]:
    """Bind 127.0.0.1:port (loopback only) and close it; return (free, detail)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            return False, exc.strerror or str(exc)
    return True, "free"


def check_port(port: int | None) -> DoctorCheck:
    if port is None:
        return DoctorCheck("port", "Loopback port", "skip", "port check disabled", required=False)
    free, detail = probe_port(port)
    if free:
        return DoctorCheck(
            "port", "Loopback port", "pass", f"127.0.0.1:{port} is free", required=False
        )
    return DoctorCheck(
        "port",
        "Loopback port",
        "warn",
        f"127.0.0.1:{port} is not free ({detail})",
        "stop the other process or run 'uv run qc serve --port <other>'",
        required=False,
    )


def check_disk(root: Path) -> DoctorCheck:
    try:
        usage = shutil.disk_usage(root if root.exists() else Path.cwd())
    except OSError as exc:
        return DoctorCheck(
            "disk", "Disk space", "skip", f"disk usage unavailable: {exc}", required=False
        )
    free = usage.free
    if free < MIN_FREE_BYTES:
        return DoctorCheck(
            "disk",
            "Disk space",
            "warn",
            f"only {free / GIB:.2f} GiB free",
            "free disk space before building/backtesting",
            required=False,
        )
    return DoctorCheck("disk", "Disk space", "pass", f"{free / GIB:.1f} GiB free", required=False)


def check_git(root: Path) -> DoctorCheck:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--branch"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DoctorCheck(
            "git", "Git repository", "skip", f"git unavailable: {exc}", required=False
        )
    if proc.returncode != 0:
        return DoctorCheck(
            "git",
            "Git repository",
            "warn",
            "not a git repository",
            "run 'git init' if you want experiment provenance",
            required=False,
        )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    header = lines[0] if lines else ""
    branch = header[3:].split("...")[0].strip() if header.startswith("## ") else ""
    dirty = max(len(lines) - 1, 0)
    detail = f"branch={branch or 'unknown'} dirty_files={dirty}"
    return DoctorCheck("git", "Git repository", "pass", detail, required=False)


def check_token() -> DoctorCheck:
    if os.environ.get("TUSHARE_TOKEN", "").strip():
        return DoctorCheck(
            "token",
            "TUSHARE_TOKEN",
            "pass",
            "TUSHARE_TOKEN is set (value never displayed); the tushare provider can be tested",
            required=False,
        )
    return DoctorCheck(
        "token",
        "TUSHARE_TOKEN",
        "skip",
        "TUSHARE_TOKEN not set; the default provider is synthetic (fully offline)",
        "set TUSHARE_TOKEN only when you want to verify the real provider; never commit it",
        required=False,
    )


def find_chrome() -> str | None:
    for candidate in CHROME_PATHS:
        if Path(candidate).is_file():
            return candidate
    for command in CHROME_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return None


def check_chrome(include_optional: bool) -> DoctorCheck:
    if not include_optional:
        return DoctorCheck(
            "chrome", "Chrome/Chromium", "skip", "optional check disabled", required=False
        )
    found = find_chrome()
    if found:
        return DoctorCheck("chrome", "Chrome/Chromium", "pass", f"Chrome: {found}", required=False)
    return DoctorCheck(
        "chrome",
        "Chrome/Chromium",
        "warn",
        "Chrome/Chromium not found",
        "only needed for 'make e2e' and PDF report export",
        required=False,
    )


def check_tests(root: Path) -> DoctorCheck:
    binary = root / "build" / "cmake" / "qcore_tests"
    if binary.is_file():
        return DoctorCheck(
            "tests", "C++ test binary", "pass", f"C++ tests: {binary}", required=False
        )
    return DoctorCheck(
        "tests",
        "C++ test binary",
        "warn",
        f"missing {binary}",
        "run 'make build' to build the C++ test binary",
        required=False,
    )


# ---------------------------------------------------------------------------
# human rendering for 'qc doctor --no-json-output'
# ---------------------------------------------------------------------------
def render_text(report: DoctorReport) -> str:
    lines: list[str] = []
    for check in report.checks:
        line = f"[{check.status.upper()}] {check.id}  {check.detail}"
        if check.hint:
            line += f"  (hint: {check.hint})"
        lines.append(line)
    counts = report.counts()
    lines.append("")
    lines.append(
        f"summary: {report.status} (pass={counts['pass']} warn={counts['warn']} "
        f"fail={counts['fail']} skip={counts['skip']}) engine={report.engine_backend} "
        f"version={report.version} root={report.root}"
    )
    if report.status != "ok":
        lines.append("hint: fix the FAIL/WARN items above, then re-run 'uv run qc doctor'")
    return "\n".join(lines)
