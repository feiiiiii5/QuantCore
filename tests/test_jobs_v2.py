"""Job queue v2 tests: WebSocket progress, cancellation, crash recovery, full results."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from quantcore.jobs import JobCancelledError
from quantcore.jobs.queue import JobContext

from .conftest import local_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = "http://127.0.0.1:8000"
WS_HEADERS = {"host": "127.0.0.1:8000"}


def _client(app: object) -> TestClient:
    client = TestClient(app, base_url=BASE)
    client.headers.update(AUTH)
    return client


def _wait_status(
    client: TestClient, job_id: str, wanted: set[str], timeout: float = 15.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in wanted:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} not in {wanted}: {job}")


def test_websocket_streams_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def staged_runner(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
        for value in (0.05, 0.2, 0.8):
            ctx.update_progress(value)
            time.sleep(0.08)
        return {"engine_backend": "cpp", "metrics": {}, "summary": "staged"}

    app = local_app(tmp_path, runner=staged_runner)
    with _client(app) as client:
        response = client.post("/api/backtest", json={"template": "buy_and_hold"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        messages: list[dict[str, Any]] = []
        with client.websocket_connect(
            f"/ws/jobs/{job_id}?token={TOKEN}", headers=WS_HEADERS
        ) as socket:
            for _ in range(300):
                message = socket.receive_json()
                messages.append(message)
                if message["type"] in {"done", "error"}:
                    break
        assert messages[-1]["type"] == "done"
        progress_values = [
            message["job"]["progress"] for message in messages if message["type"] == "job"
        ]
        assert progress_values == sorted(progress_values)
        assert any(0.0 < value < 1.0 for value in progress_values)
        assert progress_values[-1] == 1.0
        done = messages[-1]["job"]
        assert done["id"] == job_id and done["status"] == "done"
        assert done["result"]["summary"] == "staged"


def test_websocket_rejects_bad_token_and_reports_missing_job(tmp_path: Path) -> None:
    app = local_app(tmp_path)
    with _client(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client.websocket_connect("/ws/jobs/job_missing?token=wrong", headers=WS_HEADERS),
        ):
            pass
        assert excinfo.value.code == 1008
        with client.websocket_connect(
            f"/ws/jobs/job_missing?token={TOKEN}", headers=WS_HEADERS
        ) as socket:
            message = socket.receive_json()
            assert message["type"] == "error"
            assert "not found" in message["error"]


def test_cancel_pending_job_immediately(tmp_path: Path) -> None:
    release = threading.Event()

    def blocking_runner(payload: dict[str, Any]) -> dict[str, Any]:
        release.wait(timeout=10.0)
        return {"released": True}

    app = local_app(tmp_path, runner=blocking_runner)
    try:
        with _client(app) as client:
            first = client.post("/api/backtest", json={"template": "buy_and_hold"}).json()
            _wait_status(client, first["job_id"], {"running"})
            second = client.post("/api/backtest", json={"template": "buy_and_hold"}).json()
            _wait_status(client, second["job_id"], {"pending"})
            assert client.get(f"/api/jobs/{second['job_id']}/result").status_code == 202
            cancelled = client.post(f"/api/jobs/{second['job_id']}/cancel")
            assert cancelled.status_code == 200
            payload = cancelled.json()
            assert payload["cancelled"] is True
            assert payload["status"] == "cancelled"
            assert client.get(f"/api/jobs/{second['job_id']}/result").status_code == 409
            release.set()
            done = _wait_status(client, first["job_id"], {"done"})
            assert done["result"]["released"] is True
    finally:
        release.set()


def test_cancel_running_job_cooperatively(tmp_path: Path) -> None:
    observed = threading.Event()

    def cooperative_runner(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
        for _ in range(500):
            if ctx.cancel_requested():
                observed.set()
                raise JobCancelledError("cancelled by test")
            ctx.update_progress(0.5)
            time.sleep(0.01)
        return {"finished": True}

    app = local_app(tmp_path, runner=cooperative_runner)
    with _client(app) as client:
        job_id = client.post("/api/backtest", json={"template": "buy_and_hold"}).json()["job_id"]
        _wait_status(client, job_id, {"running"})
        response = client.post(f"/api/jobs/{job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["cancelled"] is True
        job = _wait_status(client, job_id, {"cancelled"}, timeout=10)
        assert job["error"] and "cancel" in job["error"].lower()
        assert observed.is_set()
        assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
        listed = client.get("/api/jobs", params={"status": "cancelled"}).json()
        assert any(item["id"] == job_id for item in listed)
        assert client.get("/api/jobs", params={"status": "bogus"}).status_code == 422
        # cancelling an already terminal job is a no-op that reports its status
        again = client.post(f"/api/jobs/{job_id}/cancel").json()
        assert again["status"] == "cancelled"


def test_crash_recovery_marks_orphaned_jobs_failed(tmp_path: Path) -> None:
    app = local_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        client.headers.update(AUTH)
        job_id = client.post("/api/backtest", json={"template": "buy_and_hold"}).json()["job_id"]
        orphan = app.state.jobs.state.claim_job()
        assert orphan is not None and orphan["id"] == job_id
        assert app.state.jobs.state.get_job(job_id)["status"] == "running"

    # A restarted server recovers jobs interrupted by the previous process.
    restarted = local_app(tmp_path)
    with TestClient(restarted, base_url=BASE) as client:
        client.headers.update(AUTH)
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "failed"
        assert "interrupted" in job["error"]
        assert client.get(f"/api/jobs/{job_id}/result").status_code == 409


def test_real_backtest_job_result_and_experiment(tmp_path: Path) -> None:
    app = local_app(tmp_path)
    with _client(app) as client:
        response = client.post(
            "/api/backtest",
            json={
                "template": "buy_and_hold",
                "synthetic": {
                    "n_sec": 20,
                    "start": "2022-01-04",
                    "end": "2023-12-29",
                    "seed": 3,
                },
            },
        )
        assert response.status_code == 202
        job = _wait_status(client, response.json()["job_id"], {"done", "failed"}, timeout=60)
        assert job["status"] == "done", job
        payload = client.get(f"/api/jobs/{job['id']}/result").json()
        assert payload["status"] == "done"
        result = payload["result"]
        for key in ("run_id", "engine_backend", "metrics", "trade_count", "synthetic"):
            assert key in result, key
        assert result["engine_backend"] == "cpp"
        assert result["synthetic"] is True
        assert len(result["dates"]) == len(result["equity"]) > 0
        assert result["final_equity"] > 0
        experiment = client.get(f"/api/experiments/{result['run_id']}").json()
        assert experiment["run_id"] == result["run_id"]
        assert experiment["result"]["equity"]
        replay = client.post(f"/api/experiments/{result['run_id']}/replay").json()
        assert replay["matched"] is True
