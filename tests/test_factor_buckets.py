"""Factor groups cover finite observations without shifting the bottom bucket."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from quantcore.research.factors import _bucket_indices, analyze_factor


def test_five_names_fill_five_groups_once() -> None:
    np.testing.assert_array_equal(_bucket_indices(np.arange(5.0), 5), [0, 1, 2, 3, 4])


@pytest.mark.parametrize(("count", "quantiles"), [(7, 5), (11, 3), (4, 7)])
def test_uneven_groups_differ_by_at_most_one(count: int, quantiles: int) -> None:
    buckets = _bucket_indices(np.arange(float(count)), quantiles)
    sizes = np.bincount(buckets, minlength=quantiles)
    assert sizes.sum() == count
    assert sizes.max() - sizes.min() <= 1


def test_ties_keep_security_order_and_nonfinite_values_stay_unassigned() -> None:
    values = np.array([3.0, np.nan, 1.0, 1.0, np.inf, -np.inf, 2.0])
    np.testing.assert_array_equal(_bucket_indices(values, 4), [3, -1, 0, 1, -1, -1, 2])


def test_factor_report_contains_each_groups_actual_forward_return() -> None:
    dates = [20240102, 20240103]
    returns = [-0.10, -0.05, 0.0, 0.05, 0.10]
    securities = pd.DataFrame(
        [{"sec_id": f"S{index}", "code": f"{index:06d}", "board": "MAIN"} for index in range(5)]
    )
    bars = []
    for index, forward_return in enumerate(returns):
        original = float((index + 1) * 10)
        for day, date in enumerate(dates):
            close = original if day == 0 else original * (1 + forward_return)
            bars.append(
                {
                    "date": date,
                    "sec_id": f"S{index}",
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "pre_close": original,
                    "volume": 1_000_000,
                    "suspended": False,
                    "st": False,
                    "source": "SYNTHETIC",
                }
            )
    panel = PanelData(
        calendar=TradingCalendar.from_dates(dates),
        securities=securities,
        bars=pd.DataFrame(bars),
        meta={"synthetic": True, "source": "SYNTHETIC"},
    )

    report = analyze_factor(panel, "close", forward_days=1, quantiles=5)

    assert [row["bucket"] for row in report["quantile_returns"]] == [1, 2, 3, 4, 5]
    assert [row["observations"] for row in report["quantile_returns"]] == [1] * 5
    assert [row["mean_return"] for row in report["quantile_returns"]] == pytest.approx(returns)
    assert report["observations"] == 5
