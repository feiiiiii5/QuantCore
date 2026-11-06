"""Display-only daily candles use public fixtures without touching research snapshots."""

import asyncio
import datetime as dt
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantcore.realtime.clock import SHANGHAI_TZ
from quantcore.realtime.service import LiveConfig, LiveQuoteService
from quantcore.server import create_app


class HistoryHttp:
    def __init__(self, fail_primary=False):
        self.fail_primary = fail_primary
        self.calls = 0
        self.days = pd.bdate_range("2026-09-01", periods=30).strftime("%Y-%m-%d").tolist()

    async def get_json(self, url, *, headers=None):
        self.calls += 1
        assert "klt=101" in url and "fqt=0" in url
        if self.fail_primary:
            raise ConnectionError("primary unavailable")
        return {
            "data": {
                "name": "非本地证券",
                "klines": [f"{day},10,11,12,9,123,135300,0,10,1,0.5" for day in self.days],
            }
        }

    async def get_text(self, url, *, headers=None):
        self.calls += 1
        assert "scale=240" in url
        return json.dumps(
            [
                {
                    "day": day,
                    "open": "10",
                    "close": "11",
                    "high": "12",
                    "low": "9",
                    "volume": "12300",
                }
                for day in self.days
            ]
        )


@pytest.mark.parametrize("fail_primary", [False, True])
def test_live_daily_history_has_units_warmed_means_and_no_warehouse(fail_primary):
    http = HistoryHttp(fail_primary)
    now = [dt.datetime(2026, 11, 6, 10, 0, tzinfo=SHANGHAI_TZ)]
    service = LiveQuoteService(http=http, config=LiveConfig(enabled=True), clock=lambda: now[0])
    payload = asyncio.run(service.bars("603999", limit=10))
    assert payload["code"] == "603999"
    assert len(payload["dates"]) == 10
    assert payload["synthetic"] is False
    assert payload["volume"] == [12300] * 10
    assert payload["ma20"] == [11.0] * 10
    assert payload["source"] == ("sina" if fail_primary else "eastmoney")
    assert payload["amount"] == ([None] * 10 if fail_primary else [135300.0] * 10)
    calls = http.calls
    assert asyncio.run(service.bars("603999", 10)) == payload
    assert http.calls == calls
    now[0] += dt.timedelta(seconds=61)
    asyncio.run(service.bars("603999", 10))
    assert http.calls > calls


def test_live_history_is_opt_in_and_covers_nonlocal_security(tmp_path, monkeypatch):
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    app = create_app(
        token="test-token",
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path,
        start_worker=False,
    )
    http = HistoryHttp()
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.headers.update({"Authorization": "Bearer test-token"})
        assert client.get("/api/live/bars?code=603999").status_code == 409
        assert http.calls == 0
        app.state.live.config = LiveConfig(enabled=True)
        app.state.live.http = http
        app.state.live.history.http = http
        response = client.get("/api/live/bars?code=603999&limit=10")
        assert response.status_code == 200
        assert response.json()["code"] == "603999"
        assert client.get("/api/live/bars?code=invalid").status_code == 400
        assert not (tmp_path / "warehouse").exists()
