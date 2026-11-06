"""Whole-snapshot security search and exact watchlist selection."""

from types import SimpleNamespace
from typing import cast

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantcore.server import routes_market
from quantcore.server.workspace import Workspace


@pytest.fixture
def search_client(monkeypatch):
    codes = [f"{number:06d}" for number in range(1002)]
    securities = pd.DataFrame(
        {
            "sec_id": [f"SH.{code}" for code in codes],
            "code": codes,
            "name": [f"证券 {code}" for code in codes],
            "industry": ["银行"] * len(codes),
            "board": ["MAIN"] * len(codes),
        }
    )
    securities.loc[1001, "name"] = "名称[测试]"
    panel = SimpleNamespace(
        securities=securities,
        bars=pd.DataFrame(
            {"sec_id": securities.sec_id, "date": 20240102, "close": 10.0, "pre_close": 10.0}
        ),
    )
    monkeypatch.setattr(routes_market, "_latest_panel", lambda *_: (panel, {}))
    app = FastAPI()
    routes_market.register_market_routes(app, cast(Workspace, object()))
    with TestClient(app) as client:
        yield client


def test_search_and_watchlist_include_securities_beyond_first_page(search_client):
    first_page = search_client.get("/api/market/securities", params={"limit": 1000}).json()
    assert "001001" not in {row["code"] for row in first_page}
    searched = search_client.get("/api/market/securities", params={"query": "001001", "limit": 8})
    assert [row["code"] for row in searched.json()] == ["001001"]
    watched = search_client.get(
        "/api/market/securities", params={"codes": "001001,000003", "limit": 1000}
    )
    assert [row["code"] for row in watched.json()] == ["000003", "001001"]
    narrowed = search_client.get(
        "/api/market/securities", params={"codes": "001001,000003", "query": "001001"}
    )
    assert [row["code"] for row in narrowed.json()] == ["001001"]


@pytest.mark.parametrize(
    "query, expected", [("[", ["001001"]), ("银行", None), ("MAIN", None), ("   ", None)]
)
def test_search_treats_text_literally_and_supports_visible_fields(search_client, query, expected):
    response = search_client.get("/api/market/securities", params={"query": query, "limit": 8})
    assert response.status_code == 200
    rows = response.json()
    if expected is None:
        assert len(rows) == 8
    else:
        assert [row["code"] for row in rows] == expected
