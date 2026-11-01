"""M4-005 subprocess strategy worker: isolation boundary and shape validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quantcore.errors import StrategyValidationError
from quantcore.strategy.sandbox_worker import generate_targets_sandboxed


def test_worker_generates_weights(synthetic_snapshot, tmp_path: Path) -> None:
    module = tmp_path / "worker_plugin.py"
    module.write_text(
        """from quantcore.strategy.base import Strategy
import numpy as np

class WorkerPlugin(Strategy):
    name = "worker_plugin"
    def generate_weights(self, panel):
        weights = np.full((panel.n_time, panel.n_sec), np.nan)
        weights[0] = 1.0 / panel.n_sec
        return weights
""",
        encoding="utf-8",
    )
    weights = generate_targets_sandboxed(module, synthetic_snapshot.path)
    assert weights.shape == (
        len(synthetic_snapshot.calendar().dates),
        len(synthetic_snapshot.securities()),
    )
    assert np.isfinite(weights[0]).all()
    assert np.allclose(weights[0].sum(), 1.0)


def test_worker_rejects_unsafe_module(synthetic_snapshot, tmp_path: Path) -> None:
    module = tmp_path / "bad_plugin.py"
    module.write_text("import os\nos.system('echo nope')\n", encoding="utf-8")
    with pytest.raises(StrategyValidationError):
        generate_targets_sandboxed(module, synthetic_snapshot.path)
