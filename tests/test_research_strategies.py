"""Research candidates keep causal signals, valid allocations and honest data gaps."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantcore.calendar import TradingCalendar
from quantcore.cli import _load_spec
from quantcore.data.panel import PanelData
from quantcore.errors import StrategyValidationError
from quantcore.strategy.base import PanelView, UniverseFilter
from quantcore.strategy.spec import StrategySpec, template_catalog
from quantcore.templates import create_template

IDS = ("trend_momentum", "liquid_reversal", "defensive_low_vol")


@pytest.fixture()
def prices() -> PanelData:
    calendar = TradingCalendar.weekdays("2023-01-03", "2024-06-28")
    t = np.arange(len(calendar), dtype=float)
    close = np.column_stack(
        [
            10 * np.exp(0.001 * t + 0.001 * np.sin(t * 0.7)),
            10 * np.exp(0.0015 * t + 0.01 * np.sin(t)),
            10 * np.exp(-0.001 * t + 0.001 * np.sin(t * 0.4)),
            np.full(len(t), 10.0),
        ]
    )
    ids = [f"S{i}" for i in range(4)]
    bars = pd.DataFrame(
        {
            "date": np.repeat(calendar.dates, 4),
            "sec_id": np.tile(ids, len(t)),
            "open": close.ravel(),
            "high": (close * 1.01).ravel(),
            "low": (close * 0.99).ravel(),
            "close": close.ravel(),
            "pre_close": np.vstack([close[0], close[:-1]]).ravel(),
            "volume": 1_000_000,
            "amount": np.tile([1e8, 2e8, 1.5e8, 1e3], len(t)),
            "adj_factor": 1.0,
            "source": "SYNTHETIC",
        }
    )
    securities = pd.DataFrame(
        {
            "sec_id": ids,
            "code": [f"60000{i}" for i in range(4)],
            "board": "MAIN",
            "list_date": 20000101,
        }
    )
    return PanelData(calendar, securities, bars, meta={"synthetic": True})


@pytest.mark.parametrize("template", IDS)
def test_candidate_dates_weights_and_future_truncation(prices: PanelData, template: str) -> None:
    strategy = create_template(template, {"top_n": 2})
    weights = strategy.generate_targets(prices)
    flags = PanelView(prices).rebalance_flags(strategy.params.rebalance)
    np.testing.assert_array_equal(~np.isnan(weights).all(axis=1), flags)
    assert np.all(np.count_nonzero(weights[flags] > 0, axis=1) <= 2)
    sums = weights[flags].sum(axis=1)
    assert np.all(np.isclose(sums, 0) | np.isclose(sums, 1))
    assert (sums > 0).any()
    assert not (weights[flags] < 0).any()
    warmup = {"trend_momentum": 252, "liquid_reversal": 60, "defensive_low_vol": 120}[template]
    assert not np.nan_to_num(weights[:warmup]).any()
    for cut in (200, 300):
        prefix = prices.truncate(int(prices.dates[cut]))
        np.testing.assert_array_equal(strategy.generate_targets(prefix), weights[: cut + 1])


@pytest.mark.parametrize("template", IDS)
def test_split_adjustment_does_not_create_a_signal(prices: PanelData, template: str) -> None:
    strategy = create_template(template, {"top_n": 2})
    expected = strategy.generate_targets(prices)
    split = prices.select()
    after = split.bars.date >= split.dates[220]
    split.bars.loc[after, ["open", "high", "low", "close", "pre_close"]] /= 2
    split.bars.loc[after, "adj_factor"] = 2.0
    np.testing.assert_array_equal(strategy.generate_targets(split), expected)


@pytest.mark.parametrize("template", IDS)
def test_invalid_adjustment_factors_target_cash(prices: PanelData, template: str) -> None:
    prices.bars["adj_factor"] = np.tile([0.0, -1.0, np.nan, np.inf], prices.n_time)
    weights = create_template(template).generate_targets(prices)
    assert np.all(weights[~np.isnan(weights).all(axis=1)] == 0)


@pytest.mark.parametrize("template", IDS)
def test_raw_price_universe_can_force_cash(prices: PanelData, template: str) -> None:
    prices.bars["adj_factor"] = 10.0  # adjusted signal levels exceed the raw price floor
    strategy = create_template(template, universe=UniverseFilter(min_price=20.0))
    weights = strategy.generate_targets(prices)
    assert np.all(weights[~np.isnan(weights).all(axis=1)] == 0)


def test_reversal_liquidity_parameters_change_the_eligible_set(prices: PanelData) -> None:
    common = {"top_n": 2, "rebalance": "daily"}
    broad = create_template(
        "liquid_reversal", {**common, "liquidity_quantile": 0.0}
    ).generate_targets(prices)
    liquid = create_template(
        "liquid_reversal", {**common, "liquidity_quantile": 1.0}
    ).generate_targets(prices)
    np.testing.assert_array_equal(broad[-1] > 0, [True, True, False, False])
    np.testing.assert_array_equal(liquid[-1] > 0, [False, True, False, False])
    cash = create_template(
        "liquid_reversal", {**common, "min_average_amount": 1e20}
    ).generate_targets(prices)
    assert not cash[-1].any()


def test_momentum_skip_excludes_the_recent_spike(prices: PanelData) -> None:
    t = np.arange(prices.n_time)
    for sec, drift in [("S0", 0.002), ("S1", 0.001)]:
        mask = prices.bars.sec_id == sec
        prices.bars.loc[mask, "close"] = 10 * np.exp(drift * t)
    recent = (prices.bars.sec_id == "S1") & (prices.bars.date >= prices.dates[-21])
    prices.bars.loc[recent, "close"] *= 3
    prices.bars["open"] = prices.bars["close"]
    prices.bars["high"] = prices.bars["close"] * 1.01
    prices.bars["low"] = prices.bars["close"] * 0.99
    common = {"top_n": 1, "rebalance": "daily"}
    skipped = create_template("trend_momentum", {**common, "skip": 21}).generate_targets(prices)
    current = create_template("trend_momentum", {**common, "skip": 0}).generate_targets(prices)
    assert skipped[-1, 0] == 1
    assert current[-1, 1] == 1


def test_defensive_weights_are_inverse_sample_volatility(prices: PanelData) -> None:
    strategy = create_template("defensive_low_vol", {"top_n": 2, "rebalance": "daily"})
    targets = strategy.generate_targets(prices)
    close = prices.matrix("close")[-61:, :2]
    vol = np.std(close[1:] / close[:-1] - 1, axis=0, ddof=1)
    expected = (1 / vol) / np.sum(1 / vol)
    np.testing.assert_allclose(targets[-1, :2], expected, rtol=1e-12)
    assert not targets[-1, 2:].any()  # falling trend and zero-volatility flat asset


def test_candidate_signal_executes_on_the_next_native_bar(prices: PanelData) -> None:
    from quantcore.backtest.config import BacktestConfig
    from quantcore.backtest.engine import run_backtest

    strategy = create_template(
        "trend_momentum",
        {
            "lookback": 3,
            "skip": 1,
            "trend_window": 3,
            "rebalance": "daily",
            "top_n": 1,
        },
    )
    targets = strategy.generate_targets(prices)
    first_signal = int(np.flatnonzero(np.nansum(targets, axis=1) > 0)[0])
    result = run_backtest(prices, targets, BacktestConfig())
    assert result.engine_backend == "cpp"
    assert not result.trades.empty
    assert result.trades.iloc[0]["date"] == prices.dates[first_signal + 1]


@pytest.mark.parametrize(
    ("template", "params"),
    [
        ("trend_momentum", {"lookback": 20, "skip": 20}),
        ("liquid_reversal", {"liquidity_quantile": 1.1}),
        ("defensive_low_vol", {"lookback": 1}),
    ],
)
def test_candidate_parameter_counterexamples(template: str, params: dict) -> None:
    with pytest.raises(StrategyValidationError):
        create_template(template, params)


def test_catalog_and_specs_include_research_code(prices: PanelData) -> None:
    assert set(IDS) <= {entry["id"] for entry in template_catalog()}
    source = Path(__file__).resolve().parents[1] / "python/quantcore/templates/research.py"
    for template in IDS:
        spec = StrategySpec(name=template, template=template, params={"top_n": 2})
        assert source.read_bytes() in spec.code_bytes()
        restored = StrategySpec.from_yaml(spec.to_yaml())
        np.testing.assert_array_equal(
            spec.load().generate_targets(prices), restored.load().generate_targets(prices)
        )
        cli_spec = _load_spec(None, template, json.dumps({"top_n": 2}))
        np.testing.assert_array_equal(
            cli_spec.load().generate_targets(prices), spec.load().generate_targets(prices)
        )


def test_candidates_load_through_existing_api(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from quantcore.server import create_app

    application = create_app(
        token="research-test",
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path,
        snapshots_root=tmp_path / "snapshots",
        experiments_root=tmp_path / "experiments",
        start_worker=False,
    )
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        client.headers.update({"Authorization": "Bearer research-test"})
        response = client.get("/api/strategies/templates")
        assert response.status_code == 200
        assert set(IDS) <= {row["id"] for row in response.json()}
        for template in IDS:
            response = client.post(
                "/api/strategies/validate", json={"template": template, "params": {}}
            )
            assert response.status_code == 200
            assert response.json()["valid"] is True
