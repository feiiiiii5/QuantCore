"""Regression checks for quote identity, source timestamps and partial fallbacks."""

import asyncio
import datetime as dt

from quantcore.realtime.quotes import parse_eastmoney_payload, parse_sina_payload
from quantcore.realtime.service import LiveConfig, LiveQuoteService
from tests.live_quote_fixtures import FakeHttp, _at, _eastmoney_payload, _sina_text


def test_index_refresh_does_not_keep_an_unwatched_stock_fresh() -> None:
    http = FakeHttp()
    now = [_at("2026-11-02T10:15:30")]
    service = LiveQuoteService(http=http, config=LiveConfig(enabled=True), clock=lambda: now[0])
    asyncio.run(service.quotes(["600000"]))
    now[0] += dt.timedelta(seconds=30)
    asyncio.run(service.refresh())  # the background poller only requests indices
    http.stock_rows[0]["f2"] = "11.00"
    http.stock_rows[0]["f124"] = int(now[0].timestamp())
    calls = http.json_calls
    payload = asyncio.run(service.quotes(["600000"]))
    assert payload["quotes"][0]["price"] == 11.0
    assert http.json_calls > calls


def test_partial_primary_response_falls_back_for_missing_stock() -> None:
    http = FakeHttp()
    http.stock_rows = []
    service = LiveQuoteService(
        http=http, config=LiveConfig(enabled=True), clock=lambda: _at("2026-11-02T10:15:30")
    )
    payload = asyncio.run(service.quotes(["600000"]))
    assert payload["quotes"][0]["code"] == "600000"
    assert payload["quotes"][0]["source"] == "sina"
    assert http.text_calls > 0


def test_source_timestamp_is_not_replaced_by_receive_time() -> None:
    now = _at("2026-11-02T10:15:30")
    raw = _eastmoney_payload()
    assert parse_eastmoney_payload(raw, now=now)[0].timestamp is None
    raw["data"]["diff"][0]["f124"] = int(_at("2026-11-02T10:14:00").timestamp())
    assert parse_eastmoney_payload(raw, now=now)[0].timestamp == "2026-11-02T10:14:00+08:00"
    assert parse_sina_payload(_sina_text(), now=now)[0].timestamp == "2026-11-02T10:15:30+08:00"


def test_old_source_data_stays_stale_even_when_just_fetched() -> None:
    http = FakeHttp()
    service = LiveQuoteService(
        http=http, config=LiveConfig(enabled=True), clock=lambda: _at("2026-11-02T10:30:00")
    )
    payload = asyncio.run(service.quotes(["600000"]))
    assert payload["stale"] is True
    assert payload["quotes"][0]["timestamp"] == "2026-11-02T10:15:30+08:00"
    assert asyncio.run(service.status())["state"] == "idle"


def test_index_failure_does_not_discard_a_healthy_primary_stock_quote() -> None:
    class IndexFailure(FakeHttp):
        async def get_json(self, url, *, headers=None):
            if "1.000001" in url:
                raise ConnectionError("index endpoint unavailable")
            return await super().get_json(url, headers=headers)

    http = IndexFailure()
    http.stock_rows[0]["f2"] = "11.00"
    service = LiveQuoteService(
        http=http, config=LiveConfig(enabled=True), clock=lambda: _at("2026-11-02T10:15:30")
    )
    payload = asyncio.run(service.quotes(["600000"]))
    assert payload["quotes"][0]["source"] == "eastmoney"
    assert payload["quotes"][0]["price"] == 11.0
