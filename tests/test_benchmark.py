"""M3-014 benchmark comparison: buy-and-hold benchmark curve and excess metrics."""

from __future__ import annotations

import numpy as np
import pytest

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.engine import run_backtest
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
