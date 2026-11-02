"""Eastmoney fallback provider tests: recorded/derived fixtures only, never network."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from quantcore.errors import ProviderError, ProviderPermissionError
from quantcore.providers.base import ProviderQuota, RateLimiter, RetryPolicy
from quantcore.providers.eastmoney import (
    EastmoneyProvider,
    normalize_eastmoney_kline,
    normalize_eastmoney_universe,
    secid_for_code,
)
from quantcore.providers.public_web import infer_board
from quantcore.providers.registry import create_provider, describe_providers, list_providers

FIXTURES = Path(__file__).parent / "fixtures" / "eastmoney"
NO_LIMIT = ProviderQuota(min_interval_seconds=0.0, max_calls=None)


class RecordedTransport:
    """Serve the recorded Eastmoney JSON fixtures; tag selects a boundary sample."""

    def __init__(self, tag: str = "") -> None:
        self.tag = tag
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, kind: str, params: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append((kind, dict(params)))
        if kind == "clist":
            path = FIXTURES / ("universe" + self.tag + ".json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if int(params.get("pn", 1)) > 1:
                total = int((payload.get("data") or {}).get("total") or 0)
                return {"rc": 0, "data": {"total": total, "diff": []}}
        elif kind == "index_kline":
            path = FIXTURES / ("index_kline" + self.tag + ".json")
        elif kind == "kline":
            secid = str(params["secid"])
            fqt = int(params.get("fqt", 0))
            path = FIXTURES / f"kline_{secid}_fqt{fqt}{self.tag}.json"
        else:  # pragma: no cover - defensive
            raise ProviderError(f"unknown fixture request: {kind}")
        if not path.exists():
            raise ProviderError(f"eastmoney fixture not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


def make_provider(tag: str = "", **kwargs: Any) -> EastmoneyProvider:
    transport = kwargs.pop("transport", None) or RecordedTransport(tag)
    return EastmoneyProvider(
        transport=transport,
        limiter=RateLimiter(NO_LIMIT),
        retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0),
        max_workers=1,
        **kwargs,
    )


def test_registry_capabilities_and_permission() -> None:
    assert "eastmoney" in list_providers()
    row = {item["name"]: item for item in describe_providers()}["eastmoney"]
    assert row["capabilities"]["daily_bars"] is True
    assert row["capabilities"]["corporate_actions"] is True
    assert row["capabilities"]["realtime"] is False
    assert row["permission"]["requires_credentials"] is False
    assert row["quota"]["min_interval_seconds"] >= 0.3
    assert create_provider("eastmoney", allow_network=False).name == "eastmoney"


@pytest.mark.parametrize(
    ("code", "board", "secid"),
    [
        ("600000", "MAIN", "1.600000"),
        ("000001", "MAIN", "0.000001"),
        ("300750", "GEM", "0.300750"),
        ("688981", "STAR", "1.688981"),
        ("830799", "BSE", "0.830799"),
        ("430047", "BSE", "0.430047"),
        ("920000", "BSE", "0.920000"),
    ],
)
def test_board_inference_and_secid(code: str, board: str, secid: str) -> None:
    assert infer_board(code) == board
    assert secid_for_code(code) == secid
    assert secid_for_code("sh.600000") == "1.600000"


def test_concurrency_is_clamped_to_the_declared_quota() -> None:
    assert EastmoneyProvider(allow_network=False, max_workers=8).max_workers == 2


def test_universe_parsing_from_recorded_payload() -> None:
    payload = json.loads((FIXTURES / "universe.json").read_text(encoding="utf-8"))
    frame = normalize_eastmoney_universe(payload)
    assert len(frame) == 5
    assert frame.iloc[0]["code"] == "605599"
    assert frame.iloc[0]["sec_id"] == "SH.605599"
    assert frame.iloc[0]["board"] == "MAIN"
    assert int(frame.iloc[0]["list_date"]) == 20210909
    assert (frame["source"] == "EASTMONEY").all()


def test_security_master_pagination_codes_and_limit() -> None:
    provider = make_provider()
    master = provider.fetch_security_master()
    assert len(master) == 5
    assert [kind for kind, _ in provider._transport.requests] == ["clist", "clist"]
    only_one = make_provider(codes=["605599"]).fetch_security_master()
    assert only_one["code"].tolist() == ["605599"]
    limited = make_provider(limit=2).fetch_security_master()
    assert len(limited) == 2


def test_volume_lots_are_converted_to_shares() -> None:
    provider = make_provider()
    bars = provider.fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    assert len(bars) == 9
    first = bars.iloc[0]
    assert int(first["date"]) == 20261020
    assert int(first["volume"]) == 605133 * 100  # 手 -> 股
    assert float(first["amount"]) == pytest.approx(589321380.0)  # CNY as recorded
    assert float(first["open"]) == pytest.approx(9.79)
    assert float(first["close"]) == pytest.approx(9.76)
    assert first["source"] == "EASTMONEY"
    assert bars["date"].tolist() == sorted(bars["date"].tolist())
    # cross-check: amount / shares lands inside the day's range, proving the x100
    vwap = float(first["amount"]) / int(first["volume"])
    assert float(first["low"]) <= vwap <= float(first["high"])
    parsed = normalize_eastmoney_kline(
        json.loads((FIXTURES / "kline_1.600000_fqt0.json").read_text(encoding="utf-8")),
        "600000",
    )
    assert parsed["volume"].iloc[0] == 60513300
    assert parsed["pct_chg"].iloc[0] == pytest.approx(-0.002)


def test_calendar_from_derived_index_kline() -> None:
    provider = make_provider()
    calendar = provider.fetch_calendar("2026-10-20", "2026-10-31")
    assert len(calendar) == 9
    assert calendar.dates[0] == 20261020
    assert calendar.dates[-1] == 20261030
    assert any(kind == "index_kline" for kind, _ in provider._transport.requests)


def test_dividend_break_derivation_from_div_fixtures() -> None:
    provider = make_provider(tag="_div")
    bars = provider.fetch_daily_bars(["600000"], "2026-06-22", "2026-06-26")
    assert len(bars) == 5
    ex_row = bars[bars["date"] == 20260625].iloc[0]
    assert float(ex_row["pre_close"]) == pytest.approx(9.50)  # (10.00 - 0.50)
    assert float(ex_row["limit_up"]) == pytest.approx(10.45)
    assert float(ex_row["limit_down"]) == pytest.approx(8.55)
    factors = bars["adj_factor"].tolist()
    assert factors[:3] == pytest.approx([0.95, 0.95, 0.95])
    assert factors[3:] == pytest.approx([1.0, 1.0])
    actions = provider.fetch_corporate_actions(["600000"], "2026-06-22", "2026-06-26")
    assert len(actions) == 1
    action = actions.iloc[0]
    assert int(action["ex_date"]) == 20260625
    assert float(action["cash_per_share"]) == pytest.approx(0.50, abs=0.01)
    assert float(action["split_ratio"]) == 1.0
    assert action["source"] == "EASTMONEY_APPROX"


def test_gap_fixture_reports_missing_days() -> None:
    provider = make_provider(tag="_gap")
    bars = provider.fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    assert len(bars) == 7
    assert 20261022 not in bars["date"].tolist()
    assert 20261023 not in bars["date"].tolist()


def test_empty_data_fixture_returns_empty_canonical_frame() -> None:
    provider = make_provider()
    bars = provider.fetch_daily_bars(["601999"], "2026-10-20", "2026-10-30")
    assert bars.empty
    assert {"date", "sec_id", "open", "close", "volume", "limit_up"} <= set(bars.columns)


def test_error_payload_and_missing_fixture_raise_provider_error() -> None:
    with pytest.raises(ProviderError, match="rc=102"):
        make_provider(tag="_error").fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    with pytest.raises(ProviderError, match="fixture not found"):
        make_provider().fetch_daily_bars(["000001"], "2026-10-20", "2026-10-30")


def test_network_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QC_ALLOW_NETWORK", raising=False)
    provider = EastmoneyProvider(allow_network=False)
    with pytest.raises(ProviderPermissionError, match="QC_ALLOW_NETWORK"):
        provider.ensure_available()
    with pytest.raises(ProviderPermissionError):
        provider.fetch_calendar("2026-10-20", "2026-10-31")
    monkeypatch.setenv("QC_ALLOW_NETWORK", "1")
    provider.ensure_available()
    assert provider.allow_network is True


def test_turnover_from_kline_is_preserved() -> None:
    bars = make_provider().fetch_daily_bars(["600000"], "2026-10-20", "2026-10-30")
    assert float(bars.iloc[0]["turnover"]) == pytest.approx(0.0018)  # 0.18% as a fraction


def test_duplicate_kline_rows_are_deduplicated() -> None:
    payload = {
        "rc": 0,
        "data": {
            "code": "600000",
            "klines": [
                "2026-10-20,9.79,9.76,9.86,9.68,100,1000000.00,1.84,-0.20,-0.02,0.18",
                "2026-10-20,9.79,9.77,9.86,9.68,200,2000000.00,1.84,-0.19,-0.02,0.19",
                "2026-10-21,9.72,9.66,9.76,9.61,300,3000000.00,1.54,-1.02,-0.10,0.14",
            ],
        },
    }
    frame = normalize_eastmoney_kline(payload, "600000")
    assert frame["date"].tolist() == [20261020, 20261021]
    assert int(frame["volume"].iloc[0]) == 20000  # last duplicate wins, x100 shares
