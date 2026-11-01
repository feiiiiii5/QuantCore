"""Parent-side helper for the subprocess strategy worker (M4-005)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from ..errors import StrategyValidationError


def generate_targets_sandboxed(
    module_path: str | Path,
    snapshot_dir: str | Path,
    *,
    timeout: int = 120,
) -> np.ndarray:
    """Run a custom strategy module in a child Python process and load its weights."""
    module = Path(module_path).resolve()
    snapshot = Path(snapshot_dir).resolve()
    if not module.is_file():
        raise StrategyValidationError(f"strategy module not found: {module}")
    if not (snapshot / "manifest.json").is_file():
        raise StrategyValidationError(f"snapshot directory is invalid: {snapshot}")
    with tempfile.TemporaryDirectory(prefix="qc-strategy-worker-") as tmp:
        output = Path(tmp) / "weights.npy"
        env = dict(os.environ)
        env.setdefault("QC_STRATEGY_WORKER", "1")
        command = [
            sys.executable,
            "-m",
            "quantcore.strategy.worker",
            "--module",
            str(module),
            "--snapshot",
            str(snapshot),
            "--output",
            str(output),
            "--cpu-seconds",
            str(max(5, min(int(timeout), 600))),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise StrategyValidationError(f"strategy worker timed out after {timeout}s") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-800:]
            raise StrategyValidationError(f"strategy worker failed: {detail}")
        if not output.is_file():
            raise StrategyValidationError("strategy worker produced no weights file")
        weights = np.load(output)
    if weights.ndim != 2:
        raise StrategyValidationError(f"strategy worker returned non-2D weights: {weights.shape}")
    return np.ascontiguousarray(weights, dtype=np.float64)


__all__ = ["generate_targets_sandboxed"]
