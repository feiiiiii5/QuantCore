#!/usr/bin/env bash
# Local end-to-end gate: build UI, start the real qc-server, drive Playwright against it.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${QC_E2E_PORT:-8123}"
TOKEN="${QC_E2E_TOKEN:-test-token}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc-e2e.XXXXXX")"
SERVER_LOG="$TMP/server.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "[e2e] building UI..."
pnpm -C ui build >/dev/null
cp -R ui/dist "$TMP/ui"

echo "[e2e] starting qc serve on 127.0.0.1:${PORT} (token=${TOKEN})"
uv run qc serve \
  --port "$PORT" \
  --token "$TOKEN" \
  --data-root "$TMP/data" \
  --experiments-root "$TMP/experiments" \
  --ui-dir "$TMP/ui" \
  --no-open >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if ! curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "[e2e] server failed to start" >&2
  cat "$SERVER_LOG" >&2
  exit 1
fi

echo "[e2e] running Playwright..."
(
  cd ui
  QC_E2E_BASE="http://127.0.0.1:${PORT}" QC_E2E_TOKEN="$TOKEN" pnpm exec playwright test
)

echo "[e2e] passed"
