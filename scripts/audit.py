#!/usr/bin/env python3
"""Offline-ish supply-chain audit: CycloneDX SBOM + pip-audit vulnerabilities.

The SBOM is generated from lockfiles (no network). Vulnerability lookup uses pip-audit's
OSV/PyPI advisory source and therefore needs network on the first run; the command exits
non-zero if any known vulnerability is reported.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    sbom = DIST / "sbom.cdx.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "sbom.py"), "--out", str(sbom)], check=True)
    venv = ROOT / ".venv"
    packages = venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    if not packages.exists():  # Windows layout
        packages = venv / "Lib" / "site-packages"
    report = DIST / "pip-audit.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--path",
            str(packages),
            "--format",
            "json",
            "--output",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not report.exists():
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:], file=sys.stderr)
        return 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    dependencies = payload.get("dependencies", [])
    vulnerabilities = sum(len(item.get("vulns", [])) for item in dependencies)
    print(
        json.dumps(
            {
                "ok": vulnerabilities == 0,
                "sbom": str(sbom),
                "packages_audited": len(dependencies),
                "vulnerabilities": vulnerabilities,
                "audit": str(report),
            },
            ensure_ascii=False,
        )
    )
    return 0 if vulnerabilities == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
