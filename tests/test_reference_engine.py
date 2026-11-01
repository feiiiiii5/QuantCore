"""Reference-engine invariants (pure Python, test-only)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from tests.reference.engine_ref import REASONS, RefConfig, compute_costs, llround, run_reference

DATES = TradingCalendar.weekdays("2023-01-03", "2023-01-10").dates
DATES = list(DATES)[:6]
SEC_IDS = ["S0", "S1"]


def _custom_panel(
    prices: dict[str, list[float]],
    *,
    suspended: dict[str, set[int]] | None = None,
    force_limit_up: dict[str, set[int]] | None = None,
) -> PanelData:
    """Build a tiny canonical panel with chosen closes and optional limit-up days."""
    suspended = suspended or {}
    force_limit_up = force_limit_up or {}
    rows = []
    for sec, close_values in prices.items():
        previous = close_values[0]
        for index, close in enumerate(close_values):
            limit_up = round(previous * 1.1, 2)
            if index in force_limit_up.get(sec, set()):
                open_px = high = low = close = limit_up
            else:
                open_px = close
                high = round(close * 1.01, 2)
                low = round(close * 0.99, 2)
            rows.append(
                {
                    "date": DATES[index],
                    "sec_id": sec,
                    "code": sec,
                    "open": open_px,
                    "high": high,
                    "low": low,
                    "close": close,
                    "pre_close": previous,
                    "volume": 1_000_000,
                    "amount": close * 1_000_000,
                    "adj_factor": 1.0,
                    "limit_up": limit_up,
                    "limit_down": round(previous * 0.9, 2),
                    "suspended": index in suspended.get(sec, set()),
                    "st": False,
                    "turnover": 0.01,
                    "total_shares": 1_000_000_000,
                    "float_shares": 1_000_000_000,
                    "mktcap": close * 1_000_000_000,
                    "float_mktcap": close * 1_000_000_000,
                    "source": "SYNTHETIC",
                }
            )
    securities = pd.DataFrame(
        {
            "sec_id": SEC_IDS,
            "code": SEC_IDS,
            "exchange": ["SH", "SZ"],
            "name": ["A", "B"],
            "board": ["MAIN", "MAIN"],
            "list_date": DATES[0],
            "delist_date": 0,
            "sec_type": "STOCK",
            "industry": "test",
            "source": "SYNTHETIC",
        }
    )
    return PanelData(
        calendar=TradingCalendar(tuple(DATES)),
        securities=securities,
        bars=pd.DataFrame.from_records(rows),
        meta={"synthetic": True, "source": "SYNTHETIC", "disclaimer": "SYNTHETIC"},
    )


def _targets(*rows: dict[str, float]) -> np.ndarray:
    matrix = np.full((len(DATES), 2), np.nan)
    for index, row in enumerate(rows):
        values = np.zeros(2)
        for sec, weight in row.items():
            values[SEC_IDS.index(sec)] = weight
        matrix[index] = values
    return matrix


def test_buy_and_hold_flow() -> None:
    panel = _custom_panel({sec: [10.0] * len(DATES) for sec in SEC_IDS})
    weights = _targets({"S0": 0.5, "S1": 0.5})
    result = run_reference(panel, weights, RefConfig(initial_cash=10_000_000_000))
    assert result.equity[0] == 10_000_000_000
    assert result.trades, "expected fills on the next open"
    for trade in result.trades:
        assert trade["qty"] % 100 == 0
        assert trade["side"] == 0  # only buys
        expected_fees = compute_costs(RefConfig(), 0, trade["amount"], trade["sec"] == 0)
        assert trade["fee_total"] == expected_fees["fee_total"]
        assert trade["fee_total"] == (
            trade["commission"] + trade["stamp_duty"] + trade["transfer_fee"] + trade["other_fee"]
        )
    assert all(value >= 0 for value in result.cash)
    assert result.cash[-1] + result.market_value[-1] == result.equity[-1]


def test_limit_up_buy_is_rejected() -> None:
    panel = _custom_panel(
        {sec: [10.0] * len(DATES) for sec in SEC_IDS},
        force_limit_up={"S0": {1}},
    )
    weights = _targets({"S0": 1.0})
    result = run_reference(panel, weights)
    assert not result.trades
    assert result.reasons.get(REASONS["limit_up"], 0) >= 1
    assert result.equity[-1] == result.equity[0]


def test_suspended_buy_is_rejected() -> None:
    panel = _custom_panel(
        {sec: [10.0] * len(DATES) for sec in SEC_IDS},
        suspended={"S0": {1}},
    )
    weights = _targets({"S0": 1.0})
    result = run_reference(panel, weights)
    assert not result.trades
    assert result.reasons.get(REASONS["suspended"], 0) >= 1


def test_next_day_sell_after_buy() -> None:
    panel = _custom_panel({sec: [10.0] * len(DATES) for sec in SEC_IDS})
    weights = _targets({"S0": 1.0}, {}, {"S0": 1.0})
    result = run_reference(panel, weights)
    sides = [trade["side"] for trade in result.trades]
    assert sides.count(0) == 2, "buy, liquidate, re-buy"
    assert sides.count(1) == 1
    first_buy = next(trade for trade in result.trades if trade["side"] == 0)
    sell = next(trade for trade in result.trades if trade["side"] == 1)
    assert sell["date"] > first_buy["date"]


def test_min_commission_floor() -> None:
    panel = _custom_panel({sec: [10.0] * len(DATES) for sec in SEC_IDS})
    weights = _targets({"S0": 0.01})
    result = run_reference(panel, weights)
    buy = next(trade for trade in result.trades if trade["side"] == 0)
    assert buy["commission"] == 50_000  # 5 CNY floor in 1e-4 units
    assert buy["amount"] > 0


def test_deterministic() -> None:
    panel = _custom_panel(
        {sec: [10.0 + index * 0.1 for index in range(len(DATES))] for sec in SEC_IDS}
    )
    weights = _targets({"S0": 0.5, "S1": 0.5})
    first = run_reference(panel, weights)
    second = run_reference(panel, weights)
    assert first.equity == second.equity
    assert first.trades == second.trades


def test_synthetic_panel_invariants(small_panel, monthly_weights) -> None:
    result = run_reference(small_panel, monthly_weights)
    assert len(result.equity) == small_panel.n_time
    assert result.cash[0] == RefConfig().initial_cash
    assert all(value >= 0 for value in result.cash)
    board_codes = {"MAIN": 0, "GEM": 1, "STAR": 2, "BSE": 3}
    lot_by_sec = [
        board_codes.get(str(record["board"]), 0)
        for record in small_panel.securities.to_dict(orient="records")
    ]
    for trade in result.trades:
        assert trade["qty"] > 0
        board = lot_by_sec[trade["sec"]]
        if trade["side"] == 0:  # buy orders follow board lot rules; sells may be remainders
            if board in (0, 1):
                assert trade["qty"] % 100 == 0
            else:
                assert trade["qty"] >= (200 if board == 2 else 100)
        assert trade["fee_total"] >= 0
    assert result.equity[-1] == result.cash[-1] + result.market_value[-1]
    # Book invariant: final equity must be positive and finite.
    assert np.isfinite(result.equity).all() and result.equity[-1] > 0
    assert set(result.metrics) >= {"total_return", "max_drawdown", "trade_count"}


def test_llround_rounds_half_away_from_zero() -> None:
    assert llround(2.5) == 3
    assert llround(-2.5) == -3
    assert llround(0.4) == 0
