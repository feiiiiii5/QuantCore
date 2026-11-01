# Release checklist

QuantCore is local-first research software. A release is a verified local bundle,
not a brokerage integration and not an Electron installer.

## Gate

- [ ] `make setup && make ci-local` green (pytest, ctest, ruff format/check, mypy, C++ verify, UI build/test).
- [ ] `make e2e` green against a real `qc serve` (Playwright 15+, no console/page errors or horizontal overflow).
- [ ] `uv run pytest -q` count documented in `docs/acceptance-report.md`.
- [ ] No real order routing, no network calls at runtime, synthetic data labelled `SYNTHETIC`.
- [ ] `docs/features.json` truthfully lists only verified features; known gaps stay documented.
- [ ] macOS/Ubuntu CI green; Windows remains explicitly unverified.

## Bundle

- [ ] `make release` → `dist/release/quantcore-<version>-py3-none-any.whl`, sdist, `quantcore-ui-<version>.tar.gz`, `sbom.cdx.json`, `SHA256SUMS`.
- [ ] `python scripts/sbom.py` parses `uv.lock` + `ui/pnpm-lock.yaml` offline; component counts are plausible.
- [ ] Checksums verify: `cd dist/release && sha256sum -c SHA256SUMS` (macOS: `shasum -a 256 -c`).
- [ ] `uv run qc serve --ui-dir ui/dist` from a clean checkout shows the eight-page UI, `/health`, `/api/meta`.
- [ ] `uv run pytest -m e2e` / `make e2e` is documented as requiring a local Chrome channel.

## Publishing

- [ ] GitHub tag matches `pyproject.toml` version; release notes list verified features and known gaps.
- [ ] Do not claim Electron, Windows installer, real-broker execution or guaranteed alpha.
- [ ] Attach the bundle plus `SHA256SUMS`; keep `docs/features.json` and acceptance report current.
