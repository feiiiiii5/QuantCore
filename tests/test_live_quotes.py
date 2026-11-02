"""Live quote service tests: parsers, market clock, fallback and API surface.

Everything here uses recorded fixtures and an injected fake HTTP client; the default
test suite never touches the network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantcore.realtime.clock import (
    SHANGHAI_TZ,
    market_clock,
    market_phase,
    next_open,
)
from quantcore.realtime.quotes import (
    QuoteSourceError,
    parse_eastmoney_payload,
    parse_sina_payload,
    secid,
    sina_symbol,
)
from quantcore.realtime.service import LiveConfig, LiveQuoteService
from quantcore.server import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "live"
TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1:8000"


def _eastmoney_payload() -> dict:
    return json.loads((FIXTURES / "eastmoney_ulist.json").read_text(encoding="utf-8"))


def _sina_text() -> str:
    return (FIXTURES / "sina_quotes.txt").read_text(encoding="utf-8")


def _at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=SHANGHAI_TZ)


class FakeHttp:
    """Request-aware fake transport backed by the recorded fixtures."""

    def __init__(self, *, fail_json: bool = False) -> None:
        self.fail_json = fail_json
        self.json_calls = 0
        self.text_calls = 0
        self.index_rows = [_eastmoney_payload()["data"]["diff"][2]]
        self.stock_rows = _eastmoney_payload()["data"]["diff"][:2]

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None):
        self.json_calls += 1
        if self.fail_json:
            raise ConnectionError("eastmoney blocked (simulated)")
        rows = (
            list(self.index_rows)
            if ("1.000001" in url or "0.399001" in url)
            else list(self.stock_rows)
        )
        return {"data": {"total": len(rows), "diff": rows}}

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        self.text_calls += 1
        lines = _sina_text().splitlines()
        if "sh000001" in url or "sz399001" in url:
            return lines[2]
        return "\n".join(lines[:2])


# ------------------------------------------------------------------ parsers
def test_parse_eastmoney_payload_normalizes_shares_and_change() -> None:
    now = _at("2026-11-02T10:15:30")
    quotes = parse_eastmoney_payload(_eastmoney_payload(), now=now)
    assert {quote.code for quote in quotes} == {"600000", "000001"}
    pufa = next(quote for quote in quotes if quote.code == "600000")
    assert pufa.name == "浦发银行"
    assert pufa.price == 10.05
    assert pufa.prev_close == 9.89
    assert abs(pufa.change - 0.16) < 1e-9
    assert abs(pufa.change_pct - 1.6178) < 0.01
    assert pufa.volume == 1234567 * 100  # lots -> shares
    assert pufa.limit_up == 10.88
    assert pufa.limit_down == 8.90
    assert pufa.suspended is False


def test_parse_eastmoney_as_index_prefixes_codes() -> None:
    payload = {"data": {"diff": [_eastmoney_payload()["data"]["diff"][2]]}}
    quotes = parse_eastmoney_payload(payload, as_index=True)
    assert quotes and quotes[0].code == "idx:000001"
    assert quotes[0].name == "上证指数"


def test_parse_sina_payload_reads_quotes_and_index() -> None:
    now = _at("2026-11-02T10:15:30")
    stock_lines = _sina_text().splitlines()[:2]  # one request never mixes stocks and indices
    quotes = parse_sina_payload("\n".join(stock_lines), now=now)
    by_code = {quote.code: quote for quote in quotes}
    assert set(by_code) == {"600000", "000001"}
    assert by_code["600000"].volume == 123456700
    assert by_code["000001"].name == "平安银行"
    index = parse_sina_payload(_sina_text().splitlines()[2], as_index=True)
    assert index and index[0].code == "idx:000001"
    assert index[0].price == 3601.23


def test_secid_and_sina_symbol_mapping() -> None:
    assert secid("600000") == "1.600000"
    assert secid("000001") == "0.000001"
    assert secid("300750") == "0.300750"
    assert secid("830799") == "0.830799"
    assert secid("idx:000001") == "1.000001"
    assert sina_symbol("600000") == "sh600000"
    assert sina_symbol("000001") == "sz000001"
    assert sina_symbol("830799") == "bj830799"
    assert sina_symbol("idx:399001") == "sz399001"


# ------------------------------------------------------------------ clock
def test_market_phase_follows_session_schedule() -> None:
    day = "2026-11-02T"  # Monday
    assert market_phase(_at(day + "09:00:00")) == "closed"
    assert market_phase(_at(day + "09:20:00")) == "pre_open"
    assert market_phase(_at(day + "10:00:00")) == "open"
    assert market_phase(_at(day + "12:00:00")) == "lunch"
    assert market_phase(_at(day + "14:00:00")) == "open"
    assert market_phase(_at(day + "16:00:00")) == "closed"
    assert market_phase(_at("2026-11-07T10:00:00")) == "holiday"  # Saturday


def test_market_clock_payload_and_next_open() -> None:
    clock = market_clock(_at("2026-11-02T10:00:00"))
    assert clock["phase"] == "open"
    assert clock["label"] == "交易中"
    assert clock["last_trade_date"] == 20261030
    assert clock["next_open"].startswith("2026-11-02T13:00:00")
    weekend = market_clock(_at("2026-11-07T10:00:00"))
    assert weekend["phase"] == "holiday"
    assert next_open(_at("2026-11-07T10:00:00")).strftime("%Y%m%d") == "20261109"


# ------------------------------------------------------------------ service
def test_service_offline_by_default() -> None:
    service = LiveQuoteService(config=LiveConfig(enabled=False))
    status = asyncio.run(service.status())
    assert status["enabled"] is False
    assert status["state"] == "off"
    assert "QC_ALLOW_NETWORK" in status["notice"]
    payload = asyncio.run(service.quotes(["600000"]))
    assert payload["quotes"] == []
    assert payload["stale"] is True


def test_service_refresh_uses_eastmoney_and_index_cache() -> None:
    http = FakeHttp()
    fixed = _at("2026-11-02T10:15:30")
    service = LiveQuoteService(
        http=http,
        config=LiveConfig(enabled=True, interval_seconds=2.0),
        clock=lambda: fixed,
    )
    asyncio.run(service.refresh(["600000", "000001"]))
    status = asyncio.run(service.status())
    assert status["state"] == "live"
    assert status["source"] == "eastmoney"
    assert status["subscribed"] >= 3  # two stocks + one index
    quotes = asyncio.run(service.quotes(["600000"]))
    assert [quote["code"] for quote in quotes["quotes"]] == ["600000"]
    indices = asyncio.run(service.indices())
    assert [quote["code"] for quote in indices["quotes"]] == ["000001"]
    assert indices["quotes"][0]["name"] == "上证指数"
    # Stock code 000001 must not be shadowed by the index with the same digits.
    stock = asyncio.run(service.quotes(["000001"]))
    assert stock["quotes"][0]["name"] == "平安银行"


def test_service_falls_back_to_sina() -> None:
    http = FakeHttp(fail_json=True)
    fixed = _at("2026-11-02T10:15:30")
    service = LiveQuoteService(
        http=http,
        config=LiveConfig(enabled=True, interval_seconds=2.0),
        clock=lambda: fixed,
    )
    asyncio.run(service.refresh(["600000"]))
    status = asyncio.run(service.status())
    assert status["source"] == "sina"
    assert status["state"] == "live"
    quotes = asyncio.run(service.quotes(["600000"]))
    assert quotes["quotes"][0]["price"] == 10.05


def test_service_reports_source_errors() -> None:
    class BrokenHttp:
        async def get_json(self, url, *, headers=None):
            raise ConnectionError("down")

        async def get_text(self, url, *, headers=None):
            raise ConnectionError("down")

    service = LiveQuoteService(
        http=BrokenHttp(),
        config=LiveConfig(enabled=True),
        clock=lambda: _at("2026-11-02T10:00:00"),
    )
    with pytest.raises(QuoteSourceError):
        asyncio.run(service.refresh(["600000"]))
    status = asyncio.run(service.status())
    assert status["state"] == "error"
    assert status["error"]


# ------------------------------------------------------------------ API
def _app(tmp_path: Path):
    return create_app(
        token=TOKEN,
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=tmp_path / "snapshots",
        experiments_root=tmp_path / "experiments",
        ui_dir=tmp_path / "ui",
        start_worker=False,
    )


def test_live_api_requires_token_and_reports_offline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        assert client.get("/api/live/status").status_code == 401
        response = client.get("/api/live/status", headers=AUTH)
        assert response.status_code == 200
        payload = response.json()
        assert payload["enabled"] is False
        assert payload["state"] == "off"
        assert payload["market"]["phase"] in {"closed", "open", "lunch", "pre_open", "holiday"}
        indices = client.get("/api/live/indices", headers=AUTH).json()
        assert indices["quotes"] == []
        quotes = client.get("/api/live/quotes?codes=600000,000001", headers=AUTH)
        assert quotes.status_code == 200
        assert quotes.json()["quotes"] == []
        bad = client.get("/api/live/quotes?codes=not-a-code", headers=AUTH)
        assert bad.status_code == 400
