"""Property/fuzz tests for reference-engine invariants, rules and the strategy DSL.

These do not replace the deterministic differential tests; they search for edge cases in
random target weights (ledger/rules), random DSL strings (parser) and random fee/limit
inputs (execution rules).  All are pure test code and use the Python reference engine.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quantcore.backtest.config import CostModelConfig, RuleSetConfig
from quantcore.errors import StrategyValidationError
from quantcore.paper.errors import PaperValidationError
from quantcore.paper.rules import canonical_buy_qty, fee_breakdown, price_limit_pct
from quantcore.strategy.expr import compile_expression
from tests.reference.engine_ref import RefConfig, run_reference
from tests.test_reference_engine import DATES, SEC_IDS, _custom_panel

FAST = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _panel():
    return _custom_panel({sec: [10.0, 10.2, 9.9, 10.4, 10.1, 10.3] for sec in SEC_IDS})


@FAST
@given(
    st.lists(
        st.tuples(
            st.floats(-3.0, 3.0, allow_nan=False, allow_infinity=False),
            st.floats(-3.0, 3.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=len(DATES),
        max_size=len(DATES),
    )
)
def test_random_targets_preserve_reference_ledger_invariants(rows):
    weights = np.asarray(rows, dtype=np.float64)
    result = run_reference(_panel(), weights, RefConfig(initial_cash=10_000_000_000))
    assert len(result.equity) == len(DATES)
    assert np.isfinite(np.asarray(result.equity, dtype=np.float64)).all()
    assert np.asarray(result.cash, dtype=np.float64).min() >= -1e-6
    for index in range(len(DATES)):
        assert result.equity[index] == pytest.approx(
            result.cash[index] + result.market_value[index], abs=1e-4
        )
    for trade in result.trades:
        assert trade["qty"] >= 0
        assert trade["fee_total"] >= 0
        assert trade["fee_total"] == pytest.approx(
            trade["commission"] + trade["stamp_duty"] + trade["transfer_fee"] + trade["other_fee"],
            abs=1e-6,
        )
        if trade["side"] == 0 and trade["qty"] > 0:
            assert trade["qty"] % 100 == 0


@FAST
@given(st.text(alphabet="abc0123()+-*/,_ .'\"[]=", min_size=0, max_size=60))
def test_expression_parser_fuzz_only_raises_validation_error(source):
    try:
        compiled = compile_expression(source)
    except StrategyValidationError:
        return
    assert compiled.source == source.strip()
    # Compiling valid-looking random text must not execute arbitrary code or crash later.
    assert compiled.referenced_fields is not None


@FAST
@given(
    st.sampled_from(["MAIN", "GEM", "STAR", "BSE", "UNKNOWN"]),
    st.booleans(),
    st.integers(20000101, 20301231),
    st.floats(0.0, 1000.0, allow_nan=False, allow_infinity=False),
    st.floats(0.0, 4.0, allow_nan=False, allow_infinity=False),
)
def test_rules_fuzz_price_limits_and_fees(board, is_st, date, amount, rate):
    rules = RuleSetConfig()
    pct = price_limit_pct(board, is_st, date, rules)
    assert 0.0 < pct <= 0.5
    costs = CostModelConfig(commission_rate=rate / 1000.0, stamp_duty_rate=rate / 5000.0)
    fees = fee_breakdown(costs, 1, amount, is_shanghai_stock=True)
    assert all(value >= 0 for value in fees.values())
    assert fees["fee_total"] == pytest.approx(
        sum(v for k, v in fees.items() if k != "fee_total"), abs=1e-6
    )


@FAST
@given(st.sampled_from(["MAIN", "GEM", "STAR", "BSE"]), st.integers(0, 5000))
def test_rules_fuzz_lot_validation(board, qty):
    rules = RuleSetConfig()
    if qty <= 0:
        with pytest.raises(PaperValidationError):
            canonical_buy_qty(board, qty, rules)
        return
    try:
        accepted = canonical_buy_qty(board, qty, rules)
    except PaperValidationError:
        return
    assert accepted == qty
    if board in ("MAIN", "GEM"):
        assert accepted % rules.main_lot == 0
    else:
        assert accepted >= (rules.star_lot if board == "STAR" else rules.bse_lot)
