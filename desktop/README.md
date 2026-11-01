# QuantCore Desktop (Electron dev shell)

This is a **local research/simulation** shell: it spawns `uv run qc serve` and renders the
same React UI in an Electron window. It does not connect to a broker, does not place real
orders and does not replace the local service security model.

```bash
pnpm -C ui build                 # required: UI assets served by qc
pnpm -C desktop install          # Electron binary
env -u ELECTRON_RUN_AS_NODE pnpm -C desktop start
```

Headless smoke (used by `make desktop-smoke`):

```bash
env -u ELECTRON_RUN_AS_NODE QC_HEADLESS=1 QC_SMOKE=1 pnpm -C desktop start
```

The shell chooses a random token, starts `qc serve` on `127.0.0.1:8787`, waits for `/health`,
then loads `/?token=...`; the token is removed from the address bar by the same UI bootstrap
used in the browser. Closing the app stops the child server.

Not included yet: signed macOS/Windows installers, auto-update, code signing. `M10-001`
covers the dev shell; packaging remains a documented gap.
