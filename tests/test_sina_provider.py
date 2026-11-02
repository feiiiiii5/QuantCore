"""Sina provider tests: recorded fixtures only, never network.

Covers universe parsing/pagination, board inference, symbol mapping, volume units
(shares as-is), date sorting, calendar slicing, real recorded qfq-based adjustment and
deterministic corporate-action break derivation, plus error/permission paths.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quantcore.errors import ProviderError, ProviderPermissionError
from quantcore.providers.base import ProviderQuota, RateLimiter, RetryPolicy
from quantcore.providers.public_web import (
    derive_adjustment,
    infer_board,
    infer_exchange,
    normalize_code,
    parse_public_json,
    parse_sina_daily,
    parse_tencent_qfq,
    sina_symbol,
)
from quantcore.providers.registry import create_provider, describe_providers, list_providers
from quantcore.providers.sina import SinaProvider

FIXTURES = Path(__file__).parent / "fixtures" / "sina"
NO_LIMIT = ProviderQuota(min_interval_seconds=0.0, max_calls=None)


class RecordedTransport:
    """Serve the recorded Sina/Tencent text files (offline)."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, kind: str, params: Mapping[str, Any]) -> str:
        self.requests.append((kind, dict(params)))
        if kind == "universe":
            path = FIXTURES / ("universe_page" + str(int(params.get("page", 1))) + ".json")
            return path.read_text(encoding="utf-8") if path.exists() else "[]"
        if kind == "kline":
            path = FIXTURES / ("kline_" + str(params["symbol"]) + ".json")
        elif kind == "index_kline":
            path = FIXTURES / ("index_kline_" + str(params["symbol"]) + ".json")
        elif kind == "qfq":
            symbol = str(params["param"]).split(",")[0]
            path = FIXTURES / ("qfq_" + symbol + ".json")
        else:  # pragma: no cover - defensive
            raise ProviderError(f"unknown fixture request: {kind}")
        if not path.exists():
            raise ProviderError(f"sina fixture not found: {path}")
        return path.read_text(encoding="utf-8")
        raise AssertionError(f"unexpected request kind: {kind}")


def make_provider(**kwargs: Any) -> SinaProvider:
    transport = kwargs.pop("transport", None) or RecordedTransport()
    return SinaProvider(
        transport=transport,
        limiter=RateLimiter(NO_LIMIT),
        retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0),
        max_workers=1,
        **kwargs,
    )


def test_registry_and_capabilities() -> None:
    assert {"sina", "eastmoney"} <= set(list_providers())
    rows = {item["name"]: item for item in describe_providers()}
    sina = rows["sina"]
    assert sina["capabilities"]["daily_bars"] is True
    assert sina["capabilities"]["security_master"] is True
    assert sina["capabilities"]["realtime"] is False
    assert sina["permission"]["requires_credentials"] is False
    assert sina["quota"]["min_interval_seconds"] >= 0.25
    assert "concurrent" in sina["quota"]["notes"]
    provider = create_provider("sina", allow_network=False)
    assert provider.name == "sina"


@pytest.mark.parametrize(
    ("code", "board", "exchange", "symbol"),
    [
        ("600000", "MAIN", "SH", "sh600000"),
        ("601398", "MAIN", "SH", "sh601398"),
        ("688981", "STAR", "SH", "sh688981"),
        ("000001", "MAIN", "SZ", "sz000001"),
        ("002594", "MAIN", "SZ", "sz002594"),
        ("300750", "GEM", "SZ", "sz300750"),
        ("830799", "BSE", "BJ", "bj830799"),
        ("430047", "BSE", "BJ", "bj430047"),
        ("920000", "BSE", "BJ", "bj920000"),
    ],
)
def test_board_exchange_symbol_mapping(code: str, board: str, exchange: str, symbol: str) -> None:
    assert infer_board(code) == board
    assert infer_exchange(code) == exchange
    assert sina_symbol(code) == symbol


def test_code_normalisation_and_invalid_codes() -> None:
    for value in ("600000", "sh600000", "SH.600000", "600000.SH"):
        assert normalize_code(value) == "600000"
    with pytest.raises(ProviderError):
        normalize_code("abc")
    with pytest.raises(ProviderError):
        normalize_code("60000")
    with pytest.raises(ProviderError):
        infer_board("900001")  # B-share prefix is not an A-share board


def test_parse_public_json_strict_bare_keys_and_null() -> None:
    assert parse_public_json('{"a": 1}') == {"a": 1}
    tolerant = '[{symbol:"sh600000",code:"600000",name:"浦发银行"}]'
    rows = parse_public_json(tolerant)
    assert rows[0]["code"] == "600000"
    assert rows[0]["name"] == "浦发银行"
    assert parse_public_json("null") is None
    with pytest.raises(ProviderError):
        parse_public_json("not-json-at-all")


def test_recorded_universe_parsing() -> None:
    page1 = json.loads((FIXTURES / "universe_page1.json").read_text(encoding="utf-8"))
    from quantcore.providers.public_web import normalize_sina_universe

    frame = normalize_sina_universe(page1)
    assert len(frame) == 80
    assert list(frame.columns) == [
        "sec_id",
        "code",
        "exchange",
        "name",
        "board",
        "list_date",
        "delist_date",
        "sec_type",
        "industry",
        "source",
    ]
    assert frame.iloc[0]["sec_id"] == "BJ.920000"
    assert frame.iloc[0]["board"] == "BSE"
    assert (frame["source"] == "SINA").all()
    page8 = json.loads((FIXTURES / "universe_page8.json").read_text(encoding="utf-8"))
    frame8 = normalize_sina_universe(page8)
    assert frame8.iloc[0]["code"] == "600279"
    assert frame8.iloc[0]["sec_id"] == "SH.600279"
    assert frame8.iloc[0]["board"] == "MAIN"


def test_security_master_pagination_and_limit() -> None:
    page1 = (FIXTURES / "universe_page1.json").read_text(encoding="utf-8")
    page2_rows = json.loads(page1)[:5]
    calls = {"n": 0}

    def transport(kind: str, params: Mapping[str, Any]) -> str:
        assert kind == "universe"
        calls["n"] += 1
        page = int(params.get("page", 1))
        if page == 1:
            return page1
        if page == 2:
            return json.dumps(page2_rows, ensure_ascii=False)
        return "[]"

    provider = make_provider(transport=transport)
    master = provider.fetch_security_master()
    assert len(master) == 85
    assert calls["n"] == 3  # page 1, page 2, empty page 3
    limited = make_provider(limit=3)
    assert len(limited.fetch_security_master()) == 3
    assert len(limited._transport.requests) == 1


def test_daily_bars_volume_is_shares_and_amount_is_estimated() -> None:
    provider = make_provider()
    bars = provider.fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    assert len(bars) == 9
    assert bars["date"].tolist() == sorted(bars["date"].tolist())
    assert str(bars.iloc[0]["sec_id"]) == "SH.600000"
    raw_volume = json.loads((FIXTURES / "kline_sh600000.json").read_text(encoding="utf-8"))
    first_day = next(row for row in raw_volume if row["day"] == "2026-10-20")
    assert int(first_day["volume"]) == int(bars.iloc[0]["volume"])  # shares, NOT lots
    assert int(bars.iloc[0]["volume"]) == 60_513_255
    # amount is an estimate: volume x mean(open, high, low, close) - magnitude only
    row = bars.iloc[0]
    expected_amount = round(
        row["volume"] * (row["open"] + row["high"] + row["low"] + row["close"]) / 4.0, 2
    )
    assert row["amount"] == pytest.approx(expected_amount)
    assert bars.iloc[0]["pre_close"] == pytest.approx(9.78)  # from the previous fixture day
    assert set(bars.columns) >= {
        "date",
        "sec_id",
        "code",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "adj_factor",
        "limit_up",
        "limit_down",
        "suspended",
        "st",
        "source",
    }
    assert (bars["source"] == "SINA").all()
    assert (bars["suspended"] == False).all()  # noqa: E712 - pandas bool column


def test_calendar_uses_index_kline_and_slices() -> None:
    provider = make_provider()
    calendar = provider.fetch_calendar("2026-10-20", "2026-10-31")
    assert len(calendar) == 9
    assert calendar.dates[0] == 20261020
    assert calendar.dates[-1] == 20261030
    assert any(kind == "index_kline" for kind, _ in provider._transport.requests)


def test_real_recorded_qfq_derives_a_dividend_break() -> None:
    provider = make_provider()
    raw = provider._raw_daily("600000", 20260101, 20261031)
    qfq = provider._qfq_closes("600000", 20260101, 20261031)
    factor, actions = derive_adjustment(raw, qfq, source="SINA_APPROX")
    assert len(factor) == len(raw)
    values = factor.to_numpy()
    assert values[0] < 0.99  # pre-dividend qfq factor
    assert values[-1] == pytest.approx(1.0)
    assert np.all(np.diff(values) >= -1e-9)  # adj_factor is non-decreasing
    assert len(actions) == 1
    action = actions.iloc[0]
    assert int(action["ex_date"]) == 20260716
    assert 0.30 <= float(action["cash_per_share"]) <= 0.50
    assert float(action["split_ratio"]) == 1.0
    assert action["source"] == "SINA_APPROX"
    # the ex-date pre_close uses the adjusted reference, so limit prices stay consistent
    bars = provider.fetch_daily_bars(["600000"], "2026-07-15", "2026-07-17")
    ex_row = bars[bars["date"] == 20260716].iloc[0]
    previous = bars[bars["date"] == 20260715].iloc[0]
    adjusted_reference = (
        float(previous["close"]) * float(previous["adj_factor"]) / float(ex_row["adj_factor"])
    )
    assert ex_row["pre_close"] == pytest.approx(adjusted_reference, abs=0.011)
    assert ex_row["limit_up"] > ex_row["close"] > ex_row["limit_down"]


def test_company_action_break_is_derived_deterministically() -> None:
    dates = [20260622, 20260623, 20260624, 20260625, 20260626]
    raw = pd.DataFrame(
        {
            "date": dates,
            "sec_id": "SH.600000",
            "close": [10.00, 10.00, 10.00, 9.70, 9.80],
        }
    )
    adjusted = pd.DataFrame({"date": dates, "close": [9.50, 9.50, 9.50, 9.70, 9.80]})
    factor, actions = derive_adjustment(raw, adjusted)
    assert factor.tolist() == pytest.approx([0.95, 0.95, 0.95, 1.0, 1.0])
    assert len(actions) == 1
    action = actions.iloc[0]
    assert int(action["ex_date"]) == 20260625
    assert float(action["cash_per_share"]) == pytest.approx(0.50, abs=0.01)
    assert float(action["split_ratio"]) == 1.0


def test_corporate_actions_via_provider_and_cache() -> None:
    provider = make_provider()
    provider.fetch_daily_bars(["600000"], "2026-01-01", "2026-10-31")
    requests_after_bars = len(provider._transport.requests)
    actions = provider.fetch_corporate_actions(["600000"], "2026-01-01", "2026-10-31")
    assert len(actions) == 1
    assert int(actions.iloc[0]["ex_date"]) == 20260716
    assert len(provider._transport.requests) == requests_after_bars  # cache hit


def test_derive_actions_can_be_disabled() -> None:
    provider = make_provider(derive_actions=False)
    bars = provider.fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    assert (bars["adj_factor"] == 1.0).all()
    assert provider.fetch_corporate_actions(["600000"], "2026-10-20", "2026-10-30").empty
    assert not any(kind == "qfq" for kind, _ in provider._transport.requests)


def test_incremental_window_only_returns_requested_days() -> None:
    provider = make_provider()
    bars = provider.fetch_daily_bars(["600000"], "2026-10-27", "2026-10-30")
    assert bars["date"].tolist() == [20261027, 20261028, 20261029, 20261030]
    kline_requests = [params for kind, params in provider._transport.requests if kind == "kline"]
    assert kline_requests and kline_requests[0]["symbol"] == "sh600000"
    assert int(kline_requests[0]["datalen"]) >= 40


def test_missing_fixture_and_parse_helpers() -> None:
    provider = make_provider()
    with pytest.raises(ProviderError, match="fixture not found"):
        provider.fetch_daily_bars(["000001"], "2026-10-20", "2026-10-31")
    assert parse_sina_daily([], "600000").empty
    assert parse_sina_daily([{"day": "bad-date", "open": 1}], "600000").empty
    assert parse_tencent_qfq({}, "sh600000").empty
    assert (
        parse_tencent_qfq(
            {"data": {"sh600000": {"qfqday": [["2026-01-02", "1", "2"]]}}}, "sh600000"
        ).iloc[0]["close"]
        == 2.0
    )


def test_network_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    provider = SinaProvider(allow_network=False)
    with pytest.raises(ProviderPermissionError, match="QC_ALLOW_NETWORK"):
        provider.ensure_available()
    with pytest.raises(ProviderPermissionError):
        provider.fetch_security_master()
    monkeypatch.setenv("QC_ALLOW_NETWORK", "1")
    provider.ensure_available()
    assert provider.allow_network is True


def _adjustment_frames(
    raw_closes: list[float], adjusted_closes: list[float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = [20240101 + index for index in range(len(raw_closes))]
    raw = pd.DataFrame({"date": dates, "close": raw_closes, "sec_id": ["SZ.000001"] * len(dates)})
    adjusted = pd.DataFrame({"date": dates, "close": adjusted_closes})
    return raw, adjusted


def test_derive_adjustment_rejects_one_off_ratio_spike() -> None:
    """A single-day qfq ratio bump (vendor glitch) must not fabricate an ex-date."""
    raw, adjusted = _adjustment_frames([10.0] * 9, [8.0] * 5 + [8.24] + [8.0] * 3)
    factor, actions = derive_adjustment(raw, adjusted)
    assert actions.empty
    assert float(factor.iloc[-1]) == pytest.approx(0.8, abs=1e-6)


def test_derive_adjustment_rejects_ratio_jump_on_limit_up_day() -> None:
    """Regression for the real 000001 2024-02-21 case: a qfq ratio step on a limit-up day
    implies a >11% adjusted return, so it must be treated as a vendor glitch."""
    raw_closes = [9.70, 9.75, 9.72, 9.60, 9.55, 9.81, 9.82, 10.80, 10.90, 10.85, 10.53, 10.50]
    adjusted = [round(value * 0.7788, 3) for value in raw_closes[:7]]
    adjusted += [round(value * 0.7989, 3) for value in raw_closes[7:]]
    raw, adjusted_frame = _adjustment_frames(raw_closes, adjusted)
    factor, actions = derive_adjustment(raw, adjusted_frame)
    assert actions.empty
    assert float(factor.iloc[-1]) == pytest.approx(0.7788, abs=1e-4)


def test_derive_adjustment_accepts_sustained_dividend_step() -> None:
    """A genuine ex-dividend shows up as a persistent qfq/raw ratio step."""
    raw_closes = [10.0, 10.0, 10.0, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5, 9.5]
    adjusted = [9.5] * len(raw_closes)  # forward-adjusted prices stay smooth across the ex-date
    raw, adjusted_frame = _adjustment_frames(raw_closes, adjusted)
    factor, actions = derive_adjustment(raw, adjusted_frame)
    assert len(actions) == 1
    action = actions.iloc[0]
    assert int(action["ex_date"]) == 20240104
    assert float(action["cash_per_share"]) > 0
    assert float(factor.iloc[-1]) == pytest.approx(1.0, abs=1e-6)
