#!/usr/bin/env bash
# Build a local, offline-verifiable release bundle (wheel+sdist+UI+SBOM+checksums).
# This is not an Electron installer and does not publish anything.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(uv run python -c 'import tomllib,pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')"
OUT="$ROOT/dist/release"
rm -rf "$OUT"
mkdir -p "$OUT"
echo "[release] building wheel/sdist for $VERSION"
uv build
echo "[release] building UI"
pnpm -C ui build
echo "[release] packaging UI dist"
tar -czf "$OUT/quantcore-ui-$VERSION.tar.gz" -C ui dist
python scripts/sbom.py --out "$OUT/sbom.cdx.json"
cp dist/quantcore-"$VERSION".whl "$OUT"/ 2>/dev/null || cp dist/*.whl "$OUT"/
cp dist/quantcore-"$VERSION".tar.gz "$OUT"/ 2>/dev/null || cp dist/*.tar.gz "$OUT"/
cp README.md "$OUT/README.md"
cp docs/QUICKSTART.md "$OUT/QUICKSTART.md" 2>/dev/null || true
( cd "$OUT" && sha256sum * > SHA256SUMS 2>/dev/null || shasum -a 256 * > SHA256SUMS )
echo "[release] bundle: $OUT"
ls -lh "$OUT"
