"""M9-004 tests: read-only multi-session paper portfolio aggregation API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

import quantcore
from quantcore.server import create_app

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")

TOKEN = "portfolio-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = "http://127.0.0.1:8000"


def _tradable_code(panel: Any) -> str:
    """Pick a security that can fill a buy order on the first step day."""
    for sec in range(panel.n_sec):
        open_px = panel.matrix("open")[1, sec]
        high = panel.matrix("high")[1, sec]
        low = panel.matrix("low")[1, sec]
        close = panel.matrix("close")[1, sec]
        volume = panel.matrix("volume")[1, sec]
        suspended = panel.matrix("suspended")[1, sec]
        limit_up = panel.matrix("limit_up")[1, sec]
        if not all(np.isfinite(v) and v > 0 for v in (open_px, high, low, close, volume)):
            continue
        if high <= low or (np.isfinite(suspended) and suspended > 0.5):
            continue
        if np.isfinite(limit_up) and limit_up > 0 and open_px >= limit_up:
            continue
        return str(panel.securities.iloc[sec]["code"])
    raise AssertionError("no tradable synthetic security found")


@pytest.fixture()
def portfolio_app(tmp_path: Path, snapshot_root: Path, synthetic_snapshot: Any) -> Any:
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
def client(portfolio_app: Any) -> Any:
    with TestClient(portfolio_app, base_url=BASE) as test_client:
        test_client.headers.update(AUTH)
        yield test_client


def _create_session(
    client: TestClient,
    snapshot_id: str,
    *,
    name: str,
    initial_cash: float = 1_000_000.0,
    start: str | None = None,
    end: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "snapshot": snapshot_id,
        "initial_cash": initial_cash,
        "name": name,
    }
    if start is not None:
        payload["start"] = start
    if end is not None:
        payload["end"] = end
    response = client.post("/api/paper/sessions", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _step(client: TestClient, session_id: str, days: int = 1) -> dict[str, Any]:
    response = client.post(f"/api/paper/sessions/{session_id}/step", json={"days": days})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def prepared_sessions(client: TestClient, synthetic_snapshot: Any) -> dict[str, Any]:
    snapshot_id = synthetic_snapshot.snapshot_id
    code = _tradable_code(synthetic_snapshot.to_panel_data())
    first = _create_session(client, snapshot_id, name="组合-动量", initial_cash=1_000_000.0)
    second = _create_session(client, snapshot_id, name="组合-均衡", initial_cash=2_000_000.0)
    for session_id in (first, second):
        order = client.post(
            f"/api/paper/sessions/{session_id}/orders",
            json={"code": code, "side": "buy", "qty": 100},
        )
        assert order.status_code == 200, order.text
    _step(client, first, days=1)
    _step(client, first, days=2)
    _step(client, second, days=1)
    _step(client, second, days=1)
    return {
        "snapshot_id": snapshot_id,
        "first": first,
        "second": second,
        "code": code,
    }


def test_portfolio_aggregation_contract(
    client: TestClient, prepared_sessions: dict[str, Any]
) -> None:
    first, second = prepared_sessions["first"], prepared_sessions["second"]
    allocations = [
        {"session_id": first, "weight": 0.6},
        {"session_id": second, "weight": 0.4},
    ]
    response = client.post(
        "/api/paper/portfolio",
        json={"allocations": allocations, "initial_cash": 1_000_000.0},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in ("allocations", "dates", "equity", "metrics", "contributions", "note"):
        assert key in payload, key
    assert "normalized_equity" in payload

    assert [row["session_id"] for row in payload["allocations"]] == [first, second]
    assert [row["weight"] for row in payload["allocations"]] == [0.6, 0.4]
    for row in payload["allocations"]:
        assert row["snapshot"] == prepared_sessions["snapshot_id"]
        assert row["synthetic"] is True
        assert row["name"]

    dates = payload["dates"]
    assert dates and all(isinstance(value, int) for value in dates)
    assert dates == sorted(dates)
    assert len(payload["equity"]) == len(dates) == len(payload["normalized_equity"])
    assert payload["equity"][0] == pytest.approx(1_000_000.0, rel=1e-9)
    assert payload["normalized_equity"][0] == pytest.approx(1.0, abs=1e-9)

    metrics = payload["metrics"]
    for key in (
        "total_return",
        "annualized_return",
        "volatility",
        "sharpe",
        "max_drawdown",
    ):
        assert key in metrics, key
    assert metrics["max_drawdown"] >= 0.0

    contributions = payload["contributions"]
    assert len(contributions) == 2
    assert sum(row["contribution"] for row in contributions) == pytest.approx(
        metrics["total_return"], abs=1e-6
    )
    assert {row["session_id"] for row in contributions} == {first, second}
    for row in contributions:
        assert row["weight"] in {0.6, 0.4}
        assert isinstance(row["name"], str)
    assert "不写回" in payload["note"] or "交集" in payload["note"]

    # read-only: repeating the request produces identical output
    again = client.post(
        "/api/paper/portfolio",
        json={"allocations": allocations, "initial_cash": 1_000_000.0},
    )
    assert again.status_code == 200
    assert again.json() == payload


def test_portfolio_weight_validation(client: TestClient, prepared_sessions: dict[str, Any]) -> None:
    first, second = prepared_sessions["first"], prepared_sessions["second"]
    assert (
        client.post(
            "/api/paper/portfolio",
            json={
                "allocations": [
                    {"session_id": first, "weight": 0.6},
                    {"session_id": second, "weight": 0.5},
                ]
            },
        ).status_code
        == 400
    )
    duplicate = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": first, "weight": 0.5},
                {"session_id": first, "weight": 0.5},
            ]
        },
    )
    assert duplicate.status_code == 400
    assert "duplicate" in duplicate.json()["detail"].lower()

    # tolerance: within 1e-6 of 1.0 is accepted
    nearly = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": first, "weight": 0.6},
                {"session_id": second, "weight": 0.4000005},
            ]
        },
    )
    assert nearly.status_code == 200, nearly.text


def test_portfolio_request_validation(
    client: TestClient, prepared_sessions: dict[str, Any]
) -> None:
    first, second = prepared_sessions["first"], prepared_sessions["second"]
    single = client.post(
        "/api/paper/portfolio", json={"allocations": [{"session_id": first, "weight": 1.0}]}
    )
    assert single.status_code == 422
    empty = client.post("/api/paper/portfolio", json={"allocations": []})
    assert empty.status_code == 422
    bad_weight = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": first, "weight": 0.0},
                {"session_id": second, "weight": 1.0},
            ]
        },
    )
    assert bad_weight.status_code == 422
    too_many = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": f"paper_{index:012x}", "weight": 0.1} for index in range(11)
            ]
        },
    )
    assert too_many.status_code == 422
    assert (
        client.post(
            "/api/paper/portfolio",
            json={
                "allocations": [
                    {"session_id": first, "weight": 0.5},
                    {"session_id": second, "weight": 0.5},
                ]
            },
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )


def test_portfolio_unknown_and_disjoint_sessions(
    client: TestClient, prepared_sessions: dict[str, Any], synthetic_snapshot: Any
) -> None:
    first = prepared_sessions["first"]
    assert (
        client.post(
            "/api/paper/portfolio",
            json={
                "allocations": [
                    {"session_id": first, "weight": 0.5},
                    {"session_id": "paper_000000000000", "weight": 0.5},
                ]
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/paper/portfolio",
            json={
                "allocations": [
                    {"session_id": first, "weight": 0.5},
                    {"session_id": "not-a-session", "weight": 0.5},
                ]
            },
        ).status_code
        == 404
    )

    # sessions with a single common date (no overlapping stepped history) → 400
    fresh_a = _create_session(client, synthetic_snapshot.snapshot_id, name="fresh-a")
    fresh_b = _create_session(client, synthetic_snapshot.snapshot_id, name="fresh-b")
    too_few = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": fresh_a, "weight": 0.5},
                {"session_id": fresh_b, "weight": 0.5},
            ]
        },
    )
    assert too_few.status_code == 400
    assert "common" in too_few.json()["detail"].lower()

    # a session in a disjoint date window has no common dates with the first session
    late = _create_session(
        client,
        synthetic_snapshot.snapshot_id,
        name="late",
        start="2024-01-02",
        end="2024-06-28",
    )
    _step(client, late, days=1)
    disjoint = client.post(
        "/api/paper/portfolio",
        json={
            "allocations": [
                {"session_id": first, "weight": 0.5},
                {"session_id": late, "weight": 0.5},
            ]
        },
    )
    assert disjoint.status_code == 400
