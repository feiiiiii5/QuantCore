"""M3-014 benchmark comparison: buy-and-hold benchmark curve and excess metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.engine import _attach_benchmark, run_backtest
from quantcore.backtest.result import BacktestResult
from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from quantcore.errors import BacktestError


def test_benchmark_curve_and_metrics(small_panel) -> None:
    code = str(small_panel.securities.iloc[0]["code"])
    weights = np.full((small_panel.n_time, small_panel.n_sec), np.nan)
    weights[::20] = 1.0 / min(10, small_panel.n_sec)
    result = run_backtest(small_panel, weights, BacktestConfig(benchmark_code=code))
    assert result.benchmark["code"] == code
    assert len(result.benchmark["equity"]) == len(result.dates)
    assert result.benchmark["total_return"] == pytest.approx(
        result.benchmark["equity"][-1] / result.benchmark["equity"][0] - 1, abs=1e-8
    )
    for key in ("benchmark_return", "excess_return", "tracking_error", "information_ratio"):
        assert key in result.metrics
    assert result.metrics["excess_return"] == pytest.approx(
        result.metrics["total_return"] - result.metrics["benchmark_return"], abs=1e-8
    )
    persisted = result.summary()
    assert persisted["benchmark"]["code"] == code


def test_benchmark_unknown_code_raises(small_panel) -> None:
    weights = np.full((small_panel.n_time, small_panel.n_sec), np.nan)
    weights[0] = 0.0
    with pytest.raises(BacktestError, match="benchmark security not found"):
        run_backtest(small_panel, weights, BacktestConfig(benchmark_code="999999"))


def test_benchmark_api_config_is_accepted(api_client) -> None:
    securities = api_client.get("/api/market/securities?limit=1").json()
    code = securities[0]["code"]
    response = api_client.post(
        "/api/backtest",
        json={
            "template": "buy_and_hold",
            "params": {},
            "config": {"benchmark_code": code, "initial_cash": 1_000_000},
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    import time

    deadline = time.time() + 60
    job = None
    while time.time() < deadline:
        job = api_client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.05)
    assert job and job["status"] == "done", job
    payload = api_client.get(f"/api/jobs/{job_id}/result").json()["result"]
    assert payload["metrics"]["benchmark_return"] is not None
    assert payload["benchmark"]["code"] == code


@pytest.mark.parametrize("missing", [(2,), (1, 2, 3)])
def test_benchmark_tracking_uses_only_paired_daily_observations(missing: tuple[int, ...]) -> None:
    dates = np.array([20260105, 20260106, 20260107, 20260108, 20260109])
    prices = np.array([10.0, 11.0, 12.1, 13.31, 14.641])
    prices[list(missing)] = np.nan
    panel = PanelData(
        TradingCalendar(tuple(dates.tolist())),
        pd.DataFrame([{"sec_id": "600000.SH", "code": "600000"}]),
        pd.DataFrame(
            {
                "date": dates,
                "sec_id": "600000.SH",
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
                "volume": 100,
            }
        ),
    )
    equity = np.array([100, 110, 121, 133.1, 146.41]) * 10_000
    result = BacktestResult(
        dates=dates,
        equity=np.rint(equity).astype(np.int64),
        cash=np.rint(equity).astype(np.int64),
        market_value=np.zeros(5, dtype=np.int64),
        trades=pd.DataFrame(),
        metrics={"total_return": 0.4641},
        reasons={},
        engine_version="fixture",
        seed=42,
    )
    _attach_benchmark(result, panel, BacktestConfig(initial_cash=100, benchmark_code="600000"))
    assert result.benchmark["equity"][2] is None
    assert result.metrics["benchmark_return"] == pytest.approx(0.4641)
    if len(missing) == 1:
        assert result.metrics["tracking_error"] == pytest.approx(0.0, abs=1e-8)
        assert result.benchmark["daily_observations"] == 2
    else:
        assert result.metrics["tracking_error"] is None
        assert result.metrics["information_ratio"] is None
        assert result.benchmark["daily_observations"] == 0


@pytest.mark.parametrize(("cash", "split"), [(0.0, 2.0), (0.5, 1.0), (0.5, 2.0)])
def test_benchmark_holds_split_shares_and_dividend_cash(cash: float, split: float) -> None:
    from tests.test_corporate_backtest import action_panel, config, weights

    panel = action_panel(cash=cash, split=split)
    result = run_backtest(panel, weights(panel), config(benchmark_code="600000"))
    assert result.benchmark["equity"] == pytest.approx([10000] * 4)
    assert result.metrics["benchmark_return"] == 0
    assert result.metrics["excess_return"] == 0
    assert result.metrics["tracking_error"] == 0


def test_benchmark_uses_explicit_events_and_respects_disabled_panel_events() -> None:
    from tests.test_corporate_backtest import action_panel, config, weights

    panel = action_panel(split=2.0)
    disabled = run_backtest(
        panel,
        weights(panel),
        config(
            benchmark_code="600000",
            use_panel_corporate_actions=False,
        ),
    )
    assert disabled.metrics["benchmark_return"] == -0.5
    explicit = run_backtest(
        panel,
        weights(panel),
        config(
            benchmark_code="600000",
            use_panel_corporate_actions=False,
            corporate_actions=[{"sec_id": "600000.SH", "ex_date": 20260107, "split_ratio": 2.0}],
        ),
    )
    assert explicit.metrics["benchmark_return"] == 0


@pytest.mark.parametrize("missing", [0, 3])
def test_benchmark_missing_window_boundary_does_not_claim_excess_return(missing: int) -> None:
    from tests.test_corporate_backtest import action_panel, config, weights

    panel = action_panel()
    panel.bars.loc[missing, ["open", "high", "low", "close"]] = np.nan
    result = run_backtest(panel, weights(panel), config(benchmark_code="600000"))
    assert result.benchmark["complete_window"] is False
    assert result.metrics["excess_return"] is None
