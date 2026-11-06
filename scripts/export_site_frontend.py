#!/usr/bin/env python3
"""Build the real QuantCore frontend for its existing private Site; no backend data."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / ".openai/hosting.json").read_text())
    destination = root / ".sites/quantcore"
    identity = destination / ".openai/hosting.json"
    if (
        identity.exists()
        and json.loads(identity.read_text())["project_id"] != manifest["project_id"]
    ):
        raise ValueError("the export directory belongs to a different Site")
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text(json.dumps(manifest, indent=2) + "\n")
    environment = os.environ.copy()
    for key in (
        "SSH_AUTH_SOCK",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        environment.pop(key, None)
    environment["VITE_QC_DEFAULT_API_BASE"] = "http://127.0.0.1:8000"
    for command in (
        ["pnpm", "exec", "tsc", "-b"],
        ["pnpm", "exec", "vite", "build", "--outDir", str(destination / "dist"), "--emptyOutDir"],
    ):
        subprocess.run(command, cwd=root / "ui", env=environment, check=True, timeout=1200)
    frontend = destination / "frontend-source"
    for name in ("src", "public"):
        if (root / "ui" / name).exists():
            shutil.copytree(root / "ui" / name, frontend / name, dirs_exist_ok=True)
    for source in (root / "ui").iterdir():
        if source.is_file() and (
            source.name in {"package.json", "pnpm-lock.yaml", "index.html", "vite.config.ts"}
            or source.name.startswith("tsconfig")
        ):
            shutil.copy2(source, frontend / source.name)
    (destination / "dist/_redirects").write_text("/* /index.html 200\n")
    (destination / "README.md").write_text(
        "# QuantCore private test frontend\n\n"
        "The served assets are the actual React workbench; its source is in frontend-source/.\n"
        "The default API is http://127.0.0.1:8000. Python, C++20, data and virtual accounts "
        "run on the visitor's own computer. No API token or warehouse is published.\n\n"
        "Start QuantCore with --allow-origin matching the Site, then enter the local "
        "bearer token in Settings. Browser loopback-network permission may be required.\n"
        "This export contains no cloud-hosted Python/C++ backend.\n"
    )
    print(json.dumps({"project_id": manifest["project_id"], "export": str(destination)}))


if __name__ == "__main__":
    main()
