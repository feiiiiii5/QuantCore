"""M9 local strategy plugin tests: discovery, static audit, validation and job backtest."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import quantcore
from quantcore.server import create_app

TOKEN = "plugin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = "http://127.0.0.1:8000"

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")

VALID_PLUGIN = '''
"""Demo local plugin used by tests."""
import numpy as np
from quantcore.strategy.base import Strategy

PLUGIN_INFO = {"interface": "strategy", "description": "demo plugin", "version": "1.2"}

class DemoPlugin(Strategy):
    name = "demo_plugin"
    version = "1.2"
    description = "demo plugin"

    def generate_weights(self, panel):
        n_time, n_sec = panel.n_time, panel.n_sec
        weights = np.full((n_time, n_sec), np.nan)
        for day in range(n_time):
            if day % 20 == 0:
                weights[day] = 0.0
                weights[day, : min(5, n_sec)] = 1.0 / min(5, n_sec)
        return weights
'''

DANGER_PLUGIN = """
import os

def run():
    return __import__("os"), os.system("echo nope")
"""
NO_INTERFACE = "VALUE = 1\n"
BROKEN = "def broken(:\n    pass\n"


def _plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "data" / "strategies"
    root.mkdir(parents=True, exist_ok=True)
    (root / "demo.py").write_text(VALID_PLUGIN, encoding="utf-8")
    (root / "danger.py").write_text(DANGER_PLUGIN, encoding="utf-8")
    (root / "noplugin.py").write_text(NO_INTERFACE, encoding="utf-8")
    (root / "broken.py").write_text(BROKEN, encoding="utf-8")
    return root


@pytest.fixture()
def plugin_app(tmp_path: Path, snapshot_root: Path, synthetic_snapshot: Any) -> Any:
    _plugin_root(tmp_path)
    return create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=snapshot_root,
        experiments_root=tmp_path / "experiments",
        ui_dir=None,
        start_worker=True,
    )


@pytest.fixture()
def client(plugin_app: Any) -> Any:
    with TestClient(plugin_app, base_url=BASE) as test_client:
        yield test_client


def _wait_job(client: TestClient, job_id: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job}")


def test_plugin_list_contract(client: TestClient) -> None:
    response = client.get("/api/strategies/plugins", headers=AUTH)
    assert response.status_code == 200, response.text
    rows = {row["name"]: row for row in response.json()}
    assert {"demo", "danger", "noplugin", "broken"} <= set(rows)
    for row in rows.values():
        for key in (
            "name",
            "path",
            "bytes",
            "updated_at",
            "valid",
            "issues",
            "interface",
            "description",
            "version",
        ):
            assert key in row, key
        assert isinstance(row["issues"], list)

    demo = rows["demo"]
    assert demo["valid"] is True
    assert demo["interface"] == "strategy"
    assert demo["description"] == "demo plugin"
    assert demo["version"] == "1.2"
    assert demo["bytes"] > 0 and demo["path"].endswith("demo.py")
    assert demo["issues"] == []

    danger = rows["danger"]
    assert danger["valid"] is False
    assert any(issue["severity"] == "error" for issue in danger["issues"])
    assert any("import not allowed" in issue["message"] for issue in danger["issues"])

    noplugin = rows["noplugin"]
    assert noplugin["valid"] is False
    assert noplugin["interface"] == "unknown"
    assert any("no strategy interface" in issue["message"] for issue in noplugin["issues"])

    broken = rows["broken"]
    assert broken["valid"] is False
    assert any("syntax" in issue["message"].lower() for issue in broken["issues"])

    assert client.get("/api/strategies/plugins").status_code == 401


def test_plugin_validate_contract_and_path_safety(client: TestClient) -> None:
    response = client.post("/api/strategies/plugins/demo/validate", headers=AUTH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "demo"
    assert payload["valid"] is True
    assert payload["issues"] == []
    assert payload["interface"] == "strategy"
    policy = payload["policy"]
    assert policy["static_audit"] is True
    assert policy["network"] is False
    assert policy["real_orders"] is False
    assert policy["security_boundary"] is False

    danger = client.post("/api/strategies/plugins/danger/validate", headers=AUTH).json()
    assert danger["valid"] is False
    assert danger["issues"]

    assert client.post("/api/strategies/plugins/nope/validate", headers=AUTH).status_code == 404
    assert client.post("/api/strategies/plugins/foo.txt/validate", headers=AUTH).status_code == 404
    assert client.post("/api/strategies/plugins/foo/bar/validate", headers=AUTH).status_code == 404
    assert (
        client.post("/api/strategies/plugins/..%2Fevil/validate", headers=AUTH).status_code == 404
    )
    assert (
        client.post(
            "/api/strategies/plugins/demo/validate", headers={"Authorization": "Bearer bad"}
        ).status_code
        == 401
    )


def test_plugin_backtest_submits_job_and_persists_experiment(
    client: TestClient, synthetic_snapshot: Any
) -> None:
    response = client.post(
        "/api/strategies/plugins/demo/backtest",
        json={
            "params": {"top_n": 5},
            "snapshot": synthetic_snapshot.snapshot_id,
            "start": "2022-06-01",
            "end": "2023-06-30",
            "initial_cash": 500_000.0,
        },
        headers=AUTH,
    )
    assert response.status_code == 202, response.text
    submitted = response.json()
    assert submitted["plugin"] == "demo"
    job = _wait_job(client, submitted["job_id"])
    assert job["status"] == "done", job.get("error")
    result = job["result"]
    assert result["plugin"] == "demo"
    run_id = result["run_id"]
    assert run_id

    experiment = client.get(f"/api/experiments/{run_id}", headers=AUTH)
    assert experiment.status_code == 200
    metadata = experiment.json()["metadata"]
    assert metadata["plugin"] == "demo"
    assert metadata["strategy"]["module"].endswith("demo.py")
    assert metadata["strategy"].get("template") is None
    assert metadata["params"] == {"top_n": 5}
    assert metadata["strategy_name"] == "demo"

    payload = client.get(f"/api/experiments/{run_id}/result", headers=AUTH).json()
    assert payload["engine_backend"] == "cpp"
    assert len(payload["equity"]) == len(payload["dates"]) > 0
    assert payload["trades"], "plugin strategy should generate trades"

    failure = client.post(
        "/api/strategies/plugins/danger/backtest",
        json={"snapshot": synthetic_snapshot.snapshot_id},
        headers=AUTH,
    )
    assert failure.status_code == 400
    no_interface = client.post(
        "/api/strategies/plugins/noplugin/backtest",
        json={"snapshot": synthetic_snapshot.snapshot_id},
        headers=AUTH,
    )
    assert no_interface.status_code == 400
    assert (
        client.post("/api/strategies/plugins/nope/backtest", json={}, headers=AUTH).status_code
        == 404
    )
    assert (
        client.post("/api/strategies/plugins/..%2Fevil/backtest", json={}, headers=AUTH).status_code
        == 404
    )
    assert (
        client.post(
            "/api/strategies/plugins/demo/backtest",
            json={},
            headers={"Authorization": "Bearer bad"},
        ).status_code
        == 401
    )


def test_plugin_backtest_without_snapshot_returns_404(tmp_path: Path) -> None:
    _plugin_root(tmp_path)
    app = create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=tmp_path / "empty-snapshots",
        experiments_root=tmp_path / "experiments",
        ui_dir=None,
        start_worker=False,
    )
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/api/strategies/plugins/demo/backtest", json={}, headers=AUTH)
        assert response.status_code == 404
        assert "snapshot" in json.dumps(response.json()).lower()
