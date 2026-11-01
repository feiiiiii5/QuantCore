"""Subprocess strategy worker: generate target weights in an isolated child process.

The parent writes no untrusted code into the qc-server process. The worker:
1. limits CPU/address space/file size (POSIX; best effort),
2. loads one immutable snapshot,
3. audits/imports the strategy module through :mod:`quantcore.strategy.sandbox`,
4. calls ``generate_targets`` and writes a ``.npy`` weight matrix.

It is still a local, trusted-plugin facility (not a hard multi-tenant sandbox), but it
moves arbitrary custom strategy code out of the API server process.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _limit_resources(cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except (ValueError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--snapshot", required=True, help="snapshot directory (manifest.json)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cpu-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    _limit_resources(max(1, args.cpu_seconds))
    import numpy as np

    from quantcore.snapshot.reader import SnapshotManifest
    from quantcore.strategy.sandbox import load_strategy_module

    snapshot_dir = Path(args.snapshot).resolve()
    manifest = SnapshotManifest.read(snapshot_dir / "manifest.json")
    from quantcore.snapshot.reader import Snapshot

    snapshot = Snapshot(root=snapshot_dir, manifest=manifest)
    panel = snapshot.to_panel_data()
    strategy = load_strategy_module(Path(args.module).resolve())
    weights = np.asarray(strategy.generate_targets(panel), dtype=np.float64)
    if weights.shape != (panel.n_time, panel.n_sec):
        raise SystemExit(
            f"strategy returned shape {weights.shape}, expected {(panel.n_time, panel.n_sec)}"
        )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, weights)
    return 0


if __name__ == "__main__":
    sys.exit(main())
