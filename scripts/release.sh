#!/usr/bin/env bash
# Build a local release bundle; no installation or publication.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec uv run --no-sync python scripts/release_bundle.py
