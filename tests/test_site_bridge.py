"""Explicit HTTPS frontends can read a token-protected, loopback-only local API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from typer.testing import CliRunner

from quantcore.cli import app as cli
from quantcore.server import ServerSecurity, create_app

SITE = "https://research-site.example"
TOKEN = "site-bridge-test-token"


def application(root: Path, origins: list[str] | None = None):
    return create_app(
        token=TOKEN,
        allowed_origins=origins,
        port=8000,
        data_root=root,
        snapshots_root=root / "snapshots",
        experiments_root=root / "experiments",
        state_path=root / "state.sqlite",
        start_worker=False,
    )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://research-site.example",
        "null",
        "https://user:pass@research-site.example",
        "https://research-site.example/",
        "https://research-site.example/api",
        "https://research-site.example?",
        "https://research-site.example#fragment",
        "https://*.example",
        "https://",
        "https://research-site.example:invalid",
        "https://research-site.example:0",
        "https://research-site.example\\path",
    ],
)
def test_config_rejects_non_origin_urls(origin: str) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        ServerSecurity(token=TOKEN, allowed_origins=(origin,))


def test_config_canonicalizes_exact_https_origins() -> None:
    security = ServerSecurity(
        token=TOKEN, allowed_origins=("https://SITE.example:443", "https://site.example")
    )
    assert security.allowed_origins == ("https://site.example",)
    assert security.allowed_origin("https://site.example")
    assert not security.allowed_origin("https://site.example.evil")


def test_explicit_cors_preflight_pna_and_authenticated_requests(tmp_path: Path) -> None:
    app = application(tmp_path, [SITE])
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        preflight = client.options(
            "/api/meta",
            headers={
                "Origin": SITE,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == SITE
        assert preflight.headers["access-control-allow-private-network"] == "true"
        assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
        for authorization in (None, "Bearer wrong"):
            headers = {"Origin": SITE}
            if authorization:
                headers["Authorization"] = authorization
            denied = client.get("/api/meta", headers=headers)
            assert denied.status_code == 401
            assert denied.headers["access-control-allow-origin"] == SITE
        accepted = client.get(
            "/api/meta", headers={"Origin": SITE, "Authorization": f"Bearer {TOKEN}"}
        )
        assert accepted.status_code == 200
        assert accepted.headers["access-control-allow-origin"] == SITE
        assert accepted.json()["cors"] is True
        assert accepted.json()["allowed_origins"] == [SITE]
        assert client.get("/health").json()["allowed_origins"] == [SITE]
        assert app.state.security.public_dict()["cors"] is True
        assert app.state.security.public_dict()["allowed_origins"] == [SITE]
        assert "access-control-allow-credentials" not in accepted.headers
        assert client.options("/api/meta", headers={"Origin": SITE}).status_code == 401
        assert (
            client.post(
                "/api/meta", headers={"Origin": SITE, "Access-Control-Request-Method": "GET"}
            ).status_code
            == 401
        )
        bad_host = client.options(
            "/api/meta",
            headers={
                "Host": "evil.example:8000",
                "Origin": SITE,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert bad_host.status_code == 400
        assert "access-control-allow-origin" not in bad_host.headers
        bad_origin = client.options(
            "/api/meta",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert bad_origin.status_code == 403
        assert "access-control-allow-origin" not in bad_origin.headers
        forbidden_header = client.options(
            "/api/meta",
            headers={
                "Origin": SITE,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Forbidden",
            },
        )
        assert forbidden_header.status_code == 400


def test_default_has_no_cross_origin_access(tmp_path: Path) -> None:
    app = application(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        health = client.get("/health").json()
        assert health["cors"] is False
        assert health["allowed_origins"] == []
        response = client.options(
            "/api/meta", headers={"Origin": SITE, "Access-Control-Request-Method": "GET"}
        )
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers
        assert client.get("/api/meta").status_code == 401


@pytest.mark.parametrize(
    "origin,token,host",
    [
        ("https://evil.example", TOKEN, "127.0.0.1:8000"),
        (SITE, "wrong", "127.0.0.1:8000"),
        (SITE, TOKEN, "evil.example:8000"),
    ],
)
def test_websockets_keep_origin_host_and_token_checks(tmp_path: Path, origin, token, host) -> None:
    with TestClient(application(tmp_path, [SITE]), base_url="http://127.0.0.1:8000") as client:
        with (
            pytest.raises(WebSocketDisconnect) as error,
            client.websocket_connect(
                f"/ws/jobs/missing?token={token}", headers={"Origin": origin, "Host": host}
            ),
        ):
            pytest.fail("untrusted websocket accepted")
        assert error.value.code == 1008


def test_trusted_websocket_still_requires_its_existing_token(tmp_path: Path) -> None:
    with (
        TestClient(application(tmp_path, [SITE]), base_url="http://127.0.0.1:8000") as client,
        client.websocket_connect(
            f"/ws/jobs/missing?token={TOKEN}", headers={"Origin": SITE, "Host": "127.0.0.1:8000"}
        ) as socket,
    ):
        assert socket.receive_json()["error"] == "job not found"


def test_cli_repeatable_origins_keep_the_loopback_bind(tmp_path: Path, monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: captured.update(app=app, **kwargs))
    result = CliRunner().invoke(
        cli,
        [
            "serve",
            "--token",
            TOKEN,
            "--data-root",
            str(tmp_path),
            "--experiments-root",
            str(tmp_path / "experiments"),
            "--allow-origin",
            SITE,
            "--allow-origin",
            "https://second.example",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert captured["host"] == "127.0.0.1"
    assert captured["app"].state.security.allowed_origins == (SITE, "https://second.example")
    assert json.loads(result.stdout)["security"]["cors"] is True
