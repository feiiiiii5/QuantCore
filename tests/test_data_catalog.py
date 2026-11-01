"""M8-005 V2 dataset catalog: descriptors are complete and API-served."""

from __future__ import annotations

from quantcore.data.catalog import CATALOG_VERSION, DATASETS


def test_catalog_descriptors() -> None:
    names = {dataset["name"] for dataset in DATASETS}
    assert {
        "daily_bars",
        "minute_bars",
        "securities",
        "financials",
        "corporate_actions",
        "snapshots",
    } <= names
    for dataset in DATASETS:
        assert dataset["version"] == CATALOG_VERSION
        assert dataset["fields"]
        assert dataset["grain"]


def test_catalog_api(api_client) -> None:
    response = api_client.get("/api/data/catalog")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == "v2"
    names = {item["name"] for item in payload["datasets"]}
    assert "minute_bars" in names and "securities" in names
    assert any("SYNTHETIC" in note for note in payload["notes"])
