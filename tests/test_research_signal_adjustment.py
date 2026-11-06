"""The research signal factor responds to an ex-date, never to future events."""

import pandas as pd
import pytest
from scripts.research_signal_adjustment import causal_factors


def event(day: int, cash: float) -> dict:
    return {"ex_date": day, "cash_per_share": cash, "split_ratio": 1.0}


def test_cash_ex_date_keeps_adjusted_price_continuous():
    raw = pd.DataFrame({"date": [20240102, 20240103], "close": [10.0, 9.5]})
    factor = causal_factors(raw, pd.DataFrame([event(20240103, 0.5)]))
    assert factor.iloc[0] == 1.0
    assert (raw.close * factor).tolist() == pytest.approx([10.0, 10.0])


def test_ordinary_price_rise_does_not_change_the_factor():
    raw = pd.DataFrame({"date": [20240102, 20240103], "close": [10.0, 11.0]})
    assert causal_factors(raw, pd.DataFrame()).tolist() == [1.0, 1.0]


def test_appending_a_future_event_does_not_change_the_prefix():
    raw = pd.DataFrame({"date": [20240102, 20240103, 20240104], "close": [10.0, 9.5, 9.0]})
    past = pd.DataFrame([event(20240103, 0.5)])
    future = pd.DataFrame([event(20240103, 0.5), event(20240104, 0.5)])
    prefix = causal_factors(raw.iloc[:2], past)
    extended = causal_factors(raw, future)
    assert extended.iloc[:2].tolist() == prefix.tolist()
    assert raw.close.iloc[-1] * extended.iloc[-1] == pytest.approx(10.0)
