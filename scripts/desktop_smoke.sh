#!/usr/bin/env bash
# Build the UI, install Electron, and verify that the desktop shell can load the real UI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
pnpm -C ui build >/dev/null
pnpm -C desktop install --frozen-lockfile --prefer-offline >/dev/null
# Some CI containers export ELECTRON_RUN_AS_NODE=1; unset it so Electron starts as a browser.
env -u ELECTRON_RUN_AS_NODE QC_HEADLESS=1 QC_SMOKE=1 QC_REPO_ROOT="$ROOT" pnpm -C desktop start
