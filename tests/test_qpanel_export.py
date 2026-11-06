"""Fast export keeps the exact existing field layout and duplicate-row semantics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantcore import require_panel
from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.engine import run_backtest, run_backtest_batch
from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PANEL_FIELDS
from quantcore.snapshot.qpanel import (
    QPANEL_LAYOUT,
    QPANEL_SCHEMA_VERSION,
    _securities_payload,
    qpanel_field,
    write_qpanel,
)


@pytest.mark.parametrize("irregular", [False, True])
def test_export_matches_existing_pivot_bytes(small_panel, tmp_path: Path, irregular: bool) -> None:
    panel = small_panel.select(end=20221230)
    if irregular:
        panel.securities = panel.securities.iloc[::-1].reset_index(drop=True)
        duplicate = panel.bars.iloc[[0]].copy()
        duplicate["open"] = 123.0
        duplicate["close"] = np.nan  # last non-null is selected independently per field
        outside = panel.bars.iloc[[1]].copy()
        outside["date"] = 20250106  # export excludes dates outside its calendar
        unknown = panel.bars.iloc[[2]].copy()
        unknown["sec_id"] = "outside-panel"
        panel.bars = pd.concat([panel.bars, duplicate, outside, unknown], ignore_index=True)
        panel.calendar = TradingCalendar((*panel.calendar.dates, 20230103))
    actual = tmp_path / "actual.qpanel"
    reference = tmp_path / "reference.qpanel"
    write_qpanel(panel, actual)
    module = require_panel()
    writer = module.PanelWriter(
        panel.n_sec,
        panel.n_time,
        list(panel.calendar.dates),
        _securities_payload(panel),
    )
    for field in PANEL_FIELDS:
        writer.add_field(field, QPANEL_LAYOUT, np.ascontiguousarray(panel.matrix(field)))
    metadata = panel.security_meta()
    metadata["qpanel_schema_version"] = QPANEL_SCHEMA_VERSION
    writer.set_metadata(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    writer.write(str(reference))
    assert actual.read_bytes() == reference.read_bytes()
    opened = module.Panel.open(str(actual))
    for field in PANEL_FIELDS:
        np.testing.assert_array_equal(qpanel_field(opened, field), panel.matrix(field))


def test_serialized_panel_keeps_native_batch_thread_determinism(
    small_panel, monthly_weights
) -> None:
    targets = [monthly_weights, np.asfortranarray(monthly_weights * 0.5)]
    expected = [run_backtest(small_panel, target, BacktestConfig()) for target in targets]
    for threads in (1, 2, 4):
        actual = run_backtest_batch(small_panel, targets, BacktestConfig(), threads=threads)
        for left, right in zip(actual, expected, strict=True):
            assert left.engine_backend == right.engine_backend == "cpp"
            np.testing.assert_array_equal(left.equity, right.equity)
            np.testing.assert_array_equal(left.cash, right.cash)
            np.testing.assert_array_equal(left.market_value, right.market_value)
            pd.testing.assert_frame_equal(left.trades, right.trades)
            pd.testing.assert_frame_equal(left.final_positions, right.final_positions)
            assert left.metrics == right.metrics
