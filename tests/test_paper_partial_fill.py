"""M9 partial-fill tests: participation cap, cross-day fills, T+1 and legacy JSON.

Simulation only: no broker gateway, no network access and no real order routing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from quantcore.data.panel import PanelData
from quantcore.paper import (
    PaperConflictError,
    PaperMarketData,
    PaperSessionEngine,
    PaperStore,
    PaperValidationError,
)
from quantcore.paper.models import PaperSession
from quantcore.paper.rules import DEFAULT_PARTICIPATION, participation_rate, round_to_tick

SNAPSHOT_META: dict[str, Any] = {
    "id": "snap_partial",
    "synthetic": True,
    "source": "SYNTHETIC",
    "content_hash": "deadbeef",
    "n_sec": 0,
    "n_time": 0,
    "start": 0,
    "end": 0,
}


def _tradable(market: PaperMarketData, day: int, sec: int) -> bool:
    open_px = market.value("open", day, sec)
    high = market.value("high", day, sec)
    low = market.value("low", day, sec)
    close = market.value("close", day, sec)
    volume = market.value("volume", day, sec)
    suspended = market.value("suspended", day, sec)
    limit_up = market.value("limit_up", day, sec)
    if not all(np.isfinite(value) and value > 0 for value in (open_px, high, low, close, volume)):
        return False
    if high <= low or (np.isfinite(suspended) and suspended > 0.5):
        return False
    return not (np.isfinite(limit_up) and limit_up > 0 and open_px >= limit_up)


def _window(
    market: PaperMarketData, days: int, *, board: str = "MAIN", before: int = 1
) -> tuple[int, int]:
    """Return (first fill day index, sec index) with a tradable run before and after it."""
    last = min(market.n_time - days - 1, 250)
    for day in range(2 + before, last):
        for sec in range(market.n_sec):
            if market.board(sec) != board:
                continue
            if all(_tradable(market, day + offset, sec) for offset in range(-before, days)):
                return day, sec
    pytest.skip(f"no {board} window with {days} tradable days")


def _market_with_volume(panel: PanelData, overrides: dict[tuple[int, int], int]) -> PaperMarketData:
    """Copy the panel, replacing volume for (day index, sec index) pairs."""
    bars = panel.bars.copy()
    for (day, sec), volume in overrides.items():
        date = int(panel.calendar.dates[day])
        mask = (bars["date"] == date) & (bars["sec_id"] == panel.sec_ids[sec])
        bars.loc[mask, "volume"] = int(volume)
    modified = PanelData(
        calendar=panel.calendar,
        securities=panel.securities.copy(),
        bars=bars,
        meta=dict(panel.meta),
    )
    return PaperMarketData(modified)


def _engine(
    market: PaperMarketData,
    start_day: int,
    end_day: int,
    *,
    participation: float | None = None,
) -> tuple[PaperSessionEngine, PaperSession]:
    session = PaperSessionEngine.create(
        market,
        snapshot=SNAPSHOT_META,
        start=market.dates[start_day],
        end=market.dates[end_day],
        name="partial",
    )
    if participation is not None:
        session.config["execution"]["participation"] = participation
    return PaperSessionEngine(market, session), session


def _assert_identities(engine: PaperSessionEngine) -> None:
    """Cash, fees, filled_qty and equity stay internally consistent after every fill."""
    session = engine.session
    fees = sum(float(trade.fees.get("fee_total", 0.0)) for trade in session.trades)
    buys = sum(trade.amount for trade in session.trades if trade.side == 0)
    sells = sum(trade.amount for trade in session.trades if trade.side == 1)
    assert session.cash == pytest.approx(session.initial_cash - buys + sells - fees, abs=1e-3)
    assert session.equity() == pytest.approx(session.cash + session.market_value(), abs=1e-6)
    for order in session.orders:
        order_fills = [trade for trade in session.trades if trade.order_id == order.id]
        assert order.filled_qty == sum(trade.qty for trade in order_fills)
        if not order_fills:
            continue
        for key in ("commission", "stamp_duty", "transfer_fee", "other_fee", "fee_total"):
            expected = sum(float(trade.fees.get(key, 0.0)) for trade in order_fills)
            assert float((order.fees or {}).get(key, 0.0)) == pytest.approx(expected, abs=1e-6)


@pytest.fixture(scope="module")
def market(small_panel: PanelData) -> PaperMarketData:
    return PaperMarketData(small_panel)


def test_default_participation_and_liquid_full_fill(market: PaperMarketData) -> None:
    assert participation_rate(None) == DEFAULT_PARTICIPATION
    day, sec = _window(market, 2)
    engine, session = _engine(market, day - 1, day + 3)
    assert session.config["execution"]["participation"] == DEFAULT_PARTICIPATION
    assert engine.participation == DEFAULT_PARTICIPATION
    engine.submit_order(code=market.code(sec), side="buy", qty=300)
    detail = engine.step()
    order = detail["orders"][0]
    assert order["status"] == "filled" and order["filled_qty"] == 300
    assert len(order["fills"]) == 1 and order["fills"][0]["qty"] == 300
    assert len(detail["trades"]) == 1
    assert detail["session"]["pending_orders"] == 0
    _assert_identities(engine)


def test_participation_one_matches_legacy_full_fill(market: PaperMarketData) -> None:
    day, sec = _window(market, 2)
    legacy, legacy_session = _engine(market, day - 1, day + 3, participation=1.0)
    default, default_session = _engine(market, day - 1, day + 3)
    for engine in (legacy, default):
        engine.submit_order(code=market.code(sec), side="buy", qty=500)
    legacy_detail = legacy.step()
    default_detail = default.step()
    for detail in (legacy_detail, default_detail):
        order = detail["orders"][0]
        assert order["status"] == "filled" and order["filled_qty"] == 500
        assert len(order["fills"]) == 1
    legacy_trade = legacy_detail["trades"][0]
    default_trade = default_detail["trades"][0]
    for key in ("price", "qty", "amount", "fee_total"):
        assert legacy_trade[key] == default_trade[key]
    assert legacy_session.cash == default_session.cash
    assert legacy_detail["positions"] == default_detail["positions"]


def test_partial_fill_continues_across_days_until_filled(
    small_panel: PanelData, market: PaperMarketData
) -> None:
    day, sec = _window(market, 4)
    modified = _market_with_volume(
        small_panel, {(day, sec): 2000, (day + 1, sec): 2000, (day + 2, sec): 2000}
    )
    engine, _session = _engine(modified, day - 1, day + 4)
    engine.submit_order(code=modified.code(sec), side="buy", qty=500)

    first = engine.step()
    order = first["orders"][0]
    assert order["status"] == "partial" and order["filled_qty"] == 200
    assert len(first["fills"]) == 1 and first["fills"][0]["qty"] == 200
    assert first["session"]["pending_orders"] == 1
    assert first["positions"][0]["qty"] == 200 and first["positions"][0]["available"] == 0
    _assert_identities(engine)

    second = engine.step()
    order = second["orders"][0]
    assert order["status"] == "partial" and order["filled_qty"] == 400
    _assert_identities(engine)

    third = engine.step()
    order = third["orders"][0]
    assert order["status"] == "filled" and order["filled_qty"] == 500
    assert len(order["fills"]) == 3 and len(third["trades"]) == 3
    assert third["positions"][0]["qty"] == 500
    notional = sum(trade["amount"] for trade in third["trades"])
    assert order["fill_price"] == pytest.approx(notional / 500, abs=1e-4)
    _assert_identities(engine)

    csv_rows = engine.signals_csv().strip().splitlines()
    assert csv_rows[0].startswith("date,code,name,side")
    columns = csv_rows[1].split(",")
    assert columns[7] == "filled" and columns[8] == "500"
    assert float(columns[9]) == pytest.approx(order["fill_price"], abs=0.01)


def test_cap_below_one_board_lot_stays_pending(
    small_panel: PanelData, market: PaperMarketData
) -> None:
    day, sec = _window(market, 3)
    modified = _market_with_volume(small_panel, {(day, sec): 500})
    engine, _session = _engine(modified, day - 1, day + 3)
    engine.submit_order(code=modified.code(sec), side="buy", qty=1000)

    detail = engine.step()
    order = detail["orders"][0]
    assert order["status"] == "pending" and order["filled_qty"] == 0
    assert detail["fills"] == [] and detail["trades"] == []

    detail = engine.step()
    order = detail["orders"][0]
    assert order["status"] == "filled" and order["filled_qty"] == 1000
    assert len(detail["trades"]) == 1


def _limit_window(market: PaperMarketData) -> tuple[int, int, float]:
    for day in range(2, min(market.n_time - 3, 200)):
        for sec in range(market.n_sec):
            if market.board(sec) != "MAIN":
                continue
            days = (day - 1, day, day + 1)
            if not all(_tradable(market, item, sec) for item in days):
                continue
            low_today = market.value("low", day, sec)
            high_today = market.value("high", day, sec)
            low_next = market.value("low", day + 1, sec)
            limit = round_to_tick(max(low_today, low_next))
            if market.value("open", day, sec) > limit and low_today <= limit <= high_today:
                return day, sec, limit
    pytest.skip("no limit-order window found")


def test_limit_order_partial_then_continues(
    small_panel: PanelData, market: PaperMarketData
) -> None:
    day, sec, limit = _limit_window(market)
    modified = _market_with_volume(small_panel, {(day, sec): 2000})
    engine, _session = _engine(modified, day - 1, day + 4)
    engine.submit_order(
        code=modified.code(sec),
        side="buy",
        qty=500,
        order_type="limit",
        limit_price=limit,
    )
    first = engine.step()
    order = first["orders"][0]
    assert order["status"] == "partial" and order["filled_qty"] == 200
    assert first["fills"][0]["price"] == pytest.approx(limit, abs=1e-9)

    second = engine.step()
    order = second["orders"][0]
    assert order["status"] == "filled" and order["filled_qty"] == 500
    assert len(order["fills"]) == 2


def test_sell_partial_available_semantics(small_panel: PanelData, market: PaperMarketData) -> None:
    day, sec = _window(market, 3, before=2)
    modified = _market_with_volume(small_panel, {(day + 1, sec): 2000})
    engine, session = _engine(modified, day - 2, day + 4)
    code = modified.code(sec)
    engine.submit_order(code=code, side="buy", qty=500)
    engine.step()  # day - 1: buy fills at the open

    position = session.positions[modified.sec_ids[sec]]
    assert (position.qty, position.available) == (500, 0)
    with pytest.raises(PaperValidationError, match=r"T\+1"):
        engine.submit_order(code=code, side="sell", qty=500)

    engine.step()  # day: T+1 makes yesterday's shares sellable
    position = session.positions[modified.sec_ids[sec]]
    assert position.available == 500
    engine.submit_order(code=code, side="sell", qty=400)

    partial = engine.step()  # day + 1: volume cap only allows 200 shares
    order = partial["orders"][-1]
    assert order["status"] == "partial" and order["filled_qty"] == 200
    position = session.positions[modified.sec_ids[sec]]
    assert (position.qty, position.available) == (300, 300)

    final = engine.step()  # day + 2: remaining 200 shares fill
    order = final["orders"][-1]
    assert order["status"] == "filled" and order["filled_qty"] == 400
    position = session.positions[modified.sec_ids[sec]]
    assert (position.qty, position.available) == (100, 100)
    _assert_identities(engine)


def test_partial_order_can_be_cancelled(small_panel: PanelData, market: PaperMarketData) -> None:
    day, sec = _window(market, 4)
    modified = _market_with_volume(small_panel, {(day, sec): 2000, (day + 1, sec): 2000})
    engine, _session = _engine(modified, day - 1, day + 4)
    order = engine.submit_order(code=modified.code(sec), side="buy", qty=500)
    engine.step()
    assert order.status == "partial" and order.filled_qty == 200

    engine.cancel_order(order.id)
    assert order.status == "cancelled" and order.reason == "cancelled by user"
    detail = engine.step()
    assert order.filled_qty == 200 and detail["fills"] == []
    with pytest.raises(PaperConflictError, match="already cancelled"):
        engine.cancel_order(order.id)


def test_legacy_session_json_without_execution_or_fills_loads(market: PaperMarketData) -> None:
    day, sec = _window(market, 3)
    engine, session = _engine(market, day - 1, day + 3, participation=1.0)
    engine.submit_order(code=market.code(sec), side="buy", qty=100)
    engine.step()

    payload = session.to_dict()
    payload.pop("config")
    for order in payload["orders"]:
        order.pop("fills")
    restored = PaperSession.from_dict(payload)
    assert restored.config == {}
    assert restored.orders[0].fills == []
    assert restored.orders[0].filled_qty == 100

    reopened = PaperSessionEngine(market, restored)
    assert reopened.participation == DEFAULT_PARTICIPATION
    detail = reopened.detail()
    assert detail["orders"][0]["status"] == "filled"
    assert detail["orders"][0]["fills"] == []
    reopened.submit_order(code=market.code(sec), side="buy", qty=100)
    detail = reopened.step()
    assert detail["orders"][-1]["status"] == "filled"
    _assert_identities(reopened)


def test_partial_order_persists_and_continues_after_reopen(
    small_panel: PanelData, market: PaperMarketData, tmp_path: Path
) -> None:
    day, sec = _window(market, 4)
    modified = _market_with_volume(small_panel, {(day, sec): 2000, (day + 1, sec): 2000})
    engine, session = _engine(modified, day - 1, day + 4)
    engine.submit_order(code=modified.code(sec), side="buy", qty=500)
    engine.step()

    store = PaperStore(tmp_path / "paper")
    store.save(session)
    reopened_session = store.load(session.id)
    assert reopened_session.orders[0].status == "partial"
    assert len(reopened_session.orders[0].fills) == 1
    assert reopened_session.config["execution"]["participation"] == DEFAULT_PARTICIPATION

    reopened = PaperSessionEngine(modified, reopened_session)
    detail = reopened.step()
    assert detail["orders"][0]["filled_qty"] == 400
    detail = reopened.step()
    assert detail["orders"][0]["status"] == "filled"
    assert len(detail["orders"][0]["fills"]) == 3
    _assert_identities(reopened)


def test_participation_config_validation(market: PaperMarketData) -> None:
    day, _sec = _window(market, 2)
    engine, session = _engine(market, day - 1, day + 2)
    assert engine.participation == DEFAULT_PARTICIPATION
    for bad in (0.0, -0.1, 1.5, "abc"):
        session.config["execution"] = {"participation": bad}
        with pytest.raises(PaperValidationError):
            PaperSessionEngine(market, session)
    session.config["execution"] = {"participation": 0.5}
    assert PaperSessionEngine(market, session).participation == 0.5
    assert participation_rate(0.25) == 0.25
