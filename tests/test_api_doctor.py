"""GET /api/doctor: read-only local self-check report over the local API (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

BASE_URL = "http://127.0.0.1:8000"
CHECK_KEYS = {"id", "title", "status", "detail", "hint", "required"}


def _fake_report(include_optional: bool) -> Any:
    class FakeReport:
        def to_dict(self) -> dict[str, Any]:
            return {
                "status": "warn",
                "generated_at": "2026-01-02T03:04:05+00:00",
                "version": "0.1.0",
                "engine_backend": "cpp",
                "engine_available": True,
                "panel_available": True,
                "root": "/tmp/qc-root",
                "counts": {
                    "pass": 1,
                    "warn": 1,
                    "fail": 0,
                    "skip": 1 if include_optional else 0,
                },
                "checks": [
                    {
                        "id": "python",
                        "title": "Python",
                        "status": "pass",
                        "detail": "3.12",
                        "hint": "",
                        "required": True,
                    },
                    {
                        "id": "optional",
                        "title": "Optional",
                        "status": "skip",
                        "detail": "skipped",
                        "hint": "pass include_optional=true",
                        "required": False,
                    },
                ],
            }

    return FakeReport()


def test_doctor_requires_bearer_token(api_app: Any) -> None:
    with TestClient(api_app, base_url=BASE_URL) as client:
        assert client.get("/api/doctor").status_code == 401
        denied = client.get("/api/doctor", headers={"Authorization": "Bearer wrong"})
        assert denied.status_code == 401


def test_doctor_serialises_report(api_client: Any, monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_doctor(root: Any = None, **kwargs: Any) -> Any:
        calls.append({"root": root, **kwargs})
        return _fake_report(bool(kwargs.get("include_optional", True)))

    monkeypatch.setattr("quantcore.server.routes_doctor.run_doctor", fake_run_doctor)
    response = api_client.get("/api/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warn"
    assert payload["counts"] == {"pass": 1, "warn": 1, "fail": 0, "skip": 1}
    assert [check["id"] for check in payload["checks"]] == ["python", "optional"]
    assert set(payload["checks"][0]) == CHECK_KEYS
    assert payload["checks"][0]["required"] is True
    assert calls and calls[0]["include_optional"] is True
    assert calls[0]["root"] == Path.cwd()
    settings = api_client.app.state.settings
    assert calls[0]["data_root"] == settings.data_root
    assert calls[0]["snapshots_root"] == settings.snapshots_root

    response = api_client.get("/api/doctor?include_optional=false")
    assert response.status_code == 200
    assert response.json()["counts"]["skip"] == 0
    assert calls[-1]["include_optional"] is False


def test_doctor_real_report_shape(api_client: Any) -> None:
    response = api_client.get("/api/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "warn", "fail"}
    for key in ("generated_at", "version", "engine_backend", "root"):
        assert isinstance(payload[key], str)
    for key in ("engine_available", "panel_available"):
        assert isinstance(payload[key], bool)
    counts = payload["counts"]
    assert set(counts) == {"pass", "warn", "fail", "skip"}
    assert all(isinstance(count, int) for count in counts.values())
    checks = payload["checks"]
    assert checks
    for check in checks:
        assert set(check) == CHECK_KEYS
        assert check["status"] in {"pass", "warn", "fail", "skip"}
        assert isinstance(check["required"], bool)


def test_real_run_doctor_does_not_raise() -> None:
    from quantcore.doctor import run_doctor

    payload = run_doctor().to_dict()
    assert payload["status"] in {"ok", "warn", "fail"}
    assert isinstance(payload["checks"], list)
