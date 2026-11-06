#!/usr/bin/env python3
"""Assemble a fresh local release; standard library only, never publish anything."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tomllib
import uuid
import zipfile
from email.parser import Parser
from pathlib import Path


def run(command: list[str], root: Path, environment: dict[str, str], log: Path) -> int:
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=1200,
            check=False,
        )
    return result.returncode


def require_step(command: list[str], root: Path, environment: dict[str, str], log: Path) -> None:
    code = run(command, root, environment, log)
    if code:
        raise RuntimeError(f"{log.stem} exited {code}; see {log}")


def distributions(bundle: Path, version: str) -> Path:
    wheels, sources = list(bundle.glob("*.whl")), list(bundle.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise RuntimeError("this build must produce exactly one native wheel and one sdist")
    wheel = wheels[0]
    if (
        not wheel.name.startswith(f"quantcore-{version}-")
        or sources[0].name != f"quantcore-{version}.tar.gz"
    ):
        raise RuntimeError("build artifacts do not match the current project version")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        wheel_info = next(name for name in names if name.endswith(".dist-info/WHEEL"))
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        tags = Parser().parsestr(archive.read(wheel_info).decode())
        package = Parser().parsestr(archive.read(metadata).decode())
        native = any(
            Path(name).name.startswith("_qcore") and name.endswith((".so", ".pyd"))
            for name in names
        )
        if tags.get("Root-Is-Purelib", "").lower() != "false" or not native:
            raise RuntimeError("release wheel must contain the native _qcore extension")
        if package.get("Name") != "quantcore" or package.get("Version") != version:
            raise RuntimeError("wheel metadata does not match this project/version")
    return wheel


def audit(bundle: Path, work: Path, root: Path, environment: dict[str, str]) -> None:
    report = bundle / "pip-audit.json"
    code = run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--path",
            sysconfig.get_path("purelib"),
            "--skip-editable",
            "--format",
            "json",
            "--output",
            str(report),
            "--progress-spinner",
            "off",
        ],
        root,
        environment,
        work / "audit.log",
    )
    summary: dict[str, object] = {
        "status": "error",
        "returncode": code,
        "scope": "installed build environment; editable distributions omitted",
    }
    try:
        dependencies = json.loads(report.read_text(encoding="utf-8"))["dependencies"]
        if (
            not isinstance(dependencies, list)
            or not dependencies
            or any(not isinstance(item, dict) for item in dependencies)
        ):
            raise ValueError("audit returned no valid dependency inventory")
        skipped = [
            {"name": item["name"], "reason": item["skip_reason"]}
            for item in dependencies
            if item.get("skip_reason")
        ]
        # pip-audit includes --skip-editable exclusions in its JSON inventory.
        # Only our own source checkout is an intentional, reviewed omission.
        omitted = [
            item
            for item in skipped
            if item["name"] == "quantcore" and item["reason"] == "distribution marked as editable"
        ]
        unreviewed = [item for item in skipped if item not in omitted]
        vulnerabilities = sum(len(item.get("vulns", [])) for item in dependencies)
        summary.update(
            packages_audited=len(dependencies) - len(skipped),
            vulnerabilities=vulnerabilities,
            skipped_dependencies=skipped,
            intentional_omissions=omitted,
            status="failed"
            if code or vulnerabilities
            else "incomplete"
            if unreviewed
            else "passed",
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        summary["error"] = str(exc)
    (bundle / "audit-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if summary["status"] != "passed":
        raise RuntimeError(
            f"audit {summary['status']}; see {bundle / 'audit-summary.json'} and {work / 'audit.log'}"
        )


def checksums(bundle: Path) -> None:
    manifest = bundle / "SHA256SUMS"
    paths = sorted(path for path in bundle.rglob("*") if path.is_file() and path != manifest)
    lines = []
    for path in paths:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        lines.append(f"{digest}  {path.relative_to(bundle).as_posix()}\n")
    manifest.write_text("".join(lines))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    version = str(tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"])
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".release-", dir=dist))
    bundle = work / "bundle"
    bundle.mkdir()
    environment = os.environ.copy()
    for key in (
        "SSH_AUTH_SOCK",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "QC_SERVER_TOKEN",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
        "VITE_QC_DEFAULT_API_BASE",
    ):
        environment.pop(key, None)
    print(f"[release] staging: {work}", flush=True)
    try:
        require_step(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(bundle / "requirements.txt"),
            ],
            root,
            environment,
            work / "requirements.log",
        )
        require_step(
            ["uv", "build", "--python", sys.executable, "--out-dir", str(bundle)],
            root,
            environment,
            work / "build.log",
        )
        wheel = distributions(bundle, version)
        require_step(["pnpm", "-C", "ui", "build"], root, environment, work / "ui-build.log")
        if not (root / "ui/dist/index.html").is_file():
            raise RuntimeError("UI build did not produce ui/dist/index.html")
        with tarfile.open(bundle / f"quantcore-ui-{version}.tar.gz", "w:gz") as archive:
            archive.add(root / "ui/dist", arcname="dist")
        require_step(
            [sys.executable, str(root / "scripts/sbom.py"), "--out", str(bundle / "sbom.cdx.json")],
            root,
            environment,
            work / "sbom.log",
        )
        audit(bundle, work, root, environment)
        (bundle / "INSTALL.md").write_text(
            f"# QuantCore {version} local bundle\n\n"
            f"For a matching macOS/Linux platform and CPython wheel tag. Requires uv and Python {python_version}; "
            "dependency installation needs internet or a separately prepared wheelhouse. This bundle "
            "does not include Python, a signed installer, market data or brokerage connectivity.\n\n"
            "Verify SHA256SUMS first: `sha256sum -c SHA256SUMS` or macOS "
            "`shasum -a 256 -c SHA256SUMS`. Checksums detect corruption, not publisher identity.\n\n"
            f"```sh\nuv venv --python {python_version} .venv\n"
            "uv pip install --python .venv/bin/python --require-hashes -r requirements.txt\n"
            f"uv pip install --python .venv/bin/python --no-deps ./{wheel.name}\n"
            f"mkdir -p ui\ntar -xzf quantcore-ui-{version}.tar.gz -C ui\n"
            ".venv/bin/qc doctor\n.venv/bin/qc demo --data-root data\n"
            ".venv/bin/qc serve --data-root data --ui-dir ui/dist --port 8000 --open\n```\n\n"
            "The demo uses SYNTHETIC data. Network data access is off by default; no real orders. "
            "SBOM inventories lockfiles; audit-summary.json covers the installed build environment "
            "and omits editable distributions. Neither proves every target deployment is safe.\n"
        )
        checksums(bundle)
        output = dist / "release"
        backup = dist / f"release-previous-{uuid.uuid4().hex[:12]}" if output.exists() else None
        if backup is not None:
            output.rename(backup)
        try:
            bundle.rename(output)
        except OSError:
            if backup is not None:
                backup.rename(output)
            raise
        print(f"[release] bundle: {output}")
        print(f"[release] audit passed; build diagnostics: {work}")
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        StopIteration,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"[release] FAILED: {exc}\n[release] diagnostics preserved: {work}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
