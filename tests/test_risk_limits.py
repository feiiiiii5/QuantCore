"""M3-009 risk limits: max positions, max weight and long-only target clamping."""

from __future__ import annotations

import numpy as np

from quantcore.backtest.config import BacktestConfig, RiskLimitsConfig
from quantcore.backtest.engine import _apply_risk_limits


def test_max_positions_and_weight_clamp() -> None:
    weights = np.full((2, 6), np.nan)
    weights[0] = [0.4, 0.3, 0.2, 0.1, 0.0, 0.0]
    weights[1] = [0.8, 0.1, 0.05, 0.03, 0.01, 0.01]
    config = BacktestConfig(risk=RiskLimitsConfig(max_positions=2, max_weight=0.25))
    limited = _apply_risk_limits(weights, config)
    assert limited.shape == weights.shape
    assert np.isnan(limited[0]).sum() == 0
    assert np.count_nonzero(limited[0] > 0) == 2
    assert limited[0].max() <= 0.25 + 1e-12
    assert limited[1, 0] <= 0.25 + 1e-12
    assert np.count_nonzero(limited[1] > 0) == 2
    assert np.allclose(weights[1], [0.8, 0.1, 0.05, 0.03, 0.01, 0.01])


def test_long_only_clamps_negative_targets() -> None:
    weights = np.full((1, 3), np.nan)
    weights[0] = [-0.2, 0.5, float("inf")]
    limited = _apply_risk_limits(weights, BacktestConfig(risk=RiskLimitsConfig(long_only=True)))
    assert limited[0, 0] == 0.0
    assert limited[0, 1] == 0.5
    assert not np.isfinite(limited[0, 2])  # inf is not a finite target; engine handles/rejects


def test_default_config_is_noop() -> None:
    weights = np.full((2, 3), np.nan)
    weights[0] = [0.2, 0.3, 0.5]
    limited = _apply_risk_limits(weights, BacktestConfig())
    assert np.allclose(limited, weights, equal_nan=True)


def test_risk_limits_api_config_accepted(api_client) -> None:
    response = api_client.post(
        "/api/backtest",
        json={
            "template": "momentum",
            "params": {"top_n": 5, "lookback": 60},
            "config": {"risk": {"max_positions": 3, "max_weight": 0.5}},
        },
    )
    assert response.status_code == 202, response.text
