# Release checklist

QuantCore is local-first research software. A release is a verified local bundle,
not a brokerage integration and not a signed Electron installer.

## Current verified state (2026-11-02)

- `docs/features.json` **121/121** passes; known gaps stay documented in `docs/acceptance-report.md` and `docs/PROGRESS.md`.
- Local gates: pytest 240 collected / 238 passed / 2 skipped; ctest 95/95; UI vitest 10; Playwright **18/18** via `make e2e`
  (needs a local Chrome channel); ruff/format/mypy green; `make doctor` ok and `make demo` (<3 s, engine=cpp) verified.
- CI: 5 jobs green — `test (macos-latest)`, `test (ubuntu-latest)`, `windows-smoke`, `ui`, `desktop-windows-package`.
- Unsigned macOS/Windows zips are buildable: the macOS zip via `pnpm -C desktop package:mac` (local), the Windows zip in
  the `desktop-windows-package` CI job. There is **no signing or notarization**, and the Windows zip has not been
  install/run verified on a real Windows machine; Windows C++ support remains unverified (pure-Python smoke only).
- Playwright E2E is local-only (`make e2e`); it is not part of GitHub CI.

## Gate

- [ ] `make setup && make ci-local` green (pytest, ctest, ruff format/check, mypy, C++ verify, UI build/test).
- [ ] `make e2e` green against a real `qc serve` (Playwright **18**, no console/page errors or horizontal overflow; local Chrome channel required).
- [ ] `uv run pytest -q` count documented in `docs/acceptance-report.md`.
- [ ] No real order routing, no network calls at runtime, synthetic data labelled `SYNTHETIC`.
- [ ] `docs/features.json` truthfully lists only verified features; known gaps stay documented.
- [ ] macOS/Ubuntu CI green; Windows pure-Python smoke and unsigned package build green, but Windows install/run remains unverified.

## Bundle

- [ ] `make release` → `dist/release/quantcore-<version>-py3-none-any.whl`, sdist, `quantcore-ui-<version>.tar.gz`, `sbom.cdx.json`, `SHA256SUMS`.
- [ ] `make audit` generates SBOM + `dist/pip-audit.json`; 0 known vulnerabilities or documented exceptions.
- [ ] `python scripts/sbom.py` parses `uv.lock` + `ui/pnpm-lock.yaml` offline; component counts are plausible.
- [ ] Checksums verify: `cd dist/release && sha256sum -c SHA256SUMS` (macOS: `shasum -a 256 -c`).
- [ ] `uv run qc serve --ui-dir ui/dist` from a clean checkout shows the eight-page UI, `/health`, `/api/meta`.
- [ ] `uv run pytest -m e2e` / `make e2e` is documented as requiring a local Chrome channel.

## Publishing

- [ ] GitHub tag matches `pyproject.toml` version; release notes list verified features and known gaps.
- [ ] Do not claim signed/notarized installers, a verified Windows install/run, real-broker execution or guaranteed alpha.
- [ ] Attach the bundle plus `SHA256SUMS`; keep `docs/features.json` and acceptance report current.
