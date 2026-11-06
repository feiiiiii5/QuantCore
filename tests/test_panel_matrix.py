"""Matrix assembly preserves pivot semantics and all built-in strategy signals."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore.data.matrices import MatrixLayout
from quantcore.data.panel import PANEL_FIELDS, PanelData
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
from quantcore.strategy.base import PanelView
from quantcore.templates.registry import create_template, template_ids


def reference_matrix(bars, dates, sec_ids, name, fill=np.nan):
    pivot = bars[["date", "sec_id", name]].pivot_table(
        index="date", columns="sec_id", values=name, aggfunc="last"
    )
    values = pivot.reindex(index=dates, columns=sec_ids).to_numpy(dtype=np.float64)
    return values if np.isnan(fill) else np.where(np.isnan(values), fill, values)


@pytest.fixture()
def irregular_panel() -> PanelData:
    panel = generate_synthetic_panel(
        SyntheticConfig(n_sec=3, start="2023-01-03", end="2023-12-29", seed=17)
    )
    bars = panel.bars.iloc[2:].copy()
    duplicate = bars.iloc[[0, 0, 1]].copy()
    duplicate["close"] = [42.0, np.nan, np.nan]
    duplicate["amount"] = [np.nan, 99.0, np.nan]
    outside = bars.iloc[[0, 0]].copy()
    outside.iloc[0, outside.columns.get_loc("date")] = 19990101
    outside.iloc[1, outside.columns.get_loc("sec_id")] = "OUTSIDE"
    panel.bars = pd.concat([bars, duplicate, outside], ignore_index=True)
    # Preserve source order within a duplicate group while scrambling all other
    # rows, then reorder the security axis independently of the source table.
    panel.bars = panel.bars.sort_values("sec_id", ascending=False, kind="stable")
    panel.securities = panel.securities.iloc[::-1].reset_index(drop=True)
    return panel


@pytest.mark.parametrize("fill", [np.nan, 0.0, -123.0])
def test_all_fields_match_pivot_with_missing_duplicates_and_outside_rows(irregular_panel, fill):
    panel = irregular_panel
    layout = MatrixLayout(panel.bars, panel.dates, panel.sec_ids)
    for name in PANEL_FIELDS:
        expected = reference_matrix(panel.bars, panel.dates, panel.sec_ids, name, fill)
        np.testing.assert_array_equal(panel.matrix(name, fill), expected)
        np.testing.assert_array_equal(layout.matrix(name, fill), expected)


def test_view_truncation_and_unknown_field(irregular_panel):
    panel = irregular_panel
    view = PanelView(panel, cut=2)
    for name in ("close", "amount", "st"):
        expected = reference_matrix(panel.bars, panel.dates, panel.sec_ids, name)[:3]
        np.testing.assert_array_equal(view.field(name), expected)
        assert view.field(name) is view.field(name)
    with pytest.raises(KeyError, match="unknown field: absent"):
        panel.matrix("absent")
    with pytest.raises(KeyError, match="unknown field: absent"):
        view.field("absent")


def test_mutable_panel_and_new_views_use_current_rows(irregular_panel):
    panel = irregular_panel
    panel.matrix("close")
    PanelView(panel).field("close")
    panel.bars = panel.bars.iloc[::-1].copy()
    panel.bars["close"] = np.arange(len(panel.bars), dtype=float)
    panel.bars.iloc[0, panel.bars.columns.get_loc("sec_id")] = panel.sec_ids[0]
    expected = reference_matrix(panel.bars, panel.dates, panel.sec_ids, "close")
    np.testing.assert_array_equal(panel.matrix("close"), expected)
    np.testing.assert_array_equal(PanelView(panel).field("close"), expected)


def test_repeated_security_axis_matches_pivot(irregular_panel):
    panel = irregular_panel
    panel.securities = panel.securities.iloc[[0, 0, 1]]
    expected = reference_matrix(panel.bars, panel.dates, panel.sec_ids, "close")
    np.testing.assert_array_equal(panel.matrix("close"), expected)


@pytest.fixture(scope="module")
def strategy_panel():
    return generate_synthetic_panel(
        SyntheticConfig(n_sec=8, start="2022-01-03", end="2023-06-30", seed=31)
    )


@pytest.mark.parametrize("template", template_ids())
def test_old_and_new_template_weights_match_pivot(strategy_panel, template, monkeypatch):
    actual = create_template(template).generate_targets(strategy_panel)

    def pivot_matrix(self, name, fill=np.nan):
        return reference_matrix(self.bars, self.dates, self.sec_ids, name, fill)

    monkeypatch.setattr(MatrixLayout, "matrix", pivot_matrix)
    expected = create_template(template).generate_targets(strategy_panel)
    np.testing.assert_array_equal(actual, expected)
