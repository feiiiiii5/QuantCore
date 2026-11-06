"""Fresh public quote updates drive only local virtual paper accounts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantcore.paper import LivePaperSessionEngine, PaperStore, PaperValidationError
from quantcore.realtime.clock import SHANGHAI_TZ
from quantcore.realtime.service import LiveConfig, LiveQuoteService
from quantcore.server import create_app


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[dt.datetime]:
    value = [dt.datetime(2026, 11, 2, 10, 15, 30, tzinfo=SHANGHAI_TZ)]
    monkeypatch.setattr("quantcore.paper.live._now", lambda: value[0].isoformat())
    return value


def quote(clock: list[dt.datetime], *, volume: float = 10000, price: float = 10, **extra) -> dict:
    return {
        "code": "600000",
        "name": "fixture",
        "price": price,
        "volume": volume,
        "source": "fixture",
        "timestamp": clock[0].isoformat(),
        "suspended": False,
        "limit_up": 11,
        "limit_down": 9,
        **extra,
    }


def refresh(
    engine: LivePaperSessionEngine,
    clock: list[dt.datetime],
    item: dict,
    *,
    phase: str = "open",
    enabled: bool = True,
) -> dict:
    return engine.refresh(
        {"quotes": [item], "stale": False},
        {"enabled": enabled, "market": {"phase": phase}},
        now=clock[0],
    )


def engine(clock: list[dt.datetime]) -> LivePaperSessionEngine:
    return LivePaperSessionEngine(
        LivePaperSessionEngine.create_live(initial_cash=10000, now=clock[0])
    )


def test_live_baseline_incremental_volume_fills_fees_and_persistence(clock, tmp_path) -> None:
    account = engine(clock)
    order = account.submit_order(code="600000", side="buy", qty=200)
    clock[0] += dt.timedelta(seconds=1)
    assert refresh(account, clock, quote(clock))["fills"] == []
    clock[0] += dt.timedelta(seconds=3)
    result = refresh(account, clock, quote(clock, volume=11000))
    assert order.status == "partial" and order.filled_qty == 100
    assert result["positions"][0]["available"] == 0
    assert result["account"]["cash"] < 9000  # Fee-inclusive simulated buy.
    assert refresh(account, clock, quote(clock, volume=11000))["fills"] == []
    clock[0] += dt.timedelta(seconds=3)
    result = refresh(account, clock, quote(clock, volume=12000))
    assert order.status == "filled" and len(result["trades"]) == 2
    store = PaperStore(tmp_path)
    store.save(account.session)
    restored = LivePaperSessionEngine(store.load(account.session.id))
    assert restored.detail()["positions"][0]["qty"] == 200
    assert restored.detail()["session"]["mode"] == "live"
    assert restored.detail()["positions"][0]["quote_timestamp"] == clock[0].isoformat()
    last_timestamp = clock[0].isoformat()
    clock[0] += dt.timedelta(seconds=20)
    stale = refresh(restored, clock, quote(clock, price=99, timestamp=last_timestamp))
    assert stale["positions"][0]["last"] == 10
    assert stale["positions"][0]["quote_timestamp"] == last_timestamp
    assert "陈旧" in stale["live"]["quotes"][0]["reason"]


@pytest.mark.parametrize(
    "bad",
    [
        {"timestamp": None},
        {"timestamp": "2026-11-02"},
        {"timestamp": "2026-11-02T09:00:00+08:00"},
        {"suspended": True},
    ],
)
def test_invalid_or_stale_quotes_never_fill(clock, bad: dict) -> None:
    account = engine(clock)
    account.submit_order(code="600000", side="buy", qty=100)
    refresh(account, clock, quote(clock))
    clock[0] += dt.timedelta(seconds=3)
    result = refresh(account, clock, quote(clock, volume=20000, **bad))
    assert result["trades"] == []
    assert result["account"]["equity"] == 10000
    assert result["live"]["quotes"][0]["reason"]


@pytest.mark.parametrize("phase,enabled", [("closed", True), ("lunch", True), ("open", False)])
def test_no_fills_when_closed_or_feed_off(clock, phase: str, enabled: bool) -> None:
    account = engine(clock)
    account.submit_order(code="600000", side="buy", qty=100)
    refresh(account, clock, quote(clock))
    clock[0] += dt.timedelta(seconds=3)
    result = refresh(account, clock, quote(clock, volume=12000), phase=phase, enabled=enabled)
    assert result["trades"] == []


def test_volume_interval_must_begin_after_order_creation(clock) -> None:
    account = engine(clock)
    refresh(account, clock, quote(clock))
    clock[0] += dt.timedelta(seconds=1)
    order = account.submit_order(code="600000", side="buy", qty=100)
    clock[0] += dt.timedelta(seconds=2)
    refresh(account, clock, quote(clock, volume=12000))
    assert order.filled_qty == 0  # This volume interval began before the order existed.
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=13000))
    assert order.filled_qty == 100


def test_limits_use_future_last_price_and_liquidity_is_shared(clock) -> None:
    account = engine(clock)
    first = account.submit_order(
        code="600000", side="buy", qty=100, order_type="limit", limit_price=9.9
    )
    second = account.submit_order(code="600000", side="buy", qty=100)
    refresh(account, clock, quote(clock))
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=11000, price=10, low=9.0))
    assert first.filled_qty == 0  # Today's historical low cannot fill a later limit order.
    assert second.filled_qty == 100
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=12000, price=9.8))
    assert first.filled_qty == 100
    with pytest.raises(PaperValidationError, match=r"T\+1"):
        account.submit_order(code="600000", side="sell", qty=100)
    clock[0] = clock[0].replace(day=3)
    refresh(account, clock, quote(clock, volume=10000))
    sale = account.submit_order(code="600000", side="sell", qty=200)
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=12000))
    assert sale.status == "filled"
    assert account.session.positions == {}


class FixtureHttp:
    """Real service and parsers with local source rows, never external HTTP."""

    def __init__(self, clock: list[dt.datetime]) -> None:
        payload = json.loads(
            (Path(__file__).parent / "fixtures/live/eastmoney_ulist.json").read_text()
        )
        self.row = dict(payload["data"]["diff"][0])
        self.clock = clock

    async def get_json(self, url: str, *, headers=None):
        self.row["f124"] = int(self.clock[0].timestamp())
        return {"data": {"diff": [dict(self.row)]}}

    async def get_text(self, url: str, *, headers=None):
        raise AssertionError("valid fixture primary quotes need no fallback")


def test_live_api_full_order_refresh_cancel_reload_without_snapshot(clock, tmp_path) -> None:
    app = create_app(
        token="paper-token",
        data_root=tmp_path,
        state_path=tmp_path / "state.sqlite",
        experiments_root=tmp_path / "experiments",
        start_worker=False,
    )
    http = FixtureHttp(clock)
    live = LiveQuoteService(config=LiveConfig(enabled=True), http=http, clock=lambda: clock[0])
    app.state.live = live
    headers = {"Authorization": "Bearer paper-token"}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        created = client.post(
            "/api/paper/sessions", headers=headers, json={"mode": "live", "initial_cash": 10000}
        )
        assert created.status_code == 201, created.text
        sid = created.json()["id"]
        assert created.json()["snapshot"] is None
        submitted = client.post(
            f"/api/paper/sessions/{sid}/orders",
            headers=headers,
            json={"code": "600000", "side": "buy", "qty": 100},
        )
        assert submitted.status_code == 200, submitted.text
        first = client.post(f"/api/paper/sessions/{sid}/refresh", headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["trades"] == []
        clock[0] += dt.timedelta(seconds=4)
        http.row["f5"] = float(http.row["f5"]) + 1000  # Source lots become shares.
        import asyncio

        asyncio.run(live.refresh(["600000"]))
        filled = client.post(f"/api/paper/sessions/{sid}/refresh", headers=headers)
        assert filled.status_code == 200, filled.text
        assert filled.json()["orders"][0]["status"] == "filled"
        assert filled.json()["positions"][0]["qty"] == 100
        assert filled.json()["positions"][0]["available"] == 0
        assert client.post(f"/api/paper/sessions/{sid}/step", headers=headers).status_code == 400
        assert client.post(f"/api/paper/sessions/{sid}/auto", headers=headers).status_code == 400
        pending = client.post(
            f"/api/paper/sessions/{sid}/orders",
            headers=headers,
            json={
                "code": "600000",
                "side": "buy",
                "qty": 100,
                "order_type": "limit",
                "limit_price": 1,
            },
        )
        oid = pending.json()["order"]["id"]
        assert (
            client.post(
                f"/api/paper/sessions/{sid}/orders/{oid}/cancel", headers=headers
            ).status_code
            == 200
        )
        saved = PaperStore(tmp_path / "paper").load(sid)
        assert len(saved.trades) == 1 and saved.positions["SH.600000"].qty == 100


@pytest.mark.parametrize("side,price", [("buy", 11.0), ("sell", 9.0)])
def test_missing_quote_limits_are_derived_from_previous_close(
    clock, side: str, price: float
) -> None:
    account = engine(clock)
    if side == "sell":
        account.submit_order(code="600000", side="buy", qty=100)
        refresh(account, clock, quote(clock))
        clock[0] += dt.timedelta(seconds=3)
        refresh(account, clock, quote(clock, volume=11000))
        clock[0] += dt.timedelta(days=1)
        refresh(account, clock, quote(clock))
    order = account.submit_order(code="600000", side=side, qty=100)
    refresh(account, clock, quote(clock, limit_up=None, limit_down=None, prev_close=10))
    clock[0] += dt.timedelta(seconds=3)
    refresh(
        account,
        clock,
        quote(
            clock,
            price=price,
            volume=12000,
            limit_up=None,
            limit_down=None,
            prev_close=10,
            source="sina",
        ),
    )
    clock[0] += dt.timedelta(seconds=3)
    refresh(
        account,
        clock,
        quote(
            clock,
            price=price,
            volume=14000,
            limit_up=None,
            limit_down=None,
            prev_close=10,
            source="sina",
        ),
    )
    assert order.filled_qty == 0
    assert "涨跌停" in (order.reason or "")


def test_cumulative_volume_correction_cannot_reuse_a_fill_budget(clock, tmp_path) -> None:
    account = engine(clock)
    first = account.submit_order(code="600000", side="buy", qty=100)
    second = account.submit_order(code="600000", side="buy", qty=200)
    refresh(account, clock, quote(clock))
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=11000))
    assert first.filled_qty == 100
    assert second.filled_qty == 0  # One interval's shared budget is 100 shares.
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, volume=10000))  # Vendor corrects its cumulative count.
    store = PaperStore(tmp_path)
    store.save(account.session)
    restored = LivePaperSessionEngine(store.load(account.session.id))
    clock[0] += dt.timedelta(seconds=3)
    refresh(restored, clock, quote(clock, volume=11000))
    assert restored.session.orders[1].filled_qty == 0  # Already consumed before correction/reload.
    clock[0] += dt.timedelta(seconds=3)
    refresh(restored, clock, quote(clock, volume=12000))
    assert restored.session.orders[1].filled_qty == 100
    with pytest.raises(PaperValidationError, match=r"T\+1"):
        restored.submit_order(code="600000", side="sell", qty=100)
    restored.cancel_order(second.id)
    clock[0] += dt.timedelta(days=1)
    refresh(restored, clock, quote(clock, volume=100))  # New trading day resets the counter.
    sale = restored.submit_order(code="600000", side="sell", qty=100)
    clock[0] += dt.timedelta(seconds=3)
    refresh(restored, clock, quote(clock, volume=1100))
    assert sale.filled_qty == 100
    assert restored.session.orders[1].filled_qty == 100  # Cancellation prevents further fills.


def test_source_switch_and_restart_cannot_reuse_a_counted_volume_interval(clock, tmp_path) -> None:
    account = engine(clock)
    order = account.submit_order(code="600000", side="buy", qty=300)
    refresh(account, clock, quote(clock, source="eastmoney"))
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, source="eastmoney", volume=11000))
    assert order.filled_qty == 100
    # An existing session has only the most recent observation's source/volume.
    account.live["observations"]["600000"].pop("source_volumes", None)

    # The fallback and returning primary both report lower cumulative counters.
    for source in ("sina", "eastmoney"):
        clock[0] += dt.timedelta(seconds=3)
        assert refresh(account, clock, quote(clock, source=source))["fills"] == []
    store = PaperStore(tmp_path)
    store.save(account.session)
    restored = LivePaperSessionEngine(store.load(account.session.id))
    clock[0] += dt.timedelta(seconds=3)
    result = refresh(restored, clock, quote(clock, source="eastmoney", volume=11000))
    assert result["fills"] == []  # This primary-source interval already funded the first fill.
    assert restored.session.orders[0].filled_qty == 100

    clock[0] += dt.timedelta(seconds=3)
    result = refresh(restored, clock, quote(clock, source="eastmoney", volume=12000))
    assert len(result["fills"]) == 1
    assert restored.session.orders[0].filled_qty == 200  # Only genuinely new volume counts.


@pytest.mark.parametrize(
    "code,limit,qty,name,year",
    [
        ("688001", 12.0, 200, "fixture", 2026),
        ("920001", 13.0, 100, "fixture", 2026),
        ("600000", 10.5, 100, "*ST fixture", 2025),
    ],
)
def test_fallback_limits_reuse_board_and_dated_st_rules(
    clock, code, limit, qty, name, year
) -> None:
    clock[0] = clock[0].replace(year=year, day=3)
    account = engine(clock)
    order = account.submit_order(code=code, side="buy", qty=qty)
    common = {
        "code": code,
        "name": name,
        "source": "sina",
        "prev_close": 10,
        "limit_up": None,
        "limit_down": None,
    }
    refresh(account, clock, quote(clock, **common))
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, price=limit, volume=12000, **common))
    assert order.filled_qty == 0
    clock[0] += dt.timedelta(seconds=3)
    refresh(account, clock, quote(clock, price=limit - 0.01, volume=14000, **common))
    assert order.filled_qty == qty


def test_missing_limit_and_previous_close_waits_for_a_usable_quote(clock) -> None:
    account = engine(clock)
    order = account.submit_order(code="600000", side="buy", qty=100)
    refresh(account, clock, quote(clock, limit_up=None, limit_down=None, prev_close=0))
    clock[0] += dt.timedelta(seconds=3)
    refresh(
        account, clock, quote(clock, volume=12000, limit_up=None, limit_down=None, prev_close=0)
    )
    assert order.filled_qty == 0
    assert "前收盘价" in (order.reason or "")
