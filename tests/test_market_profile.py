"""M8 stock-profile expansion: list fields + per-security profile endpoint."""

from __future__ import annotations


def test_security_list_exposes_profile_fields(api_client) -> None:
    response = api_client.get("/api/market/securities?limit=3")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    for row in rows:
        for key in (
            "sec_id",
            "code",
            "name",
            "board",
            "industry",
            "sec_type",
            "exchange",
            "list_date",
            "delist_date",
            "source",
        ):
            assert key in row, key
        assert row["sec_type"] == "STOCK"
        assert row["exchange"] in {"SH", "SZ", "BJ", ""}


def test_security_profile_returns_metadata_and_quote(api_client) -> None:
    listed = api_client.get("/api/market/securities?limit=1").json()[0]
    response = api_client.get(f"/api/market/securities/{listed['code']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == listed["code"]
    assert payload["sec_id"] == listed["sec_id"]
    assert payload["source"]
    assert payload["quote"]["date"] > 0
    assert payload["quote"]["close"] > 0
    # sec_id is accepted as an alias for code.
    by_id = api_client.get(f"/api/market/securities/{payload['sec_id']}")
    assert by_id.status_code == 200
    assert by_id.json()["code"] == payload["code"]


def test_unknown_security_profile_is_404(api_client) -> None:
    response = api_client.get("/api/market/securities/NOT_A_SECURITY")
    assert response.status_code == 404
    assert "unknown security" in response.json()["detail"]
