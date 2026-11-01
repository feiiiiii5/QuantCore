"""M9-002 continuous simulated clock for paper sessions (no live market feed)."""

from __future__ import annotations

import time


def test_auto_run_advances_and_stops(api_client) -> None:
    created = api_client.post(
        "/api/paper/sessions", json={"initial_cash": 1_000_000, "name": "auto"}
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    before = api_client.get(f"/api/paper/sessions/{session_id}").json()["session"]["current_date"]
    started = api_client.post(
        f"/api/paper/sessions/{session_id}/auto",
        json={"interval_ms": 50, "days_per_tick": 1},
    )
    assert started.status_code == 200, started.text
    assert started.json()["running"] is True
    current = before
    for _ in range(100):
        time.sleep(0.05)
        payload = api_client.get(f"/api/paper/sessions/{session_id}").json()
        current = int(payload["session"]["current_date"])
        if current > before:
            break
    assert current > before
    stopped = api_client.post(f"/api/paper/sessions/{session_id}/auto/stop")
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
    status = api_client.get(f"/api/paper/sessions/{session_id}/auto").json()
    assert status["running"] is False


def test_auto_run_unknown_session(api_client) -> None:
    response = api_client.post("/api/paper/sessions/paper_000000000000/auto")
    assert response.status_code == 404
