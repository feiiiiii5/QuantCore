"""Contract tests for the M5/M6 API surface (market, screener, experiments, jobs)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from quantcore.server import create_app

TOKEN = "v2-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = "http://127.0.0.1:8000"


def _client(tmp_path: Path, *, start_worker: bool = False, runner: Any = None):
    app = create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=tmp_path / "data" / "snapshots",
        experiments_root=tmp_path / "experiments",
        ui_dir=tmp_path / "ui",
        start_worker=start_worker,
        runner=runner,
    )
    return TestClient(app, base_url=BASE)


def _wait(client: TestClient, job_id: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job}")


def test_meta_and_market_contract(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        meta = client.get("/api/meta", headers=AUTH)
        assert meta.status_code == 200
        assert meta.json()["engine_backend"] == "cpp"
        overview = client.get("/api/market/overview", headers=AUTH)
        assert overview.status_code == 200
        payload = overview.json()
        assert payload["indices"] and payload["snapshot"]["synthetic"] is True
        assert set(payload["breadth"]) >= {
            "up",
            "down",
            "flat",
            "limit_up",
            "limit_down",
            "suspended",
        }
        securities = client.get("/api/market/securities?limit=3", headers=AUTH).json()
        assert len(securities) == 3
        bars = client.get(f"/api/market/bars?code={securities[0]['code']}", headers=AUTH)
        assert bars.status_code == 200
        assert len(bars.json()["dates"]) == len(bars.json()["close"])


def test_screener_and_templates(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        presets = client.get("/api/screener/presets", headers=AUTH).json()
        assert presets
        result = client.post(
            "/api/screener/run",
            json={"expression": presets[0]["expression"], "limit": 20},
            headers=AUTH,
        )
        assert result.status_code == 200
        payload = result.json()
        assert payload["matched_count"] == len(payload["rows"])
        assert payload["rows"][0]["score"] is not None
        templates = client.get("/api/strategies/templates", headers=AUTH).json()
        assert {item["id"] for item in templates} >= {"momentum", "dual_ma", "multi_factor"}
        validated = client.post(
            "/api/strategies/validate",
            json={"template": "momentum", "params": {"top_n": 5}},
            headers=AUTH,
        ).json()
        assert validated["valid"] is True
        bad = client.post(
            "/api/strategies/validate",
            json={"template": "momentum", "params": {"top_n": -1}},
            headers=AUTH,
        ).json()
        assert bad["valid"] is False


def test_factor_and_sweep(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        factor = client.post(
            "/api/research/factor",
            json={
                "expression": "ts_mean(close,5)/ts_mean(close,20)",
                "forward_days": 5,
                "quantiles": 3,
            },
            headers=AUTH,
        )
        assert factor.status_code == 200
        payload = factor.json()
        assert "ic_mean" in payload and payload["observations"] > 0
        sweep = client.post(
            "/api/research/sweep",
            json={"template": "momentum", "param_grid": {"top_n": [3]}, "workers": 1},
            headers=AUTH,
        )
        assert sweep.status_code == 200
        assert sweep.json()["points"][0]["error"] is None


@pytest.mark.skipif(not __import__("quantcore").engine_available(), reason="C++ engine unavailable")
def test_backtest_job_to_experiment_replay_report_export(tmp_path: Path) -> None:
    with _client(tmp_path, start_worker=True) as client:
        response = client.post(
            "/api/backtest",
            json={
                "template": "momentum",
                "params": {"top_n": 5, "lookback": 60},
                "synthetic": {"n_sec": 30, "start": "2022-01-04", "end": "2023-12-29"},
            },
            headers=AUTH,
        )
        assert response.status_code == 202
        job = _wait(client, response.json()["job_id"])
        assert job["status"] == "done", job
        run_id = job["result"]["run_id"]
        full = client.get(f"/api/jobs/{job['id']}/result", headers=AUTH).json()["result"]
        assert full["engine_backend"] == "cpp" and full["equity"]
        experiment = client.get(f"/api/experiments/{run_id}", headers=AUTH)
        assert experiment.status_code == 200
        result = client.get(f"/api/experiments/{run_id}/result", headers=AUTH).json()
        assert result["engine_backend"] == "cpp"
        assert result["cash"][0] == pytest.approx(1_000_000.0, abs=0.01)
        replay = client.post(f"/api/experiments/{run_id}/replay", headers=AUTH)
        assert replay.status_code == 200
        assert replay.json()["matched"] is True
        report = client.get(f"/api/experiments/{run_id}/report", headers=AUTH)
        assert report.status_code == 200 and "text/html" in report.headers["content-type"]
        export = client.get(f"/api/experiments/{run_id}/export", headers=AUTH)
        assert export.status_code == 200 and export.content[:2] == b"PK"
        listed = client.get("/api/experiments", headers=AUTH).json()
        assert any(item["run_id"] == run_id for item in listed)


def test_cancel_running_job(tmp_path: Path) -> None:
    def slow_runner(payload: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.8)
        return {"ok": True}

    with _client(tmp_path, start_worker=True, runner=slow_runner) as client:
        job_id = client.post(
            "/api/backtest", json={"template": "buy_and_hold"}, headers=AUTH
        ).json()["job_id"]
        time.sleep(0.1)
        cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH)
        assert cancelled.status_code == 200
        job = _wait(client, job_id, timeout=5)
        assert job["status"] in {"cancelled", "done"}


def test_websocket_reports_job(tmp_path: Path) -> None:
    with _client(tmp_path, start_worker=True) as client:
        job_id = client.post(
            "/api/backtest", json={"template": "buy_and_hold"}, headers=AUTH
        ).json()["job_id"]
        with client.websocket_connect(
            f"/ws/jobs/{job_id}?token={TOKEN}", headers={"host": "127.0.0.1:8000"}
        ) as ws:
            first = ws.receive_json()
            assert first["type"] in {"job", "done", "error"}
            terminal = None
            for _ in range(200):
                message = ws.receive_json()
                if message["type"] in {"done", "error"}:
                    terminal = message
                    break
            assert terminal is not None
            assert terminal["job"]["id"] == job_id


def test_token_url_bootstraps_local_storage(api_client: Any) -> None:
    response = api_client.get("/", params={"token": "abc123"})
    assert response.status_code == 200
    assert "qc_token_boot" in response.text
    assert "localStorage.setItem('qc_token'" in response.text


def test_snapshot_fields_are_display_ready(api_client: Any) -> None:
    snapshots = api_client.get("/api/data/snapshots").json()
    assert snapshots
    first = snapshots[0]
    assert first["start"] is None or isinstance(first["start"], str)
    assert first["end"] is None or isinstance(first["end"], str)
    if first["start"]:
        assert len(first["start"]) == 10 and first["start"][4] == "-"
    status = api_client.get("/api/data/status").json()
    assert status["snapshots"][0]["id"].startswith("snap_")


def test_data_update_snapshot_and_onboarding(tmp_path: Path) -> None:
    with _client(tmp_path, start_worker=True) as client:
        update = client.post(
            "/api/data/update",
            json={
                "provider": "synthetic",
                "start": "2022-01-04",
                "end": "2023-12-29",
                "n_sec": 12,
                "seed": 7,
            },
            headers=AUTH,
        )
        assert update.status_code == 202, update.text
        update_job = _wait(client, update.json()["job_id"])
        assert update_job["status"] == "done", update_job
        status = client.get("/api/data/status", headers=AUTH).json()
        assert status["warehouse"]["exists"] is True and status["warehouse"]["rows"] > 0
        snapshot = client.post("/api/data/snapshot", json={"require_qpanel": True}, headers=AUTH)
        assert snapshot.status_code == 202
        snap_job = _wait(client, snapshot.json()["job_id"])
        assert snap_job["status"] == "done", snap_job
        snapshot_id = snap_job["result"]["snapshot_id"]
        assert client.get("/api/data/snapshots", headers=AUTH).json()
        assert (
            client.get(f"/api/data/quality?snapshot={snapshot_id}", headers=AUTH).status_code == 200
        )


@pytest.mark.skipif(not __import__("quantcore").engine_available(), reason="C++ engine unavailable")
def test_onboarding_bootstrap_creates_snapshot_and_experiment(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/onboarding/bootstrap",
            json={"n_sec": 12, "start": "2022-01-04", "end": "2023-12-29", "seed": 11},
            headers=AUTH,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["run_id"] and payload["snapshot"]
        experiment = client.get(f"/api/experiments/{payload['run_id']}", headers=AUTH)
        assert experiment.status_code == 200
        assert experiment.json()["metrics"]
