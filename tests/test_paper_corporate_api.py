"""Paper constructor validation must precede persistence and map to API errors."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from quantcore.paper import PaperMarketData, PaperSessionEngine, PaperStore
from quantcore.server import create_app
from quantcore.snapshot import build_snapshot
from tests.test_corporate_backtest import action_panel

AUTH = {"Authorization": "Bearer corporate-api-test"}


def setup_app(tmp_path, *, rights=False):
    panel = action_panel(cash=0.5)
    if rights:
        panel.corporate_actions["rights_ratio"] = 0.1
    root = tmp_path / "snapshots"
    manifest = build_snapshot(panel, root)
    app = create_app(
        data_root=tmp_path / "data",
        snapshots_root=root,
        state_path=tmp_path / "state.sqlite",
        token="corporate-api-test",
        start_worker=False,
    )
    return app, panel, manifest


def test_unsupported_rights_reject_creation_without_persisting_a_broken_account(tmp_path):
    app, _, manifest = setup_app(tmp_path, rights=True)
    with TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as client:
        result = client.post(
            "/api/paper/sessions", json={"snapshot": manifest.snapshot_id}, headers=AUTH
        )
        assert result.status_code == 400, result.text
        assert "rights subscriptions" in result.json()["detail"]
        assert client.get("/api/paper/sessions", headers=AUTH).json() == []
        assert not list((tmp_path / "data/paper").glob("paper_*.json"))


@pytest.mark.parametrize(("invalid", "status"), [("rights", 400), ("tax", 400), ("date", 409)])
def test_invalid_legacy_account_load_and_mutation_return_domain_status(tmp_path, invalid, status):
    app, panel, manifest = setup_app(tmp_path, rights=invalid == "rights")
    # Model an account saved by an older API that did not construct its engine.
    session = PaperSessionEngine.create(
        PaperMarketData(panel), snapshot={"id": manifest.snapshot_id}, initial_cash=10_000
    )
    if invalid == "tax":
        session.config["costs"]["enable_dividend_tax"] = True
    if invalid == "date":
        session.current_date = 20260109
    store = PaperStore(tmp_path / "data/paper")
    store.save(session)
    before = store.path_for(session.id).read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as client:
        for suffix in ("", "/signals.csv"):
            result = client.get(f"/api/paper/sessions/{session.id}{suffix}", headers=AUTH)
            assert result.status_code == status, result.text
        result = client.post(f"/api/paper/sessions/{session.id}/step", json={}, headers=AUTH)
        assert result.status_code == status, result.text
    assert store.path_for(session.id).read_bytes() == before


def test_missing_snapshot_stops_automatic_run_with_a_domain_error(tmp_path):
    app, panel, _ = setup_app(tmp_path)
    session = PaperSessionEngine.create(
        PaperMarketData(panel), snapshot={"id": "snap_missing"}, initial_cash=10_000
    )
    PaperStore(tmp_path / "data/paper").save(session)
    base = f"/api/paper/sessions/{session.id}"
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get(base, headers=AUTH).status_code == 409
        assert client.post(f"{base}/auto", json={}, headers=AUTH).status_code == 200
        try:
            for _ in range(300):
                status = client.get(f"{base}/auto", headers=AUTH).json()
                if not status["running"]:
                    break
                time.sleep(0.01)
        finally:
            client.post(f"{base}/auto/stop", headers=AUTH)
        assert status["running"] is False
        assert "snapshot unavailable for paper session" in status["error"]
