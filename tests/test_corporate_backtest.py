"""Corporate actions reach the native production engine and remain replayable."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantcore.backtest.config import BacktestConfig, CostModelConfig
from quantcore.backtest.engine import run_backtest, run_backtest_batch
from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from quantcore.errors import BacktestError
from quantcore.experiments import ExperimentStore, replay_experiment, run_experiment
from quantcore.research.experiment_data import load_bundle
from quantcore.snapshot import build_snapshot, load_snapshot
from quantcore.strategy.spec import StrategySpec


def action_panel(*, cash: float = 0.0, split: float = 1.0) -> PanelData:
    dates = (20260105, 20260106, 20260107, 20260108)
    securities = pd.DataFrame(
        [
            {
                "sec_id": "600000.SH",
                "code": "600000",
                "exchange": "SH",
                "board": "MAIN",
                "list_date": 20000101,
                "name": "fixture",
            }
        ]
    )
    bars = []
    ex_price = (10.0 - cash) / split
    for i, date in enumerate(dates):
        price = 10.0 if i < 2 else ex_price
        bars.append(
            {
                "date": date,
                "sec_id": "600000.SH",
                "open": price,
                "close": price,
                "pre_close": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "volume": 1_000_000,
                "amount": price * 1_000_000,
                "limit_up": price * 1.1,
                "limit_down": price * 0.9,
                "adj_factor": 1.0 if i < 2 else 10.0 / price,
            }
        )
    actions = pd.DataFrame(
        [
            {
                "sec_id": "600000.SH",
                "ann_date": 20251201,
                "record_date": 20260106,
                "ex_date": 20260107,
                "pay_date": 20260108,
                "cash_per_share": cash,
                "split_ratio": split,
                "rights_ratio": 0.0,
                "rights_price": 0.0,
            }
        ]
    )
    return PanelData(
        TradingCalendar(dates), securities, pd.DataFrame(bars), corporate_actions=actions
    )


def config(**kwargs: object) -> BacktestConfig:
    costs = CostModelConfig(
        commission_rate=0,
        min_commission=0,
        stamp_duty_rate=0,
        transfer_fee_rate=0,
        exchange_fee_rate=0,
        reg_fee_rate=0,
    )
    return BacktestConfig(initial_cash=10_000, costs=costs, **kwargs)


def weights(panel: PanelData) -> np.ndarray:
    output = np.full((panel.n_time, panel.n_sec), np.nan)
    output[0, 0] = 0.5
    return output


@pytest.mark.parametrize(("cash", "split"), [(0.0, 2.0), (0.5, 1.0), (0.5, 2.0)])
def test_panel_actions_preserve_value_and_credit_cash(cash: float, split: float) -> None:
    panel = action_panel(cash=cash, split=split)
    result = run_backtest(panel, weights(panel), config())
    assert result.engine_backend == "cpp"
    assert result.equity_yuan.tolist() == pytest.approx([10_000] * 4)
    assert result.cash[-1] / 10_000 == pytest.approx(5_000 + 500 * cash)
    assert result.final_positions.iloc[0]["qty"] == 500 * split


def test_explicit_actions_override_panel_and_can_be_used_without_it() -> None:
    panel = action_panel(split=2.0)
    explicit = [{"sec_id": "600000.SH", "ex_date": "2026-01-07", "split_ratio": 3.0}]
    result = run_backtest(panel, weights(panel), config(corporate_actions=explicit))
    assert result.final_positions.iloc[0]["qty"] == 1_500
    panel.corporate_actions = panel.corporate_actions.iloc[:0]
    result = run_backtest(panel, weights(panel), config(corporate_actions=explicit))
    assert result.final_positions.iloc[0]["qty"] == 1_500


def test_panel_actions_can_be_disabled_without_disabling_explicit_events() -> None:
    panel = action_panel(split=2.0)
    result = run_backtest(panel, weights(panel), config(use_panel_corporate_actions=False))
    assert result.equity_yuan[-1] == 7_500
    result = run_backtest(
        panel,
        weights(panel),
        config(
            use_panel_corporate_actions=False,
            corporate_actions=[{"sec": 0, "ex_date": 20260107, "split_ratio": 2.0}],
        ),
    )
    assert result.equity_yuan[-1] == 10_000


def test_snapshot_batch_and_date_slice_use_the_same_events(tmp_path: Path) -> None:
    panel = action_panel(cash=0.5, split=2.0)
    manifest = build_snapshot(panel, tmp_path)
    snapshot = load_snapshot(tmp_path, manifest.snapshot_id)
    direct = run_backtest(panel, weights(panel), config())
    restored = run_backtest(snapshot, weights(panel), config())
    batch = run_backtest_batch(snapshot, [weights(panel), weights(panel)], config(), threads=2)
    for result in [restored, *batch]:
        np.testing.assert_array_equal(result.equity, direct.equity)
        np.testing.assert_array_equal(result.cash, direct.cash)
    cut = panel.truncate(20260106)
    assert run_backtest(cut, weights(cut), config()).final_positions.iloc[0]["qty"] == 500


def test_event_security_is_mapped_to_the_panel_order() -> None:
    original = action_panel(split=2.0)
    securities = pd.concat(
        [
            original.securities.assign(sec_id="000001.SZ", code="000001", exchange="SZ"),
            original.securities,
        ],
        ignore_index=True,
    )
    bars = pd.concat(
        [
            original.bars.assign(sec_id="000001.SZ", code="000001"),
            original.bars,
        ],
        ignore_index=True,
    )
    panel = PanelData(
        original.calendar, securities, bars, corporate_actions=original.corporate_actions
    )
    target = np.full((4, 2), np.nan)
    target[0] = [0.5, 0.0]
    result = run_backtest(panel, target, config())
    assert result.final_positions.iloc[0]["sec_id"] == "000001.SZ"
    assert result.final_positions.iloc[0]["qty"] == 500


def test_persisted_events_replay_and_legacy_runs_keep_their_original_semantics(
    tmp_path: Path,
) -> None:
    panel = action_panel(split=2.0)
    store = ExperimentStore(tmp_path)
    spec = StrategySpec(name="split", template="buy_and_hold")
    current = run_experiment(store, spec, panel=panel, config=config())
    assert replay_experiment(store, current.run_id).matched
    assert load_bundle(store, current.run_id).config.use_panel_corporate_actions
    old = run_experiment(store, spec, panel=panel, config=config(use_panel_corporate_actions=False))
    old_config = dict(old.metadata["config"])
    old_config.pop("use_panel_corporate_actions")
    old_config["corporate_actions"] = [{"sec": 0, "ex_date": 20260107, "split_ratio": 2.0}]
    store.update_metadata(old.run_id, {"config": old_config})
    assert replay_experiment(store, old.run_id).matched
    assert not load_bundle(store, old.run_id).config.use_panel_corporate_actions
    assert BacktestConfig.from_dict(old_config).corporate_actions == old_config["corporate_actions"]


def test_split_sell_metrics_use_the_split_adjusted_cost_basis() -> None:
    panel = action_panel(split=2.0)
    after = panel.bars.date >= 20260107
    panel.bars.loc[after, ["open", "close"]] = 6.0
    panel.bars.loc[after, "high"] = 6.2
    panel.bars.loc[after, "low"] = 5.8
    panel.bars["limit_up"] = 100.0
    panel.bars["limit_down"] = 0.01
    target = np.full((4, 1), np.nan)
    target[:, 0] = [0.1, 0.06, 0.0, np.nan]
    result = run_backtest(panel, target, config())
    assert result.equity_yuan[-1] == 10_200
    assert result.metrics["win_rate"] == 1.0
    assert np.isinf(result.metrics["profit_factor"])


@pytest.mark.parametrize("explicit", [False, True])
def test_unsupported_rights_are_not_silently_ignored(explicit: bool) -> None:
    panel = action_panel()
    settings = config()
    if explicit:
        settings.corporate_actions = [{"sec": 0, "ex_date": 20260107, "rights_ratio": 0.1}]
    else:
        panel.corporate_actions["rights_ratio"] = 0.1
    with pytest.raises(BacktestError, match="rights subscriptions"):
        run_backtest(panel, weights(panel), settings)


def test_unimplemented_dividend_tax_is_not_silently_ignored() -> None:
    panel = action_panel(cash=0.5)
    settings = config()
    settings.costs.enable_dividend_tax = True
    with pytest.raises(ValueError, match="dividend tax is not implemented"):
        run_backtest(panel, weights(panel), settings)


@pytest.mark.parametrize(("cash", "split"), [(0.0, 2.0), (0.5, 1.0), (0.5, 2.0)])
def test_suspended_ex_date_adjusts_the_stale_mark(cash: float, split: float) -> None:
    panel = action_panel(cash=cash, split=split)
    ex_date = panel.bars.date == 20260107
    panel.bars.loc[ex_date, ["open", "high", "low", "close"]] = np.nan
    panel.bars.loc[ex_date, "volume"] = 0
    panel.bars.loc[ex_date, "suspended"] = True
    result = run_backtest(panel, weights(panel), config())
    assert result.equity_yuan.tolist() == pytest.approx([10_000] * 4)


def test_consecutive_suspended_ex_dates_compound_reference_adjustments() -> None:
    from tests.reference.engine_ref import run_reference
    from tests.reference.engine_ref_primitives import RefConfig

    panel = action_panel(split=2.0)
    panel.corporate_actions = pd.concat(
        [
            panel.corporate_actions,
            panel.corporate_actions.assign(ex_date=20260108),
        ],
        ignore_index=True,
    )
    suspended = panel.bars.date >= 20260107
    panel.bars.loc[suspended, ["open", "high", "low", "close"]] = np.nan
    panel.bars.loc[suspended, "volume"] = 0
    panel.bars.loc[suspended, "suspended"] = True
    result = run_backtest(panel, weights(panel), config())
    assert result.equity_yuan.tolist() == pytest.approx([10_000] * 4)
    assert result.final_positions.iloc[0]["qty"] == 2_000
    reference = run_reference(
        panel,
        weights(panel),
        RefConfig(
            initial_cash=100_000_000,
            commission_rate=0,
            min_commission=0,
            stamp_duty_rate=0,
            transfer_fee_rate=0,
            exchange_fee_rate=0,
            reg_fee_rate=0,
        ),
    )
    np.testing.assert_array_equal(result.equity, reference.equity)
