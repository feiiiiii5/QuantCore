"""Live quote service tests: parsers, market clock, fallback and API surface.

Everything here uses recorded fixtures and an injected fake HTTP client; the default
test suite never touches the network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantcore.realtime.clock import (
    is_trading_day,
    last_trade_date,
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
from tests.live_quote_fixtures import FakeHttp, _at, _eastmoney_payload, _sina_text

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1:8000"


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


def test_stale_cached_quote_is_refreshed_even_when_not_in_watchlist() -> None:
    http = FakeHttp()
    now = [_at("2026-11-02T10:15:30")]

    def clock() -> dt.datetime:
        return now[0]

    service = LiveQuoteService(
        http=http,
        config=LiveConfig(enabled=True, interval_seconds=2.0),
        clock=clock,
    )
    asyncio.run(service.quotes(["600000"]))
    calls_after_first = http.json_calls
    assert calls_after_first > 0
    now[0] = now[0] + dt.timedelta(seconds=60)  # beyond the staleness window
    fresh = asyncio.run(service.quotes(["600000"]))
    assert fresh["quotes"][0]["code"] == "600000"
    assert http.json_calls > calls_after_first  # refreshed, not silently stale


# ------------------------------------------------------- real XSHG calendar
# 2024 Spring Festival: closed 2024-02-09 .. 2024-02-18, reopens 2024-02-19.
def test_clock_uses_the_real_xshg_calendar() -> None:
    from quantcore.realtime.clock import calendar_source

    assert calendar_source() == "XSHG"


def test_spring_festival_is_holiday_and_next_open_crosses_it() -> None:
    assert is_trading_day(_at("2024-02-08T10:00:00")) is True
    assert is_trading_day(_at("2024-02-09T10:00:00")) is False
    assert market_phase(_at("2024-02-12T10:00:00")) == "holiday"
    assert market_phase(_at("2024-02-16T14:00:00")) == "holiday"
    assert next_open(_at("2024-02-08T15:30:00")) == _at("2024-02-19T09:30:00")
    assert next_open(_at("2024-02-12T10:00:00")) == _at("2024-02-19T09:30:00")
    clock = market_clock(_at("2024-02-12T10:00:00"))
    assert clock["phase"] == "holiday"
    assert clock["last_trade_date"] == 20240208
    assert clock["next_open"].startswith("2024-02-19T09:30:00")


def test_national_day_holiday_window() -> None:
    for day in range(1, 8):  # 2024-10-01 .. 2024-10-07 closed
        assert market_phase(_at(f"2024-10-0{day}T10:00:00")) == "holiday"
    assert market_phase(_at("2024-10-08T10:00:00")) == "open"
    assert next_open(_at("2024-09-30T15:30:00")) == _at("2024-10-08T09:30:00")
    assert market_clock(_at("2024-10-03T10:00:00"))["last_trade_date"] == 20240930


def test_preopen_after_holiday_reports_last_real_session() -> None:
    # 2026 National Day: closed 10-01..10-07; first session back is 10-08.
    assert market_phase(_at("2026-10-08T09:20:00")) == "pre_open"
    assert last_trade_date(_at("2026-10-08T09:20:00")) == 20260930
    assert market_clock(_at("2026-10-08T09:20:00"))["last_trade_date"] == 20260930
    assert next_open(_at("2026-10-08T09:20:00")) == _at("2026-10-08T09:30:00")
    # 2024 Spring Festival: first session back is 02-19; before open the last session is 02-08.
    assert last_trade_date(_at("2024-02-19T09:05:00")) == 20240208


def test_session_phase_boundaries_to_the_second() -> None:
    def phase(clock: str) -> str:
        return market_phase(_at(f"2026-11-02T{clock}"))

    assert phase("09:14:59") == "closed"
    assert phase("09:15:00") == "pre_open"
    assert phase("09:29:59") == "pre_open"
    assert phase("09:30:00") == "open"
    assert phase("11:29:59") == "open"
    assert phase("11:30:00") == "lunch"
    assert phase("12:59:59") == "lunch"
    assert phase("13:00:00") == "open"
    assert phase("14:59:59") == "open"
    assert phase("15:00:00") == "closed"


def test_next_open_handles_morning_lunch_and_afternoon() -> None:
    assert next_open(_at("2026-11-02T09:05:00")) == _at("2026-11-02T09:30:00")
    assert next_open(_at("2026-11-02T09:20:00")) == _at("2026-11-02T09:30:00")
    assert next_open(_at("2026-11-02T10:30:00")) == _at("2026-11-02T13:00:00")
    assert next_open(_at("2026-11-02T12:10:00")) == _at("2026-11-02T13:00:00")
    assert next_open(_at("2026-11-02T14:10:00")) == _at("2026-11-03T09:30:00")
    assert next_open(_at("2026-11-02T20:00:00")) == _at("2026-11-03T09:30:00")


def test_weekend_next_open_and_last_trade_date() -> None:
    assert market_phase(_at("2026-11-07T10:00:00")) == "holiday"
    assert next_open(_at("2026-11-07T10:00:00")) == _at("2026-11-09T09:30:00")
    assert market_clock(_at("2026-11-08T23:00:00"))["last_trade_date"] == 20261106
    assert market_clock(_at("2026-11-09T15:00:00"))["last_trade_date"] == 20261109


def test_holidays_parameter_overrides_extra_closure() -> None:
    closure = {20261102}
    moment = _at("2026-11-02T10:00:00")
    assert market_phase(moment) == "open"
    assert market_phase(moment, holidays=closure) == "holiday"
    assert next_open(moment, holidays=closure) == _at("2026-11-03T09:30:00")
    assert last_trade_date(moment, holidays=closure) == 20261030


def test_out_of_bounds_calendar_falls_back_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quantcore.realtime.clock as clock_module

    def out_of_bounds(*args, **kwargs):
        raise ValueError("calendar out of bounds")

    monkeypatch.setattr(clock_module.trading_calendar, "is_trading_day", out_of_bounds)
    monkeypatch.setattr(clock_module.trading_calendar, "next_trading_day", out_of_bounds)
    monkeypatch.setattr(clock_module.trading_calendar, "previous_trading_day", out_of_bounds)
    day = _at("2026-11-02T10:00:00")
    assert market_phase(day) == "open"  # weekday fallback keeps the service alive
    weekend = _at("2026-11-07T10:00:00")
    assert market_phase(weekend) == "holiday"
    assert next_open(_at("2026-11-06T16:00:00")) == _at("2026-11-09T09:30:00")
    # This is explicitly the weekday fallback, not a claim about holiday sessions.
    assert next_open(_at("2026-11-30T16:00:00")) == _at("2026-12-01T09:30:00")
    assert next_open(_at("2026-12-31T16:00:00")) == _at("2027-01-01T09:30:00")
    assert last_trade_date(_at("2027-01-01T09:00:00")) == 20261231
    assert last_trade_date(_at("2026-11-02T09:00:00")) == 20261030


# ------------------------------------------------- live REST/WS contract shape
def test_live_status_matches_ui_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        payload = client.get("/api/live/status", headers=AUTH).json()
    assert set(payload) == {
        "enabled",
        "source",
        "state",
        "market",
        "as_of",
        "latency_ms",
        "subscribed",
        "error",
        "notice",
    }
    market = payload["market"]
    assert {"phase", "is_trading_day", "server_time", "next_open", "last_trade_date"} <= set(market)
    assert market["phase"] in {"pre_open", "open", "lunch", "closed", "holiday"}
    assert payload["state"] in {"off", "idle", "connecting", "live", "error", "closed"}
    assert payload["source"] in {"eastmoney", "sina", "none"}


def test_live_ws_snapshot_contract_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    app = _app(tmp_path)
    ws_headers = {"host": "127.0.0.1:8000"}
    with TestClient(app, base_url=BASE_URL) as client:
        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client.websocket_connect("/ws/live?token=wrong", headers=ws_headers),
        ):
            pass
        assert excinfo.value.code == 1008
        with client.websocket_connect(
            f"/ws/live?token={TOKEN}&codes=600000", headers=ws_headers
        ) as socket:
            message = socket.receive_json()
        assert message["type"] == "snapshot"
        assert set(message) == {"type", "status", "indices", "quotes"}
        assert message["status"]["enabled"] is False
        assert message["indices"]["quotes"] == []
        assert message["quotes"]["quotes"] == []
        with (
            pytest.raises(WebSocketDisconnect) as bad_codes,
            client.websocket_connect(
                f"/ws/live?token={TOKEN}&codes=not-a-code", headers=ws_headers
            ),
        ):
            pass
        assert bad_codes.value.code == 1008


def test_live_quotes_validation_and_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    app = _app(tmp_path)
    with TestClient(app, base_url=BASE_URL) as client:
        too_many = ",".join(f"{index:06d}" for index in range(51))
        assert client.get(f"/api/live/quotes?codes={too_many}", headers=AUTH).status_code == 400
        assert client.get("/api/live/quotes?codes=bad", headers=AUTH).status_code == 400
        ok = client.get("/api/live/quotes", headers=AUTH).json()
        assert set(ok) == {"as_of", "source", "stale", "quotes"}


# ------------------------------------------------- quote parser edge cases
def test_preopen_missing_price_is_not_reported_as_suspended() -> None:
    payload = {
        "data": {
            "diff": [
                {"f2": "-", "f18": "10.00", "f12": "600000", "f14": "浦发银行"},
            ]
        }
    }
    preopen = parse_eastmoney_payload(payload, now=_at("2026-11-02T09:10:00"))[0]
    assert preopen.price == 10.00
    assert preopen.suspended is False
    halted = parse_eastmoney_payload(payload, now=_at("2026-11-02T10:10:00"))[0]
    assert halted.suspended is True


def test_new_beijing_920_codes_use_beijing_market() -> None:
    assert secid("920000") == "0.920000"
    assert secid("920001") == "0.920001"
    assert sina_symbol("920000") == "bj920000"
    assert secid("830799") == "0.830799"
    assert sina_symbol("830799") == "bj830799"


def test_live_service_survives_market_phase_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quantcore.realtime.service as service_module

    def broken_phase(*args, **kwargs):
        raise RuntimeError("calendar exploded")

    monkeypatch.setattr(service_module, "market_phase", broken_phase)
    service = LiveQuoteService(
        http=FakeHttp(),
        config=LiveConfig(enabled=True, interval_seconds=30.0),
        clock=lambda: _at("2026-11-02T10:00:00"),
    )

    async def run_briefly() -> None:
        task = asyncio.create_task(service._run())
        await asyncio.sleep(0.05)
        assert not task.done()  # the loop logged the error and kept sleeping
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_briefly())
    assert service._error is not None and "calendar exploded" in service._error
