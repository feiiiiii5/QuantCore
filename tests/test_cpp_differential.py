"""Differential test: C++ engine vs the pure-Python reference engine (test-only).

This is the core ``make verify-cpp`` gate: equity/cash/market value must agree to the
fixed-point unit, trades and rejection reasons must line up for the buy-and-hold and
monthly-rebalance scenarios.
"""

from __future__ import annotations

import numpy as np
import pytest

import quantcore
from quantcore.backtest.config import BacktestConfig, TraceLevel
from quantcore.backtest.engine import run_backtest
from tests.reference.engine_ref import RefConfig, run_reference

pytestmark = pytest.mark.skipif(
    not (quantcore.engine_available() and quantcore.panel_available()),
    reason="C++ engine or .qpanel is unavailable",
)

MINUTES_EPS = 1.0  # 1e-4 CNY: one fixed-point unit


def _ref_config(config: BacktestConfig) -> RefConfig:
    return RefConfig(
        initial_cash=round(config.initial_cash * 10000),
        commission_rate=config.costs.commission_rate,
        min_commission=round(config.costs.min_commission * 10000),
        stamp_duty_rate=config.costs.stamp_duty_rate,
        transfer_fee_rate=config.costs.transfer_fee_rate,
        exchange_fee_rate=config.costs.exchange_fee_rate,
        reg_fee_rate=config.costs.reg_fee_rate,
        transfer_fee_shanghai_only=config.costs.transfer_fee_shanghai_only,
        slippage_bps=config.exec.slippage_bps,
        max_participation=config.exec.max_participation,
        min_rebalance_value=round(config.exec.min_rebalance_value * 10000),
        main_lot=config.rules.main_lot,
        t_plus_one=config.rules.t_plus_one,
        annual_days=config.annual_days,
        min_price_tick=round(config.rules.min_price_tick * 10000),
        use_panel_corporate_actions=config.use_panel_corporate_actions,
        corporate_actions=config.corporate_actions,
    )


def _buy_hold_weights(panel) -> np.ndarray:
    weights = np.full((panel.n_time, panel.n_sec), np.nan)
    weights[0] = 0.0
    count = min(10, panel.n_sec)
    weights[0, :count] = 1.0 / count
    return weights


def _monthly_weights(panel, count: int = 10) -> np.ndarray:
    weights = np.full((panel.n_time, panel.n_sec), np.nan)
    count = min(count, panel.n_sec)
    for day, flag in enumerate(panel.calendar.month_start_flags()):
        if flag:
            weights[day] = 0.0
            weights[day, :count] = 1.0 / count
    return weights


def _compare_arrays(cpp_values: np.ndarray, ref_values: np.ndarray, label: str) -> None:
    cpp = np.asarray(cpp_values, dtype=np.int64)
    ref = np.asarray(ref_values, dtype=np.int64)
    assert cpp.shape == ref.shape, f"{label}: shape {cpp.shape} != {ref.shape}"
    difference = np.abs(cpp - ref)
    worst = int(difference.max()) if difference.size else 0
    assert worst <= MINUTES_EPS, (
        f"{label}: {int((difference > MINUTES_EPS).sum())} days differ, worst {worst} "
        "(1e-4 CNY units)"
    )


def _cpp_result(panel, weights, config):
    backtest = run_backtest(
        panel,
        weights,
        config,
        strategy_metadata={"name": "differential"},
        snapshot_metadata={"synthetic": True},
    )
    return backtest


def test_metrics_agree(small_panel, monthly_weights) -> None:
    config = BacktestConfig(initial_cash=1_000_000.0)
    cpp = _cpp_result(small_panel, monthly_weights, config)
    ref = run_reference(small_panel, monthly_weights, _ref_config(config))
    assert cpp.metrics["trade_count"] == ref.metrics["trade_count"]
    assert cpp.metrics["trading_days"] == ref.metrics["trading_days"]
    assert abs(cpp.metrics["total_return"] - ref.metrics["total_return"]) < 1e-9
    assert abs(cpp.metrics["max_drawdown"] - ref.metrics["max_drawdown"]) < 1e-9
    assert abs(cpp.metrics["sharpe"] - ref.metrics["sharpe"]) < 1e-9


def test_engine_backend_is_cpp() -> None:
    assert quantcore.engine_backend() == "cpp"
    assert quantcore.engine_available()
    assert quantcore.panel_available()


def test_buy_and_hold_differential(small_panel) -> None:
    weights = _buy_hold_weights(small_panel)
    config = BacktestConfig(initial_cash=1_000_000.0)
    cpp = _cpp_result(small_panel, weights, config)
    ref = run_reference(small_panel, weights, _ref_config(config))
    _compare_arrays(cpp.equity, ref.equity, "equity")
    _compare_arrays(cpp.cash, ref.cash, "cash")
    _compare_arrays(cpp.market_value, ref.market_value, "market_value")
    assert len(cpp.trades) == len(ref.trades)
    for cpp_trade, ref_trade in zip(cpp.trades.to_dict(orient="records"), ref.trades, strict=False):
        assert int(cpp_trade["date"]) == int(ref_trade["date"])
        assert int(cpp_trade["sec_index"]) == int(ref_trade["sec"])
        assert int(cpp_trade["side"]) == int(ref_trade["side"])
        assert int(cpp_trade["qty"]) == int(ref_trade["qty"])
        assert abs(int(cpp_trade["px"]) - int(ref_trade["px"])) <= MINUTES_EPS
        assert abs(int(cpp_trade["amount"]) - int(ref_trade["amount"])) <= MINUTES_EPS
        assert abs(int(cpp_trade["fee_total"]) - int(ref_trade["fee_total"])) <= MINUTES_EPS


def test_monthly_rebalance_differential(small_panel, monthly_weights) -> None:
    config = BacktestConfig(initial_cash=1_000_000.0, trace=TraceLevel.summary)
    cpp = _cpp_result(small_panel, monthly_weights, config)
    ref = run_reference(small_panel, monthly_weights, _ref_config(config))
    _compare_arrays(cpp.equity, ref.equity, "equity")
    _compare_arrays(cpp.cash, ref.cash, "cash")
    _compare_arrays(cpp.market_value, ref.market_value, "market_value")
    assert len(cpp.trades) == len(ref.trades)
    cpp_sides = cpp.trades["side"].value_counts().to_dict()
    ref_sides = {}
    for trade in ref.trades:
        ref_sides[trade["side"]] = ref_sides.get(trade["side"], 0) + 1
    assert cpp_sides == ref_sides
    # Rejection reasons should agree exactly (every code, not only the significant ones).
    cpp_reasons = {int(key): int(value) for key, value in cpp.reasons.items()}
    assert cpp_reasons == ref.reasons


def test_cpp_engine_deterministic(small_panel, monthly_weights) -> None:
    config = BacktestConfig(initial_cash=1_000_000.0)
    first = _cpp_result(small_panel, monthly_weights, config)
    second = _cpp_result(small_panel, monthly_weights, config)
    assert np.array_equal(first.equity, second.equity)
    assert np.array_equal(first.cash, second.cash)
    assert first.trades.equals(second.trades)
    assert first.metrics == second.metrics


def test_no_lookahead_execution_semantics(small_panel) -> None:
    """A target decided on the last day must not be executed inside the sample."""
    weights = np.full((small_panel.n_time, small_panel.n_sec), np.nan)
    weights[small_panel.n_time - 1] = 0.0
    weights[small_panel.n_time - 1, :3] = 1.0 / 3.0
    result = _cpp_result(small_panel, weights, BacktestConfig())
    assert len(result.trades) == 0
    assert result.equity[-1] == result.equity[0]
