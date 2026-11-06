"""Invalid corporate-action values stop at the data-quality boundary."""

from pathlib import Path

import numpy as np
import pytest

from quantcore.errors import SnapshotError
from quantcore.quality import run_quality_checks
from quantcore.snapshot import build_snapshot
from tests.test_corporate_backtest import action_panel


@pytest.mark.parametrize("field", ["cash_per_share", "split_ratio"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_action_values_cannot_enter_snapshot(
    tmp_path: Path, field: str, value: float
) -> None:
    panel = action_panel(split=2.0)
    panel.corporate_actions[field] = value
    report = run_quality_checks(panel)
    assert not report.passed
    assert any(issue.check == "corporate_actions" for issue in report.errors)
    with pytest.raises(SnapshotError, match="fails quality checks"):
        build_snapshot(panel, tmp_path / "snapshots")


def test_zero_cash_and_unit_split_are_valid_action_defaults() -> None:
    assert run_quality_checks(action_panel()).passed
