"""Release orchestration uses fresh artifacts and honest audit/checksum outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, source: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + source)
    path.chmod(0o755)


@pytest.fixture
def release_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "release project"
    scripts, tools, modules = root / "scripts", root / "tools", root / "fake_modules"
    for directory in (scripts, tools, modules, root / "ui", root / "dist/release"):
        directory.mkdir(parents=True)
    for name in ("release.sh", "release_bundle.py"):
        if (ROOT / "scripts" / name).exists():
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
    (root / "pyproject.toml").write_text('[project]\nname="quantcore"\nversion="0.1.0"\n')
    (root / "dist/release/prior.txt").write_text("keep previous successful bundle")
    (root / "dist/quantcore-stale.whl").write_text("unrelated old wheel")
    (root / "dist/quantcore-stale.tar.gz").write_text("unrelated old source")
    (root / "README.md").write_text("fixture instructions")
    executable(
        tools / "uv",
        """import os, sys, tarfile, zipfile
from pathlib import Path
args = sys.argv[1:]
if args[0] == "run":
    args = [arg for arg in args[1:] if arg != "--no-sync"]
    os.execv(sys.executable, [sys.executable, *args[1:]])
out = Path(args[args.index("--out-dir") + 1]) if "--out-dir" in args else Path("dist")
out.mkdir(parents=True, exist_ok=True)
wheel = out / "quantcore-0.1.0-cp312-cp312-macosx_11_0_arm64.whl"
with zipfile.ZipFile(wheel, "w") as archive:
    archive.writestr("quantcore/_qcore.cpython-312-darwin.so", b"fixture native extension")
    archive.writestr("quantcore-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0\\nRoot-Is-Purelib: false\\n")
    archive.writestr("quantcore-0.1.0.dist-info/METADATA", "Name: quantcore\\nVersion: 0.1.0\\n")
with tarfile.open(out / "quantcore-0.1.0.tar.gz", "w:gz") as archive:
    archive.add("pyproject.toml", arcname="quantcore-0.1.0/pyproject.toml")
""",
    )
    executable(
        tools / "pnpm",
        """from pathlib import Path
out = Path("ui/dist")
out.mkdir(parents=True, exist_ok=True)
(out / "index.html").write_text("fresh UI")
""",
    )
    executable(
        tools / "python",
        "import os, sys\nos.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n",
    )
    executable(tools / "sha256sum", "raise SystemExit(127)\n")
    executable(
        tools / "shasum",
        """import hashlib, sys
from pathlib import Path
for name in sys.argv[3:]:
    print(hashlib.sha256(Path(name).read_bytes()).hexdigest() + "  " + name)
""",
    )
    (scripts / "sbom.py").write_text("""import json, sys
from pathlib import Path
Path(sys.argv[sys.argv.index("--out") + 1]).write_text(json.dumps({"components": []}))
""")
    (scripts / "audit.py").write_text("print('{\"ok\": true}')\n")
    (modules / "pip_audit.py").write_text("""import json, os, sys
from pathlib import Path
mode = os.environ.get("QC_TEST_AUDIT_MODE", "ok")
if mode == "error":
    print("fixture advisory service unavailable", file=sys.stderr)
    raise SystemExit(2)
vulns = [{"id": "fixture-vulnerability"}] if mode == "vulnerable" else []
item = {"name": "fixture-dependency", "version": "1", "vulns": vulns}
if mode == "skipped":
    item["skip_reason"] = "fixture unsupported dependency"
dependencies = [item]
if mode == "editable-project":
    dependencies.append({"name": "quantcore", "skip_reason": "distribution marked as editable"})
Path(sys.argv[sys.argv.index("--output") + 1]).write_text(json.dumps({"dependencies": dependencies}))
raise SystemExit(1 if vulns else 0)
""")
    environment = {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "PYTHONPATH": str(modules)}
    return root, environment


def run_release(root: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/release.sh"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_mac_checksum_fallback_and_stale_artifacts_cannot_contaminate_bundle(release_project):
    root, environment = release_project
    result = run_release(root, environment)
    assert result.returncode == 0, result.stdout + result.stderr
    bundle = root / "dist/release"
    manifest = (bundle / "SHA256SUMS").read_text().splitlines()
    names = []
    for line in manifest:
        digest, name = line.split("  ", 1)
        assert name != "SHA256SUMS", "checksum manifest must never hash its own partial contents"
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
        names.append(name)
    assert not any("stale" in name or "prior.txt" in name for name in names)
    assert len(list(bundle.glob("*.whl"))) == len(list(bundle.glob("quantcore-0.1.0.tar.gz"))) == 1
    assert (bundle / "quantcore-ui-0.1.0.tar.gz").exists()
    assert (bundle / "sbom.cdx.json").exists() and (bundle / "INSTALL.md").exists()
    assert json.loads((bundle / "audit-summary.json").read_text())["status"] == "passed"
    assert (root / "dist/quantcore-stale.whl").read_text() == "unrelated old wheel"
    assert list((root / "dist").glob("release-previous-*/prior.txt"))


def test_intentional_project_editable_omission_is_reported_without_blocking(release_project):
    root, environment = release_project
    environment["QC_TEST_AUDIT_MODE"] = "editable-project"
    result = run_release(root, environment)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((root / "dist/release/audit-summary.json").read_text())
    assert summary["status"] == "passed" and summary["packages_audited"] == 1
    assert summary["intentional_omissions"] == [
        {"name": "quantcore", "reason": "distribution marked as editable"}
    ]


@pytest.mark.parametrize("mode", ["error", "vulnerable", "skipped"])
def test_failed_or_incomplete_audit_preserves_previous_bundle_and_diagnostics(
    release_project, mode
):
    root, environment = release_project
    environment["QC_TEST_AUDIT_MODE"] = mode
    result = run_release(root, environment)
    assert result.returncode != 0
    assert (root / "dist/release/prior.txt").exists()
    assert "[release] bundle:" not in result.stdout
    staging = list((root / "dist").glob(".release-*/bundle/audit-summary.json"))
    assert len(staging) == 1
    summary = json.loads(staging[0].read_text())
    assert summary["status"] != "passed"
    assert (staging[0].parent.parent / "audit.log").exists()
    assert "FAILED" in result.stderr and str(staging[0].parent.parent) in result.stderr
