"""Historical paper holdings settle the same ex-date model as native backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore.backtest.engine import run_backtest
from quantcore.calendar import TradingCalendar
from quantcore.paper import PaperMarketData, PaperSessionEngine, PaperStore, PaperValidationError
from tests.test_corporate_backtest import action_panel, config, weights


def paper(panel):
    market = PaperMarketData(panel)
    session = PaperSessionEngine.create(market, snapshot={}, initial_cash=10_000)
    session.config["costs"] = config().costs.model_dump(mode="json")
    return PaperSessionEngine(market, session)


@pytest.mark.parametrize(("cash", "split"), [(0.5, 1.0), (0.0, 2.0), (0.5, 2.0)])
def test_cash_and_split_conserve_equity_and_match_native(cash, split):
    panel = action_panel(cash=cash, split=split)
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=500)
    account.step()
    assert account.session.positions["600000.SH"].available == 0
    result = account.step()
    native = run_backtest(panel, weights(panel), config())
    assert result["account"]["equity"] == pytest.approx(10_000)
    assert result["account"]["cash"] == native.cash[2] / 10_000
    position = account.session.positions["600000.SH"]
    assert position.qty == position.available == int(500 * split)
    assert position.avg_cost * position.qty == pytest.approx(5_000)
    np.testing.assert_allclose(
        [point["equity"] for point in account.session.equity_curve], native.equity_yuan[:3]
    )


def test_event_audit_pending_orders_restart_and_reset(tmp_path):
    panel = action_panel(cash=0.5, split=2)
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=500)
    account.step()
    pending = account.submit_order(
        code="600000", side="buy", qty=100, order_type="limit", limit_price=1
    )
    payload = account.step()
    assert pending.status == "cancelled" and "corporate action" in pending.reason
    event = payload["corporate_events"][0]
    assert event["cash"] == 250
    assert event["qty_before"] == 500 and event["qty_after"] == 1000
    assert event["cancelled_order_ids"] == [pending.id]
    assert event["model"] == "pre_tax_ex_date_approximation"
    store = PaperStore(tmp_path)
    store.save(account.session)
    restored = PaperSessionEngine(account.market, store.load(account.session.id))
    assert restored.detail()["corporate_events"] == [event]
    assert restored.session.positions["600000.SH"].lots == [1000]
    restored.step()
    assert restored.session.cash == 5250 and len(restored.session.corporate_events) == 1
    restored.reset()
    assert restored.session.corporate_events == []
    restored.submit_order(code="600000", side="buy", qty=500)
    restored.step(days=2)
    assert restored.session.cash == 5250 and len(restored.session.corporate_events) == 1


@pytest.mark.parametrize("finite_close", [False, True])
def test_halted_ex_date_keeps_rebased_mark_through_later_halt(finite_close):
    panel = action_panel(cash=0.5, split=2)
    halted = panel.bars.date >= 20260107
    panel.bars.loc[halted, ["open", "high", "low", "close"]] = 10.0 if finite_close else np.nan
    panel.bars.loc[halted, "volume"] = 0
    panel.bars.loc[halted, "suspended"] = True
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=500)
    account.step(days=3)
    native = run_backtest(panel, weights(panel), config())
    np.testing.assert_allclose(
        [point["equity"] for point in account.session.equity_curve], native.equity_yuan
    )
    assert account.session.positions["600000.SH"].last == 4.75


def test_consecutive_halted_events_compound_without_stale_close_reset():
    panel = action_panel(cash=0.5, split=2)
    panel.corporate_actions = pd.concat(
        [panel.corporate_actions, panel.corporate_actions.assign(ex_date=20260108)],
        ignore_index=True,
    )
    halted = panel.bars.date >= 20260107
    panel.bars.loc[halted, "close"] = 10
    panel.bars.loc[halted, "suspended"] = True
    panel.bars.loc[halted, "volume"] = 0
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=500)
    account.step(days=3)
    native = run_backtest(panel, weights(panel), config())
    np.testing.assert_allclose(
        [point["equity"] for point in account.session.equity_curve], native.equity_yuan
    )
    assert account.session.cash == 5750
    assert account.session.positions["600000.SH"].last == 2.125


def test_split_rounds_each_acquisition_lot_like_native():
    panel = action_panel(split=1.125)
    panel.corporate_actions["ex_date"] = 20260108
    before = panel.bars.date < 20260108
    panel.bars.loc[before, ["open", "close"]] = 10
    panel.bars.loc[before, "high"] = 10.2
    panel.bars.loc[before, "low"] = 9.8
    panel.bars["limit_up"], panel.bars["limit_down"] = 100.0, 0.01
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=100)
    account.step()
    account.submit_order(code="600000", side="buy", qty=100)
    account.step()
    account.step()
    target = np.full((4, 1), np.nan)
    target[0, 0], target[1, 0] = 0.1, 0.2
    native = run_backtest(panel, target, config())
    position = account.session.positions["600000.SH"]
    assert position.qty == native.final_positions.iloc[0]["qty"] == 226
    assert position.available == 226 and position.lots == [113, 113]
    assert position.avg_cost * position.qty == pytest.approx(2000, abs=0.001)


@pytest.mark.parametrize("kind", ["rights", "tax", "invalid_cash", "invalid_split"])
def test_unsupported_models_fail_before_advancing_account(kind):
    panel = action_panel(cash=0.5)
    if kind == "rights":
        panel.corporate_actions["rights_ratio"] = 0.1
    elif kind == "invalid_cash":
        panel.corporate_actions["cash_per_share"] = np.nan
    elif kind == "invalid_split":
        panel.corporate_actions["split_ratio"] = 0
    market = PaperMarketData(panel)
    session = PaperSessionEngine.create(market, snapshot={}, initial_cash=10_000)
    if kind == "tax":
        session.config["costs"]["enable_dividend_tax"] = True
    with pytest.raises(PaperValidationError):
        PaperSessionEngine(market, session)
    assert session.cash == 10_000 and session.current_date == 20260105
    assert session.corporate_events == []


def test_old_position_without_lots_migrates_and_ex_date_buy_is_not_entitled():
    panel = action_panel(split=2)
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=100)
    account.step()
    position = account.session.positions["600000.SH"]
    position.lots.clear()
    account.step()
    assert position.qty == 200 and position.lots == [200]
    # A new ex-date order executes next day; it is not retroactively split.
    account.submit_order(code="600000", side="buy", qty=100)
    account.step()
    assert position.qty == 300 and position.available == 200
    assert position.lots == [200, 100]


def test_fresh_close_after_halt_replaces_mark_without_reapplying_event():
    panel = action_panel(cash=0.5, split=2)
    panel.calendar = TradingCalendar((*panel.calendar.dates, 20260109))
    resumed = panel.bars.iloc[[-1]].copy()
    resumed["date"] = 20260109
    resumed[["open", "close"]] = 6
    resumed["high"], resumed["low"] = 6.2, 5.8
    panel.bars = pd.concat([panel.bars, resumed], ignore_index=True)
    halted = panel.bars.date.isin([20260107, 20260108])
    panel.bars.loc[halted, "close"] = 10
    panel.bars.loc[halted, "volume"] = 0
    panel.bars.loc[halted, "suspended"] = True
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=500)
    account.step(days=4)
    native = run_backtest(panel, weights(panel), config())
    np.testing.assert_allclose(
        [point["equity"] for point in account.session.equity_curve], native.equity_yuan
    )
    assert account.session.positions["600000.SH"].last == 6
    assert account.session.cash == 5250 and len(account.session.corporate_events) == 1


def test_incompatible_cash_event_fails_without_partial_advance_or_cash_credit():
    panel = action_panel(cash=0.5)
    panel.corporate_actions["cash_per_share"] = 20
    account = paper(panel)
    account.submit_order(code="600000", side="buy", qty=100)
    account.step()
    before = account.session.to_dict()
    with pytest.raises(PaperValidationError, match="unsupported zero shares or price"):
        account.step()
    assert account.session.to_dict() == before
