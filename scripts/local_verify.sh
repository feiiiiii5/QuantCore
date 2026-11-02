#!/usr/bin/env bash
# Local verification helper: offline checks with per-step timing and a PASS/FAIL summary.
#
#   bash scripts/local_verify.sh            # doctor + test-quick
#   bash scripts/local_verify.sh --full     # + lint, test (build+pytest+ctest), verify-cpp
#   bash scripts/local_verify.sh --e2e      # + make e2e (needs a local Chrome)
#
# Every selected step runs even if an earlier one fails, so the summary is complete;
# the script exits 1 when any step failed.  It makes no network requests of its own and
# assumes "make setup" already fetched the dependencies (first-time installs use the
# mirrors in docs/DEV-SETUP.md).  See docs/LOCAL-TESTING.md for the full matrix.
set -euo pipefail
cd "$(dirname "$0")/.."

FULL=0
E2E=0

usage() {
  cat <<'USAGE'
Usage: bash scripts/local_verify.sh [--full] [--e2e]

  (no flags)  doctor + test-quick (about 1-2 minutes after a build)
  --full      also lint, test (build + pytest + ctest), verify-cpp
  --e2e       also make e2e (UI build + isolated qc serve + Playwright; needs Chrome)
  --help      show this help

All steps run even when one fails; the summary lists PASS/FAIL and wall seconds per
step, and the script exits 1 if any step failed.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --e2e) E2E=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[verify-local] unknown option: $arg (use --full / --e2e / --help)" >&2
      exit 2
      ;;
  esac
done

SUMMARY_FILE=$(mktemp /tmp/qc-verify.XXXXXX)
trap 'rm -f "$SUMMARY_FILE"' EXIT

run_step() {
  local name="$1"
  shift
  local started elapsed code status
  started=$(date +%s)
  echo ""
  echo "[verify-local] ==> $name: $*"
  set +e
  "$@"
  code=$?
  set -e
  elapsed=$(( $(date +%s) - started ))
  if [ "$code" -eq 0 ]; then
    status=PASS
    echo "[verify-local] <== $name: PASS ($elapsed s)"
  else
    status=FAIL
    echo "[verify-local] <== $name: FAIL (exit $code, $elapsed s)" >&2
  fi
  printf '  %-4s %-11s %3ss  %s\n' "$status" "$name" "$elapsed" "$*" >> "$SUMMARY_FILE"
}

echo "[verify-local] local verification (offline; full=$FULL e2e=$E2E)"

run_step doctor make doctor
run_step test-quick make test-quick

if [ "$FULL" -eq 1 ]; then
  run_step lint make lint
  run_step test make test
  run_step verify-cpp make verify-cpp
fi

if [ "$E2E" -eq 1 ]; then
  run_step e2e make e2e
fi

echo ""
echo "[verify-local] summary"
cat "$SUMMARY_FILE"
FAILED=$(grep -c '^  FAIL' "$SUMMARY_FILE" || true)
echo ""
if [ "$FAILED" -ne 0 ]; then
  echo "[verify-local] FAILED: $FAILED step(s) failed" >&2
  exit 1
fi
echo "[verify-local] passed"
