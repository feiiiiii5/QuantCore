"""M2-005 Tushare live path: optional token + fake Pro API (no network).

The real Tushare service cannot be exercised without a token; these tests verify the
request/endpoint/normalisation path with an in-process fake ``tushare`` module.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pandas as pd

from quantcore.providers.tushare import TushareProvider


class _FakePro:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    def trade_cal(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("trade_cal", kwargs))
        return pd.DataFrame({"cal_date": [20230103, 20230104, 20230105]})

    def stock_basic(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("stock_basic", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["600000.SH", "000001.SZ"],
                "symbol": ["600000", "000001"],
                "name": ["A", "B"],
                "market": ["主板", "主板"],
                "industry": ["银行", "银行"],
                "list_date": [19991110, 19910403],
            }
        )

    def daily(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("daily", kwargs))
        return pd.DataFrame(
            {
                "ts_code": [kwargs["ts_code"]],
                "trade_date": [20230103],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "vol": [1000.0],
                "amount": [1020.0],
            }
        )

    def adj_factor(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("adj_factor", kwargs))
        return pd.DataFrame({"trade_date": [20230103], "adj_factor": [1.0]})

    def stk_limit(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("stk_limit", kwargs))
        return pd.DataFrame({"trade_date": [20230103], "up_limit": [11.0], "down_limit": [9.0]})

    def fina_indicator(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("fina_indicator", kwargs))
        return pd.DataFrame(
            {
                "ts_code": [kwargs["ts_code"]],
                "end_date": [20221231],
                "ann_date": [20230120],
                "revenue": [100.0],
                "n_income": [10.0],
                "roe": [0.1],
            }
        )

    def dividend(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(("dividend", kwargs))
        return pd.DataFrame(
            {
                "ts_code": [kwargs["ts_code"]],
                "ann_date": [20230110],
                "ex_date": [20230120],
                "cash_div_tax": [0.2],
                "stk_div": [0.0],
            }
        )


def _install_fake(monkeypatch, calls: list[tuple[str, dict[str, Any]]]) -> None:
    module = types.ModuleType("tushare")
    module.pro_api = lambda token: _FakePro(calls)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tushare", module)


def test_live_daily_financials_actions(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    _install_fake(monkeypatch, calls)
    provider = TushareProvider(token="fake-token", allow_network=True)
    calendar = provider.fetch_calendar("2023-01-01", "2023-01-31")
    assert len(calendar.dates) == 3
    master = provider.fetch_security_master()
    assert len(master) == 2
    bars = provider.fetch_daily_bars(["600000.SH"], "2023-01-01", "2023-01-31")
    assert len(bars) == 1
    assert bars.iloc[0]["close"] == 10.2
    financials = provider.fetch_financials(["600000.SH"], "2023-01-01", "2023-01-31")
    assert len(financials) == 1
    assert financials.iloc[0]["ann_date"] == 20230120
    actions = provider.fetch_corporate_actions(["600000.SH"], "2023-01-01", "2023-01-31")
    assert len(actions) == 1
    assert actions.iloc[0]["cash_per_share"] == 0.2
    assert (
        "fina_indicator",
        {"ts_code": "600000.SH", "start_date": "20230101", "end_date": "20230131"},
    ) in calls


def test_live_mode_requires_network_and_token() -> None:
    offline = TushareProvider(token="x", allow_network=False)
    try:
        offline.fetch_security_master()
    except Exception as exc:  # ProviderPermissionError
        assert "allow_network" in str(exc) or "network" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("offline live provider must be rejected")


def test_live_financials_requires_codes(monkeypatch) -> None:
    _install_fake(monkeypatch, [])
    provider = TushareProvider(token="fake-token", allow_network=True)
    try:
        provider.fetch_financials([], "2023-01-01", "2023-01-31")
    except Exception as exc:
        assert "code list" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("live financials without codes must be rejected")
