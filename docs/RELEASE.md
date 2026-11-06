# Local release bundle

Updated 2026-11-07. QuantCore supports local research and simulation on macOS/Linux.
The native C++ wheel is platform/Python specific; it is not a `py3-none-any` wheel.
This bundle is not a signed/notarized installer, a cloud backend, or a verified full Windows backend.
Current validation results belong in [acceptance-report.md](acceptance-report.md), not a frozen test count here.

## Prepare and build

Use an already installed development environment (this run: Python 3.12), uv, the C++ build toolchain,
frontend dependencies and pip-audit. `make release` does not install the project environment or run all quality gates.
The wheel/sdist build can download build dependencies, and vulnerability lookup needs its advisory service.
The resulting bundle can be checksum-verified offline; installing its runtime dependencies is not guaranteed offline.

```sh
make release
```

The entrypoint uses `uv run --no-sync` and a standard-library packager. Every run builds in a unique
`dist/.release-<id>/bundle/` directory. It requires exactly one wheel and one source distribution for the
current `pyproject.toml` version, validates wheel metadata and the presence of `_qcore`, then builds and archives the UI.
The build explicitly selects the packager's interpreter; generated installation commands use its Python major/minor version.
It never falls back to copying arbitrary older files from `dist/`.

Only after a successful audit and checksum generation is the new bundle moved to `dist/release/`.
An existing successful bundle is preserved as `dist/release-previous-<id>/`; unrelated `dist/` outputs remain intact.
Build, frontend, SBOM and audit logs remain in the printed staging directory, outside the completed bundle.

## Contents and checksums

- One current native wheel, with its actual CPython/ABI/platform filename.
- `quantcore-<version>.tar.gz` source distribution.
- `quantcore-ui-<version>.tar.gz`, containing the freshly built `dist/` frontend directory.
- `sbom.cdx.json`: offline inventory derived from Python and frontend lockfiles.
- `pip-audit.json` and `audit-summary.json`: this run's dependency audit report and explicit outcome.
- `INSTALL.md`: wheel installation, UI extraction, local self-check, synthetic demo and server commands.
- `SHA256SUMS`: SHA-256 for payload files, excluding the manifest itself.

Checksums are generated with Python, so creation does not depend on GNU `sha256sum` or macOS `shasum` availability.
From the finished bundle, either verification command can be used:

```sh
cd dist/release
sha256sum -c SHA256SUMS
# macOS alternative:
shasum -a 256 -c SHA256SUMS
```

Checksums detect corruption; they do not authenticate the publisher. Review the wheel tag against the receiving
machine/Python version. A source distribution requires a compatible C++ toolchain; it is not an installer fallback.

## Audit and failure behavior

The packager invokes pip-audit against the current interpreter's installed dependency directory, omitting editable
distributions. It does not reuse a stale `dist/pip-audit.json`. This is a build-environment audit, not a proof that
the wheel plus every future target environment or every lockfile entry has been audited.

`audit-summary.json` records the process exit code, dependency count, known vulnerabilities and skipped dependencies.
A nonzero process exit, absent/invalid report, known vulnerabilities or unreviewed skipped dependencies prevents success.
The editable QuantCore source checkout is the sole intentional omission, recorded explicitly in the summary;
other skipped packages still block completion. Project code is verified separately by tests and the emitted wheel install.
Missing audit tooling, service/network failures and incomplete audits must not be reported as zero vulnerabilities passed.
The current pipeline has no automatic exception approval; resolve/review the cause before producing a successful bundle.

On failure the command exits nonzero, prints `FAILED` and the diagnostics location, and preserves the previous successful
`dist/release/`. The new staging directory contains completed build artifacts, `audit-summary.json` where available,
and logs such as `build.log`, `ui-build.log`, `sbom.log` and `audit.log`. Do not publish an incomplete staging directory.

## Release validation

Before publishing, independently verify the intended commit, native engine behavior, relevant tests and actual bundle install.
Follow the [local test guide](LOCAL-TESTING.md) and record the commands/results in the acceptance report.
Use a clean matching macOS/Linux environment to install the emitted wheel and run `qc doctor`, `qc demo`, replay and
the bundled UI against `qc serve --ui-dir ui/dist`. UI browser checks require a real supported browser.

The unsigned desktop shell, Windows smoke coverage and private Sites frontend are separate delivery paths.
They do not establish signed installers, Windows C++ install/run support, real broker execution, production readiness or returns.
This script builds local files and does not tag, push, upload or publish them.
