"""Unit tests for the M9 paper-trading engine (simulation only; no real orders)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quantcore.paper import (
    PaperConflictError,
    PaperMarketData,
    PaperNotFoundError,
    PaperSessionEngine,
    PaperStore,
    PaperValidationError,
)
from quantcore.paper.rules import round_to_tick

SNAPSHOT_META = {
    "id": "snap_test",
    "synthetic": True,
    "source": "SYNTHETIC",
    "content_hash": "deadbeef",
    "n_sec": 0,
    "n_time": 0,
    "start": 0,
    "end": 0,
}


def _tradable_sec(market: PaperMarketData, day: int) -> int | None:
    for sec in range(market.n_sec):
        open_px = market.value("open", day, sec)
        high = market.value("high", day, sec)
        low = market.value("low", day, sec)
        close = market.value("close", day, sec)
        volume = market.value("volume", day, sec)
        suspended = market.value("suspended", day, sec)
        if not all(np.isfinite(v) and v > 0 for v in (open_px, high, low, close, volume)):
            continue
        if high <= low or (np.isfinite(suspended) and suspended > 0.5):
            continue
        limit_up = market.value("limit_up", day, sec)
        if np.isfinite(limit_up) and limit_up > 0 and open_px >= limit_up:
            continue
        return sec
    return None


def _plan(market: PaperMarketData) -> tuple[int, int, int, int]:
    """Pick (start_idx, end_idx, fill_day_idx, sec_idx) with a tradable fill day."""
    for fill_day in range(2, min(market.n_time - 1, 60)):
        sec = _tradable_sec(market, fill_day)
        if sec is not None:
            start_idx = fill_day - 1
            end_idx = min(fill_day + 8, market.n_time - 1)
            return start_idx, end_idx, fill_day, sec
    pytest.skip("no tradable synthetic security found")


@pytest.fixture(scope="module")
def market(synthetic_snapshot: object) -> PaperMarketData:
    panel = synthetic_snapshot.to_panel_data()  # type: ignore[attr-defined]
    return PaperMarketData(panel)


def _new_engine(
    market: PaperMarketData,
    *,
    start_idx: int = 0,
    end_idx: int = 8,
    initial_cash: float = 1_000_000.0,
    name: str = "unit",
) -> tuple[PaperSessionEngine, object]:
    session = PaperSessionEngine.create(
        market,
        snapshot=SNAPSHOT_META,
        initial_cash=initial_cash,
        start=market.dates[start_idx],
        end=market.dates[end_idx],
        name=name,
    )
    return PaperSessionEngine(market, session), session


def test_create_session_contract(market: PaperMarketData) -> None:
    start_idx, end_idx, _, _ = _plan(market)
    _engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    view = session.session_view()
    for key in (
        "id",
        "name",
        "status",
        "snapshot",
        "current_date",
        "cash",
        "equity",
        "starting_cash",
        "created_at",
    ):
        assert key in view, key
    assert view["status"] == "active"
    assert view["current_date"] == market.dates[start_idx]
    assert view["cash"] == view["starting_cash"] == 1_000_000.0
    assert view["equity"] == 1_000_000.0
    assert view["snapshot"] == "snap_test"
    assert session.equity_curve == [{"date": market.dates[start_idx], "equity": 1_000_000.0}]
    detail = _engine.detail()
    assert detail["account"]["market_value"] == 0.0
    assert detail["positions"] == [] and detail["trades"] == []


def test_create_rejects_inverted_dates(market: PaperMarketData) -> None:
    with pytest.raises(PaperValidationError):
        PaperSessionEngine.create(
            market,
            snapshot=SNAPSHOT_META,
            start=market.dates[10],
            end=market.dates[5],
        )
    with pytest.raises(PaperValidationError):
        PaperSessionEngine.create(market, snapshot=SNAPSHOT_META, initial_cash=0)


def test_store_persists_and_reopens(market: PaperMarketData, tmp_path: Path) -> None:
    start_idx, end_idx, _, _ = _plan(market)
    _engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    store = PaperStore(tmp_path / "paper")
    store.save(session)
    assert store.path_for(session.id).exists()
    reopened = store.load(session.id)
    assert reopened.id == session.id
    assert reopened.current_date == session.current_date
    assert reopened.cash == session.cash
    listed = store.list()
    assert [item.id for item in listed] == [session.id]
    reopened_engine = PaperSessionEngine(market, reopened)
    assert reopened_engine.detail()["session"]["id"] == session.id
    store.delete(session.id)
    with pytest.raises(PaperNotFoundError):
        store.load(session.id)
    with pytest.raises(PaperNotFoundError):
        store.delete(session.id)


def test_buy_fill_fees_t_plus_one_and_sell(market: PaperMarketData) -> None:
    start_idx, end_idx, fill_day, sec = _plan(market)
    engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    code = market.code(sec)
    order = engine.submit_order(code=code, side="buy", qty=100)
    assert order.status == "pending" and order.side_name == "buy"

    detail = engine.step()
    assert detail["session"]["current_date"] == market.dates[fill_day]
    assert detail["fills"] and detail["fills"][0]["side"] == "buy"
    trade = detail["trades"][0]
    expected_open = market.value("open", fill_day, sec)
    expected_low = market.value("low", fill_day, sec)
    expected_high = market.value("high", fill_day, sec)
    assert expected_low - 1e-9 <= trade["price"] <= expected_high + 1e-9
    assert trade["price"] == pytest.approx(expected_open, abs=0.011)
    assert trade["qty"] == 100
    assert trade["fee_total"] >= 5.0
    position = detail["positions"][0]
    assert position["qty"] == 100 and position["available"] == 0
    assert detail["orders"][0]["status"] == "filled"
    assert session.cash == pytest.approx(
        1_000_000.0 - trade["amount"] - trade["fee_total"], abs=1e-3
    )

    with pytest.raises(PaperValidationError, match="T\\+1"):
        engine.submit_order(code=code, side="sell", qty=100)
    engine.step()
    sell = engine.submit_order(code=code, side="sell", qty=100)
    assert sell.status == "pending"
    detail = engine.step()
    sell_trade = [item for item in detail["trades"] if item["side"] == "sell"][-1]
    assert sell_trade["fees"]["stamp_duty"] > 0
    assert detail["positions"] == []
    assert session.cash == pytest.approx(
        1_000_000.0
        - trade["amount"]
        - trade["fee_total"]
        + sell_trade["amount"]
        - sell_trade["fee_total"],
        abs=1e-3,
    )
    assert len(session.equity_curve) == 4


def test_limit_order_fills_at_limit_then_cancel(market: PaperMarketData) -> None:
    # find a day whose open is a few ticks above the low, so a buy limit can fill between.
    chosen: tuple[int, int, float] | None = None
    for day in range(2, min(market.n_time - 1, 80)):
        sec = _tradable_sec(market, day)
        if sec is None:
            continue
        open_px = market.value("open", day, sec)
        low = market.value("low", day, sec)
        if open_px - low < 0.05:
            continue
        limit = round_to_tick(open_px - 0.02)
        if low <= limit < open_px:
            chosen = (day, sec, limit)
            break
    assert chosen is not None, "no limit order test day found"
    fill_day, sec, limit = chosen
    engine, _session = _new_engine(
        market, start_idx=fill_day - 1, end_idx=min(fill_day + 4, market.n_time - 1)
    )
    engine.submit_order(
        code=market.code(sec), side="buy", qty=100, order_type="limit", limit_price=limit
    )
    detail = engine.step()
    assert detail["fills"], "limit order should fill inside the day's range"
    assert detail["fills"][0]["price"] == pytest.approx(limit, abs=1e-9)

    # a limit far below the day's range stays pending until cancelled
    pending = engine.submit_order(
        code=market.code(sec), side="buy", qty=100, order_type="limit", limit_price=0.01
    )
    engine.step()
    assert pending.status == "pending"
    cancelled = engine.cancel_order(pending.id)
    assert cancelled.status == "cancelled"
    with pytest.raises(PaperConflictError, match="already cancelled"):
        engine.cancel_order(pending.id)
    detail = engine.detail()
    assert any(item["status"] == "cancelled" for item in detail["orders"])


def test_step_days_to_date_and_finished(market: PaperMarketData) -> None:
    start_idx, end_idx, _, _ = _plan(market)
    engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    detail = engine.step(days=2)
    assert detail["session"]["current_date"] == market.dates[start_idx + 2]
    assert len(session.equity_curve) == 3
    with pytest.raises(PaperValidationError):
        engine.step(to_date=market.dates[start_idx])
    detail = engine.step(to_date=market.dates[end_idx])
    assert detail["session"]["current_date"] == market.dates[end_idx]
    assert detail["session"]["status"] == "finished"
    with pytest.raises(PaperValidationError):
        engine.step()
    with pytest.raises(PaperValidationError):
        engine.submit_order(code=market.code(0), side="buy", qty=100)


def test_reset_restores_initial_state(market: PaperMarketData) -> None:
    start_idx, end_idx, _, sec = _plan(market)
    engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    engine.submit_order(code=market.code(sec), side="buy", qty=100)
    engine.step()
    assert session.positions
    detail = engine.reset()
    assert detail["session"]["current_date"] == market.dates[start_idx]
    assert detail["account"]["cash"] == 1_000_000.0
    assert detail["account"]["equity"] == 1_000_000.0
    assert detail["positions"] == [] and detail["trades"] == [] and detail["orders"] == []
    assert len(detail["equity_curve"]) == 1
    assert detail["session"]["status"] == "active"


def test_order_validation(market: PaperMarketData) -> None:
    start_idx, end_idx, _, sec = _plan(market)
    engine, _ = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    code = market.code(sec)
    with pytest.raises(PaperValidationError, match=r"(multiple|at least)"):
        engine.submit_order(code=code, side="buy", qty=50)
    with pytest.raises(PaperValidationError, match="not found"):
        engine.submit_order(code="NOPE.XX", side="buy", qty=100)
    with pytest.raises(PaperValidationError, match="no position"):
        engine.submit_order(code=code, side="sell", qty=100)
    with pytest.raises(PaperValidationError, match="limit_price"):
        engine.submit_order(code=code, side="buy", qty=100, order_type="limit")
    with pytest.raises(PaperValidationError, match="only valid"):
        engine.submit_order(code=code, side="buy", qty=100, order_type="market", limit_price=10.0)


def test_signals_csv(market: PaperMarketData) -> None:
    start_idx, end_idx, _, sec = _plan(market)
    engine, _ = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    engine.submit_order(code=market.code(sec), side="buy", qty=100)
    engine.step()
    text = engine.signals_csv()
    lines = text.strip().splitlines()
    assert lines[0].startswith("date,code,name,side")
    assert any("buy" in line and "filled" in line for line in lines)
    assert market.code(sec) in text


def test_reopen_engine_continues(market: PaperMarketData) -> None:
    start_idx, end_idx, fill_day, sec = _plan(market)
    engine, session = _new_engine(market, start_idx=start_idx, end_idx=end_idx)
    engine.submit_order(code=market.code(sec), side="buy", qty=100)
    engine.step()
    reopened = PaperSessionEngine(market, session)
    assert reopened.detail()["session"]["current_date"] == market.dates[fill_day]
    detail = reopened.step()
    assert detail["session"]["current_date"] == market.dates[fill_day + 1]
    assert detail["positions"][0]["available"] == 100
