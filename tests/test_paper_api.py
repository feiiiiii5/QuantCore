"""API tests for M9 paper trading (token auth, session/order lifecycle, no real orders)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

import quantcore
from quantcore.data.synthetic import generate_quick_panel
from quantcore.paper import PaperMarketData
from quantcore.paper.rules import round_to_tick
from quantcore.server import create_app

TOKEN = "paper-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = "http://127.0.0.1:8000"

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")


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


@pytest.fixture(scope="module")
def plan(synthetic_snapshot: Any) -> dict[str, Any]:
    market = PaperMarketData(synthetic_snapshot.to_panel_data())
    fallback: dict[str, Any] | None = None
    for fill_day in range(2, min(market.n_time - 1, 90)):
        sec = _tradable_sec(market, fill_day)
        if sec is None:
            continue
        open_px = market.value("open", fill_day, sec)
        low = market.value("low", fill_day, sec)
        candidate = {
            "snapshot": synthetic_snapshot.snapshot_id,
            "start": market.dates[fill_day - 1],
            "end": market.dates[min(fill_day + 8, market.n_time - 1)],
            "code": market.code(sec),
            "limit_price": None,
        }
        if fallback is None:
            fallback = dict(candidate)
        if open_px - low >= 0.02:
            limit = round_to_tick(open_px - 0.02)
            if low <= limit < open_px:
                candidate["limit_price"] = limit
                return candidate
    assert fallback is not None, "no synthetic tradable security found"
    return fallback


@pytest.fixture()
def paper_app(tmp_path: Path, synthetic_snapshot: Any, snapshot_root: Path) -> Any:
    return create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=snapshot_root,
        experiments_root=tmp_path / "experiments",
        ui_dir=None,
        start_worker=False,
    )


@pytest.fixture()
def client(paper_app: Any) -> Any:
    with TestClient(paper_app, base_url=BASE) as test_client:
        yield test_client


def _create(client: TestClient, plan: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload = {
        "snapshot": plan["snapshot"],
        "initial_cash": 1_000_000.0,
        "start": plan["start"],
        "end": plan["end"],
        "name": "API 模拟",
    }
    payload.update(overrides)
    response = client.post("/api/paper/sessions", json=payload, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


def test_paper_requires_bearer_token(client: TestClient) -> None:
    assert client.get("/api/paper/sessions").status_code == 401
    assert client.post("/api/paper/sessions", json={}).status_code == 401
    assert (
        client.get("/api/paper/sessions", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
    assert client.get("/api/paper/sessions", headers=AUTH).status_code == 200


def test_create_list_detail_and_404(client: TestClient, plan: dict[str, Any]) -> None:
    view = _create(client, plan)
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
    assert view["id"].startswith("paper_")
    assert view["snapshot"] == plan["snapshot"]
    assert view["cash"] == 1_000_000.0 and view["equity"] == 1_000_000.0

    listed = client.get("/api/paper/sessions", headers=AUTH).json()
    assert any(item["id"] == view["id"] for item in listed)

    detail = client.get(f"/api/paper/sessions/{view['id']}", headers=AUTH)
    assert detail.status_code == 200
    payload = detail.json()
    assert set(payload) >= {"session", "account", "positions", "orders", "trades", "equity_curve"}
    assert payload["positions"] == [] and payload["trades"] == []
    assert len(payload["equity_curve"]) == 1
    assert payload["account"]["pnl"] == 0.0

    assert client.get("/api/paper/sessions/paper_000000000000", headers=AUTH).status_code == 404
    assert client.get("/api/paper/sessions/not-an-id", headers=AUTH).status_code == 404


def test_order_step_t_plus_one_sell_reset_and_delete(
    client: TestClient, plan: dict[str, Any]
) -> None:
    view = _create(client, plan)
    sid = view["id"]
    code = plan["code"]

    order = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "buy", "qty": 100},
        headers=AUTH,
    )
    assert order.status_code == 200, order.text
    order_payload = order.json()["order"]
    assert order_payload["status"] == "pending" and order_payload["side"] == "buy"

    stepped = client.post(f"/api/paper/sessions/{sid}/step", json={}, headers=AUTH)
    assert stepped.status_code == 200, stepped.text
    state = stepped.json()
    assert state["fills"] and state["fills"][0]["code"] == code
    assert state["positions"] and state["positions"][0]["qty"] == 100
    assert state["positions"][0]["available"] == 0
    assert state["orders"][0]["status"] == "filled"

    t1 = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "sell", "qty": 100},
        headers=AUTH,
    )
    assert t1.status_code == 400
    assert "T+1" in t1.json()["detail"]

    assert client.post(f"/api/paper/sessions/{sid}/step", headers=AUTH).status_code == 200
    sell = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "sell", "qty": 100},
        headers=AUTH,
    )
    assert sell.status_code == 200, sell.text
    assert client.post(f"/api/paper/sessions/{sid}/step", json={}, headers=AUTH).status_code == 200
    detail = client.get(f"/api/paper/sessions/{sid}", headers=AUTH).json()
    assert detail["positions"] == []
    assert [trade["side"] for trade in detail["trades"]] == ["buy", "sell"]
    assert detail["account"]["equity"] > 0

    csv_response = client.get(f"/api/paper/sessions/{sid}/signals.csv", headers=AUTH)
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "date,code,name,side" in csv_response.text
    assert code in csv_response.text

    reset = client.post(f"/api/paper/sessions/{sid}/reset", headers=AUTH)
    assert reset.status_code == 200
    payload = reset.json()
    assert payload["positions"] == [] and payload["trades"] == []
    assert payload["session"]["current_date"] == plan["start"]
    assert payload["account"]["cash"] == 1_000_000.0

    deleted = client.delete(f"/api/paper/sessions/{sid}", headers=AUTH)
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
    assert client.get(f"/api/paper/sessions/{sid}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/paper/sessions/{sid}", headers=AUTH).status_code == 404


def test_limit_order_and_cancel(client: TestClient, plan: dict[str, Any]) -> None:
    limit_price = plan["limit_price"]
    if limit_price is None:
        pytest.skip("synthetic plan has no suitable limit-price day")
    view = _create(client, plan)
    sid = view["id"]
    code = plan["code"]
    limit = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={
            "code": code,
            "side": "buy",
            "qty": 100,
            "order_type": "limit",
            "limit_price": limit_price,
        },
        headers=AUTH,
    )
    assert limit.status_code == 200, limit.text
    stepped = client.post(f"/api/paper/sessions/{sid}/step", json={}, headers=AUTH).json()
    assert stepped["fills"] and stepped["fills"][0]["price"] == pytest.approx(limit_price, abs=1e-9)

    far = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "buy", "qty": 100, "order_type": "limit", "limit_price": 0.01},
        headers=AUTH,
    ).json()["order"]
    assert far["status"] == "pending"
    client.post(f"/api/paper/sessions/{sid}/step", json={}, headers=AUTH)
    cancelled = client.post(f"/api/paper/sessions/{sid}/orders/{far['id']}/cancel", headers=AUTH)
    assert cancelled.status_code == 200
    assert cancelled.json()["order"]["status"] == "cancelled"
    again = client.post(f"/api/paper/sessions/{sid}/orders/{far['id']}/cancel", headers=AUTH)
    assert again.status_code == 409


def test_step_to_date_and_finished(client: TestClient, plan: dict[str, Any]) -> None:
    view = _create(client, plan)
    sid = view["id"]
    past = client.post(
        f"/api/paper/sessions/{sid}/step",
        json={"to_date": plan["start"]},
        headers=AUTH,
    )
    assert past.status_code == 400

    finished = client.post(f"/api/paper/sessions/{sid}/step", json={"days": 50}, headers=AUTH)
    assert finished.status_code == 200, finished.text
    assert finished.json()["session"]["status"] == "finished"
    assert finished.json()["session"]["current_date"] == plan["end"]
    assert client.post(f"/api/paper/sessions/{sid}/step", json={}, headers=AUTH).status_code == 400
    assert (
        client.post(
            f"/api/paper/sessions/{sid}/orders",
            json={"code": plan["code"], "side": "buy", "qty": 100},
            headers=AUTH,
        ).status_code
        == 400
    )


def test_validation_errors(client: TestClient, plan: dict[str, Any]) -> None:
    view = _create(client, plan)
    sid = view["id"]
    code = plan["code"]

    bad_lot = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "buy", "qty": 50},
        headers=AUTH,
    )
    assert bad_lot.status_code == 400

    no_position = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "sell", "qty": 100},
        headers=AUTH,
    )
    assert no_position.status_code == 400

    missing_limit = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "buy", "qty": 100, "order_type": "limit"},
        headers=AUTH,
    )
    assert missing_limit.status_code == 422

    market_with_limit = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "buy", "qty": 100, "limit_price": 10.0},
        headers=AUTH,
    )
    assert market_with_limit.status_code == 422

    bad_side = client.post(
        f"/api/paper/sessions/{sid}/orders",
        json={"code": code, "side": "hold", "qty": 100},
        headers=AUTH,
    )
    assert bad_side.status_code == 422

    assert (
        client.post(
            "/api/paper/sessions/paper_000000000000/orders",
            json={"code": code, "side": "buy", "qty": 100},
            headers=AUTH,
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/paper/sessions/{sid}/orders/ord_999999/cancel", headers=AUTH).status_code
        == 404
    )
    assert (
        client.post(f"/api/paper/sessions/{sid}/step", json={"days": 0}, headers=AUTH).status_code
        == 422
    )


def test_create_validation(client: TestClient, plan: dict[str, Any]) -> None:
    bad_cash = client.post(
        "/api/paper/sessions",
        json={"snapshot": plan["snapshot"], "initial_cash": 0},
        headers=AUTH,
    )
    assert bad_cash.status_code == 422
    inverted = client.post(
        "/api/paper/sessions",
        json={
            "snapshot": plan["snapshot"],
            "start": plan["end"],
            "end": plan["start"],
        },
        headers=AUTH,
    )
    assert inverted.status_code == 400


def test_reopen_across_server_instances(
    tmp_path: Path, synthetic_snapshot: Any, snapshot_root: Path
) -> None:
    kwargs = {
        "token": TOKEN,
        "port": 8000,
        "data_root": tmp_path / "data",
        "snapshots_root": snapshot_root,
        "experiments_root": tmp_path / "experiments",
        "ui_dir": None,
        "start_worker": False,
    }
    app1 = create_app(state_path=tmp_path / "state.sqlite", **kwargs)
    with TestClient(app1, base_url=BASE) as client1:
        payload = client1.post(
            "/api/paper/sessions",
            json={"snapshot": synthetic_snapshot.snapshot_id, "name": "reopen"},
            headers=AUTH,
        )
        assert payload.status_code == 201
        sid = payload.json()["id"]
        client1.post(f"/api/paper/sessions/{sid}/step", json={"days": 2}, headers=AUTH)
        before = client1.get(f"/api/paper/sessions/{sid}", headers=AUTH).json()

    app2 = create_app(state_path=tmp_path / "state.sqlite", **kwargs)
    with TestClient(app2, base_url=BASE) as client2:
        after = client2.get(f"/api/paper/sessions/{sid}", headers=AUTH)
        assert after.status_code == 200
        assert after.json()["session"]["current_date"] == before["session"]["current_date"]
        stepped = client2.post(f"/api/paper/sessions/{sid}/step", json={"days": 1}, headers=AUTH)
        assert stepped.status_code == 200
        assert client2.delete(f"/api/paper/sessions/{sid}", headers=AUTH).status_code == 200


def test_create_without_snapshot_returns_404(tmp_path: Path) -> None:
    panel = generate_quick_panel(n_sec=5)
    snapshot_root = tmp_path / "no_snapshots"
    assert panel.n_sec == 5
    app = create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=snapshot_root,
        experiments_root=tmp_path / "experiments",
        ui_dir=None,
        start_worker=False,
    )
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/api/paper/sessions", json={}, headers=AUTH)
        assert response.status_code == 404
        assert "snapshot" in response.json()["detail"].lower()
