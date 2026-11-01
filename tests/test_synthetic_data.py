"""Tests for the deterministic SYNTHETIC A-share panel generator."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from quantcore.calendar import TradingCalendar, to_date_int
from quantcore.data.panel import PANEL_FIELDS
from quantcore.data.synthetic import (
    SYNTHETIC_DISCLAIMER,
    SyntheticConfig,
    generate_quick_panel,
    generate_synthetic_panel,
)
from quantcore.quality import run_quality_checks


def test_schema_and_synthetic_labelling(small_panel) -> None:
    assert small_panel.schema_problems() == []
    assert small_panel.meta["synthetic"] is True
    assert small_panel.meta["disclaimer"] == SYNTHETIC_DISCLAIMER
    assert set(small_panel.bars["source"].unique()) == {"SYNTHETIC"}
    assert set(small_panel.securities["source"].unique()) == {"SYNTHETIC"}
    for field in PANEL_FIELDS:
        assert field in small_panel.bars.columns, field


def test_calendar_contains_weekdays_only(small_panel) -> None:
    dates = list(small_panel.calendar.dates)
    assert dates == sorted(set(dates))
    for date in dates:
        weekday = dt.date(date // 10000, (date // 100) % 100, date % 100).weekday()
        assert weekday < 5
    assert set(small_panel.bars["date"].unique()).issubset(set(dates))


def test_deterministic_seeded_generation() -> None:
    config = SyntheticConfig(n_sec=12, start="2023-01-03", end="2024-12-31", seed=5)
    first = generate_synthetic_panel(config)
    second = generate_synthetic_panel(config)
    assert first.content_hash() == second.content_hash()
    other = generate_synthetic_panel(
        SyntheticConfig(n_sec=12, start="2023-01-03", end="2024-12-31", seed=6)
    )
    assert first.content_hash() != other.content_hash()


def test_scenarios_present(small_panel) -> None:
    scenarios = small_panel.meta["scenarios"]
    bars = small_panel.bars
    assert scenarios["limit_up_days"] > 0
    assert scenarios["suspended_rows"] > 0
    assert scenarios["st_rows"] > 0
    assert scenarios["one_line_days"] > 0
    assert scenarios["st_secs"]
    assert scenarios["suspended_secs"]
    assert scenarios["ex_rights_secs"]
    assert not small_panel.corporate_actions.empty
    one_line = bars[(bars["high"] == bars["low"]) & (~bars["suspended"]) & (bars["volume"] <= 600)]
    assert len(one_line) > 0
    sealed = (one_line["close"] >= one_line["limit_up"] - 0.011) | (
        one_line["close"] <= one_line["limit_down"] + 0.011
    )
    assert sealed.all()
    for sec in scenarios["delisted_secs"]:
        assert bars[bars["sec_id"] == sec]["date"].max() < small_panel.calendar.dates[-1]
    for sec in scenarios["ipo_secs"]:
        assert bars[bars["sec_id"] == sec]["date"].min() > small_panel.calendar.dates[0]


def test_price_rules_are_consistent(small_panel) -> None:
    bars = small_panel.bars
    tradable = bars[~bars["suspended"]]
    assert (tradable["high"] >= tradable["low"]).all()
    assert (tradable["low"] <= tradable["close"] + 0.011).all()
    assert (tradable["close"] <= tradable["high"] + 0.011).all()
    assert (tradable["close"] <= tradable["limit_up"] + 0.011).all()
    assert (tradable["close"] >= tradable["limit_down"] - 0.011).all()
    boards = small_panel.securities.set_index("sec_id")["board"]
    st_rows = bars[bars["st"]].copy()
    st_rows["board"] = st_rows["sec_id"].map(boards)
    main_st = st_rows[st_rows["board"] == "MAIN"]
    assert not main_st.empty
    expected_up = np.round(main_st["pre_close"] * 1.05, 2)
    assert np.allclose(main_st["limit_up"], expected_up, atol=0.02)


def test_quality_checks_pass(small_panel) -> None:
    report = run_quality_checks(small_panel)
    assert report.passed, [issue.message for issue in report.errors]


def test_matrix_export_matches_panel(small_panel) -> None:
    close = small_panel.matrix("close")
    assert close.shape == (small_panel.n_time, small_panel.n_sec)
    assert np.isfinite(close).sum() == len(small_panel.bars)
    suspended = small_panel.matrix("suspended")
    assert np.nanmax(suspended) <= 1.0
    assert np.isnan(close).any(), "IPO/delisting securities should leave gaps"


def test_quick_panel_factory() -> None:
    panel = generate_quick_panel(n_sec=8, seed=3)
    assert panel.n_sec == 8
    assert panel.meta["seed"] == 3


def test_generator_validates_config() -> None:
    with pytest.raises(ValueError):
        SyntheticConfig(n_sec=0)
    with pytest.raises(ValueError):
        SyntheticConfig(start="2024-01-01", end="2023-01-01")
    with pytest.raises(ValueError):
        SyntheticConfig(board_mix=(0.5, 0.5, 0.5, 0.5))


def test_twenty_year_calendar_supported() -> None:
    calendar = TradingCalendar.weekdays("2005-01-03", "2024-12-31")
    assert len(calendar) > 4500
    assert calendar.dates[0] == to_date_int("2005-01-03")


@pytest.mark.bench
def test_full_market_security_scale() -> None:
    """5500-security parameterisation (short horizon; full 20y would need ~2 GB)."""
    panel = generate_synthetic_panel(
        SyntheticConfig(n_sec=5500, start="2023-01-03", end="2023-07-31", seed=1)
    )
    assert panel.n_sec == 5500
    assert len(panel.bars) > 400_000
    assert panel.schema_problems() == []
