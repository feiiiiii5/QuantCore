"""FastAPI research server tests: security, health, job queue and one API backtest."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import quantcore
from quantcore.server import create_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1:8000"


def _app(tmp_path: Path, runner: Any = None, start_worker: bool = False):
    return create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        runner=runner,
        start_worker=start_worker,
    )


def test_health_without_auth_and_no_cors(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["engine_backend"] == "cpp"
        assert payload["cors"] is False
        assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


def test_api_requires_bearer_token(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        assert client.get("/api/jobs").status_code == 401
        assert client.get("/api/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/jobs", headers={"Authorization": "Basic abc"}).status_code == 401
        assert client.get("/api/jobs", headers=AUTH).status_code == 200


def test_host_header_is_validated(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/health", headers={"host": "evil.example.com"})
        assert response.status_code == 400
        response = client.get("/api/jobs", headers={**AUTH, "host": "evil.example.com"})
        assert response.status_code == 400


def test_origin_header_is_validated(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        denied = client.get("/api/jobs", headers={**AUTH, "origin": "https://evil.example.com"})
        assert denied.status_code == 403
        allowed = client.get("/api/jobs", headers={**AUTH, "origin": BASE_URL})
        assert allowed.status_code == 200
        assert "access-control-allow-origin" not in {key.lower() for key in allowed.headers}


def test_request_validation(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        assert (
            client.post(
                "/api/backtest", json={"template": "x", "strategy": {"name": "y"}}, headers=AUTH
            ).status_code
            == 422
        )
        assert client.post("/api/backtest", json={}, headers=AUTH).status_code == 422
        assert client.post(
            "/api/backtest", json={"template": "nope"}, headers=AUTH
        ).status_code in {200, 202}


def test_job_lifecycle_with_fake_runner(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def runner(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"engine_backend": "cpp", "metrics": {"total_return": 0.0}, "synthetic": True}

    app = _app(tmp_path, runner=runner, start_worker=True)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/api/backtest", json={"template": "buy_and_hold", "params": {}}, headers=AUTH
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        job: dict[str, Any] = {}
        for _ in range(200):
            job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
            if job["status"] in {"done", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "done", job
        result = client.get(f"/api/jobs/{job_id}/result", headers=AUTH)
        assert result.status_code == 200
        assert result.json()["result"]["engine_backend"] == "cpp"
        assert calls and calls[0]["template"] == "buy_and_hold"
        assert client.get("/api/jobs/does-not-exist", headers=AUTH).status_code == 404
        assert client.get("/api/jobs/does-not-exist/result", headers=AUTH).status_code == 404


def test_job_failure_is_reported(tmp_path: Path) -> None:
    def failing_runner(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    app = _app(tmp_path, runner=failing_runner, start_worker=True)
    with TestClient(app, base_url=BASE_URL) as client:
        job_id = client.post(
            "/api/backtest", json={"template": "buy_and_hold"}, headers=AUTH
        ).json()["job_id"]
        job: dict[str, Any] = {}
        for _ in range(200):
            job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
            if job["status"] in {"done", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "failed"
        assert "boom" in (job.get("error") or "")
        assert client.get(f"/api/jobs/{job_id}/result", headers=AUTH).status_code == 409


@pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")
def test_default_runner_backtest(tmp_path: Path) -> None:
    app = _app(tmp_path, start_worker=True)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/api/backtest",
            json={"template": "momentum", "params": {"top_n": 5, "lookback": 60}},
            headers=AUTH,
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        job: dict[str, Any] = {}
        for _ in range(600):
            job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
            if job["status"] in {"done", "failed"}:
                break
            time.sleep(0.05)
        assert job["status"] == "done", job
        result = client.get(f"/api/jobs/{job_id}/result", headers=AUTH).json()["result"]
        assert result["engine_backend"] == "cpp"
        assert result["synthetic"] is True
        assert "total_return" in result["metrics"]
