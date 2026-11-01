"""M2-015 PIT financial view: announcements filtered by as_of."""

from __future__ import annotations


def test_financials_pit_filter(api_client) -> None:
    listed = api_client.get("/api/market/securities?limit=1").json()[0]
    response = api_client.get(f"/api/market/financials/{listed['code']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == listed["code"]
    assert payload["rows"]
    assert payload["latest"] is not None
    first_ann = int(payload["rows"][0]["ann_date"])
    as_of = f"{first_ann // 10000:04d}-{first_ann // 100 % 100:02d}-{first_ann % 100:02d}"
    filtered = api_client.get(f"/api/market/financials/{listed['code']}?as_of={as_of}").json()
    assert filtered["rows"]
    assert all(int(row["ann_date"]) <= first_ann for row in filtered["rows"])
    assert filtered["latest"] is not None


def test_financials_unknown_security_and_bad_date(api_client) -> None:
    assert api_client.get("/api/market/financials/NOT_A_SEC").status_code == 404
    listed = api_client.get("/api/market/securities?limit=1").json()[0]
    assert (
        api_client.get(f"/api/market/financials/{listed['code']}?as_of=bad-date").status_code == 400
    )
