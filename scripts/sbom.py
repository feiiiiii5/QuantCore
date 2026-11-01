#!/usr/bin/env python3
"""Generate an offline CycloneDX SBOM from uv.lock + pnpm-lock.yaml.

No network: the lockfiles are the source of truth. Python packages come from
``uv.lock`` (PEP 503-ish names); frontend packages come from the pnpm lockfile.
Run ``python scripts/sbom.py --out dist/sbom.cdx.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:  # PyYAML is a dev-only dependency; fall back to a tiny parser when absent.
    import yaml
except ImportError:  # pragma: no cover - exercised only in minimal environments
    yaml = None


def _pypi_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def python_components(root: Path) -> list[dict[str, Any]]:
    lock = root / "uv.lock"
    if not lock.exists():
        return []
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for package in data.get("package", []):
        name = str(package.get("name", "")).strip()
        version = str(package.get("version", "")).strip()
        if not name or not version:
            continue
        key = (_pypi_name(name), version)
        if key in seen:
            continue
        seen[key] = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{_pypi_name(name)}@{version}",
            "scope": "required",
            "properties": [{"name": "quantcore:ecosystem", "value": "pypi"}],
        }
    return sorted(seen.values(), key=lambda item: (item["name"].lower(), item["version"]))


def _npm_name_version(key: str) -> tuple[str, str] | None:
    text = str(key).strip().lstrip("/")
    if not text or text.startswith("."):
        return None
    # pnpm keys may be "name@version", "@scope/name@version", or include peer suffixes "(...)".
    text = text.split("(", 1)[0]
    if text.startswith("@"):
        at = text.rfind("@")
        if at <= 0:
            return None
        return text[:at], text[at + 1 :]
    at = text.rfind("@")
    if at <= 0:
        return None
    return text[:at], text[at + 1 :]


def npm_components(root: Path) -> list[dict[str, Any]]:
    lock = root / "ui" / "pnpm-lock.yaml"
    if not lock.exists():
        return []
    text = lock.read_text(encoding="utf-8")
    packages: dict[str, Any] = {}
    if yaml is not None:
        loaded = yaml.safe_load(text) or {}
        packages = loaded.get("packages") or {}
    else:  # pragma: no cover - best-effort fallback
        in_packages = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "packages:":
                in_packages = True
                continue
            if in_packages and stripped.startswith("snapshots:"):
                break
            if in_packages and stripped.startswith("/") and stripped.endswith(":"):
                packages[stripped[:-1].strip()] = {}
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_key in packages:
        name_version = _npm_name_version(str(raw_key))
        if name_version is None:
            continue
        name, version = name_version
        if not version or version.startswith("link:"):
            continue
        key = (name, version)
        if key in seen:
            continue
        quoted = quote(name, safe="@").replace("@", "%40")
        seen[key] = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{quoted}@{quote(version, safe='')}",
            "scope": "required",
            "properties": [{"name": "quantcore:ecosystem", "value": "npm"}],
        }
    return sorted(seen.values(), key=lambda item: (item["name"].lower(), item["version"]))


def build_bom(root: Path) -> dict[str, Any]:
    components = python_components(root) + npm_components(root)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000000",
        "version": 1,
        "metadata": {
            "timestamp": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "tools": {"components": [{"type": "application", "name": "quantcore-sbom", "version": "0.1.0"}]},
            "component": {"type": "application", "name": "QuantCore", "version": _project_version(root)},
        },
        "components": components,
    }


def _project_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", "0.0.0"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    bom = build_bom(args.root)
    out = args.out or (args.root / "dist" / "sbom.cdx.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for component in bom["components"]:
        eco = next((p["value"] for p in component.get("properties", []) if p["name"] == "quantcore:ecosystem"), "other")
        counts[eco] = counts.get(eco, 0) + 1
    print(f"wrote {out}: {len(bom['components'])} components {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
