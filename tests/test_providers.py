"""Provider contract tests: capabilities, rate limits, fixtures and lazy adapters."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quantcore.data.synthetic import SyntheticConfig
from quantcore.errors import ProviderError, ProviderPermissionError, ProviderUnavailableError
from quantcore.providers import (
    LocalFileProvider,
    MootdxProvider,
    SyntheticProvider,
    TushareProvider,
    create_provider,
    describe_providers,
    list_providers,
)
from quantcore.providers.akshare import AKShareProvider, normalize_akshare_daily
from quantcore.providers.base import (
    ProviderQuota,
    RateLimiter,
    RetryPolicy,
    retry_call,
)


def test_registry_and_capabilities() -> None:
    assert set(list_providers()) >= {"synthetic", "local", "tushare", "akshare", "mootdx"}
    providers = {item["name"]: item for item in describe_providers()}
    assert providers["synthetic"]["capabilities"]["financials"] is True
    assert providers["tushare"]["permission"]["requires_credentials"] is True
    with pytest.raises(ProviderUnavailableError):
        create_provider("nope")


def test_synthetic_provider() -> None:
    provider = SyntheticProvider(
        SyntheticConfig(n_sec=10, start="2023-01-03", end="2023-12-29", seed=2)
    )
    assert provider.supports("daily_bars")
    calendar = provider.fetch_calendar("2023-01-03", "2023-12-29")
    assert len(calendar) > 200
    master = provider.fetch_security_master()
    assert len(master) == 10
    bars = provider.fetch_daily_bars(None, "2023-01-03", "2023-03-31")
    assert {"date", "sec_id", "close", "limit_up"} <= set(bars.columns)
    financials = provider.fetch_financials(None, "2023-01-03", "2023-12-29")
    assert not financials.empty
    panel = provider.fetch_panel("2023-01-03", "2023-12-29", codes=[master.iloc[0]["sec_id"]])
    assert panel.n_sec == 1
    assert panel.meta["synthetic"] is True


def test_rate_limiter_window_and_daily_limit() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(
        ProviderQuota(max_calls=2, window_seconds=10.0, daily_call_limit=3),
        clock=clock,
        sleeper=sleeper,
    )
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()  # forces a window wait
    assert sleeps and sleeps[0] == pytest.approx(10.0)
    with pytest.raises(ProviderError):
        limiter.acquire()
        limiter.acquire()


def test_retry_policy_backoff() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderUnavailableError("transient")
        return 42

    result = retry_call(
        flaky,
        RetryPolicy(attempts=4, base_delay=1.0, max_delay=10.0),
        sleeper=sleeps.append,
    )
    assert result == 42
    assert sleeps == [1.0, 2.0]


def test_local_file_provider_csv_mapping(tmp_path: Path) -> None:
    data = tmp_path / "local"
    data.mkdir()
    calendar = pd.DataFrame({"trade_date": [20230103, 20230104, 20230105]})
    calendar.to_csv(data / "calendar.csv", index=False)
    securities = pd.DataFrame(
        {
            "sec_id": ["S1"],
            "code": ["000001"],
            "exchange": ["SZ"],
            "name": ["测试"],
            "board": ["MAIN"],
            "list_date": [20220103],
            "delist_date": [0],
        }
    )
    securities.to_csv(data / "securities.csv", index=False)
    bars = pd.DataFrame(
        {
            "trade_date": [20230103, 20230104],
            "sec_id": ["S1", "S1"],
            "open": [10.0, 10.2],
            "high": [10.5, 10.4],
            "low": [9.9, 10.0],
            "close": [10.2, 10.1],
            "pre_close": [10.0, 10.2],
            "volume": [100000, 120000],
            "amount": [1020000.0, 1212000.0],
            "adj_factor": [1.0, 1.0],
            "limit_up": [11.0, 11.22],
            "limit_down": [9.0, 9.18],
            "suspended": [False, False],
            "st": [False, False],
        }
    )
    bars.to_csv(data / "bars.csv", index=False)
    provider = LocalFileProvider(
        data,
        column_mapping={"calendar": {"date": "trade_date"}, "bars": {"date": "trade_date"}},
    )
    provider.ensure_available()
    calendar_result = provider.fetch_calendar("2023-01-01", "2023-12-31")
    assert list(calendar_result.dates) == [20230103, 20230104, 20230105]
    frames = provider.fetch_daily_bars(["S1"], "2023-01-01", "2023-12-31")
    assert len(frames) == 2
    assert frames["date"].tolist() == [20230103, 20230104]
    assert "source" in frames.columns


def test_local_file_provider_missing_data(tmp_path: Path) -> None:
    provider = LocalFileProvider(tmp_path / "empty")
    with pytest.raises(ProviderUnavailableError):
        provider.ensure_available()


def _tushare_fixtures(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [20230103, 20230104, 20230105]}).to_json(
        directory / "calendar.json", orient="records"
    )
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "area": "深圳",
                "industry": "银行",
                "market": "主板",
                "list_date": 19910403,
            }
        ]
    ).to_json(directory / "securities.json", orient="records")
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": 20230103,
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "pre_close": 10.0,
                "vol": 1000.0,
                "amount": 1020.0,
                "adj_factor": 1.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": 20230104,
                "open": 10.2,
                "high": 10.6,
                "low": 10.0,
                "close": 10.4,
                "pre_close": 10.2,
                "vol": 1200.0,
                "amount": 1248.0,
                "adj_factor": 1.0,
                "up_limit": 11.22,
                "down_limit": 9.18,
            },
        ]
    ).to_json(directory / "daily_bars.json", orient="records")
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "end_date": 20221231,
                "ann_date": 20230315,
                "f_ann_date": 20230315,
                "report_type": "1",
                "update_flag": "1",
                "revenue": 1.0e9,
                "n_income": 2.0e8,
                "total_assets": 5.0e9,
                "total_hldr_eqy_exc_min_int": 3.0e9,
                "roe": 0.12,
                "eps": 1.5,
                "bps": 15.0,
            }
        ]
    ).to_json(directory / "financials.json", orient="records")
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "ann_date": 20230601,
                "record_date": 20230620,
                "ex_date": 20230621,
                "pay_date": 20230622,
                "cash_div_tax": 0.5,
                "stk_div": 0.0,
            }
        ]
    ).to_json(directory / "corporate_actions.json", orient="records")


def test_tushare_fixture_provider(tmp_path: Path) -> None:
    fixtures = tmp_path / "tushare"
    _tushare_fixtures(fixtures)
    provider = TushareProvider(fixture_dir=fixtures)
    provider.ensure_available()
    calendar = provider.fetch_calendar("2023-01-01", "2023-01-31")
    assert len(calendar) == 3
    bars = provider.fetch_daily_bars(None, "2023-01-01", "2023-01-31")
    assert bars["date"].tolist() == [20230103, 20230104]
    assert bars["volume"].tolist() == [100_000, 120_000]  # lots -> shares
    assert bars["amount"].tolist() == [1_020_000.0, 1_248_000.0]  # thousand CNY -> CNY
    assert set(bars["sec_id"]) == {"SZ.000001"}
    financials = provider.fetch_financials(None, "2023-01-01", "2023-12-31")
    assert financials["net_profit"].tolist() == [2.0e8]
    actions = provider.fetch_corporate_actions(None, "2023-01-01", "2023-12-31")
    assert actions["cash_per_share"].tolist() == [0.5]


def test_tushare_live_requires_opt_in() -> None:
    provider = TushareProvider()
    with pytest.raises(ProviderPermissionError):
        provider.ensure_available()
    with pytest.raises(ProviderPermissionError):
        provider.fetch_daily_bars(["000001.SZ"], "2023-01-01", "2023-01-31")


@pytest.mark.network
def test_tushare_network_smoke() -> None:
    import os

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        pytest.skip("TUSHARE_TOKEN not set")
    provider = TushareProvider(allow_network=True, token=token)
    calendar = provider.fetch_calendar("2024-01-01", "2024-01-31")
    assert len(calendar) > 10


def test_akshare_contract_with_fake_module() -> None:
    frames = pd.DataFrame(
        {
            "日期": ["2023-01-03", "2023-01-04"],
            "开盘": [10.0, 10.2],
            "收盘": [10.2, 10.4],
            "最高": [10.5, 10.6],
            "最低": [9.9, 10.0],
            "成交量": [1000, 1200],
            "成交额": [1_020_000.0, 1_248_000.0],
            "换手率": [1.2, 1.4],
        }
    )

    class FakeAkshare:
        @staticmethod
        def stock_zh_a_hist(**kwargs: Any) -> pd.DataFrame:
            assert kwargs["symbol"] == "000001"
            return frames

    provider = AKShareProvider(module=FakeAkshare())
    bars = provider.fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")
    assert len(bars) == 2
    assert bars["sec_id"].tolist() == ["SZ.000001"] * 2
    assert bars["volume"].tolist() == [100_000, 120_000]
    assert bars["limit_up"].notna().all()
    normalized = normalize_akshare_daily(frames, "600000")
    assert normalized["sec_id"].tolist() == ["SH.600000"] * 2


def test_akshare_lazy_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "akshare", None)
    provider = AKShareProvider(allow_network=True)
    with pytest.raises(ProviderUnavailableError):
        provider.fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")
    with pytest.raises(ProviderPermissionError):
        AKShareProvider().fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")


def test_mootdx_contract_with_fake_module() -> None:
    class FakeClient:
        def bars(self, symbol: str, frequency: int, offset: int) -> pd.DataFrame:
            assert frequency == 9
            return pd.DataFrame(
                {
                    "datetime": ["2023-01-03", "2023-01-04"],
                    "open": [10.0, 10.2],
                    "high": [10.5, 10.6],
                    "low": [9.9, 10.0],
                    "close": [10.2, 10.4],
                    "vol": [1000, 1200],
                    "amount": [1_020_000.0, 1_248_000.0],
                }
            )

    class FakeQuotes:
        @staticmethod
        def factory(market: str) -> FakeClient:
            assert market == "std"
            return FakeClient()

    class FakeMootdx:
        Quotes = FakeQuotes

    provider = MootdxProvider(module=FakeMootdx())
    bars = provider.fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")
    assert len(bars) == 2
    assert bars["volume"].tolist() == [100_000, 120_000]
    assert bars["close"].tolist() == [10.2, 10.4]


def test_mootdx_lazy_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "mootdx", None)
    monkeypatch.setitem(sys.modules, "mootdx.quotes", None)
    with pytest.raises(ProviderPermissionError):
        MootdxProvider().fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")
    provider = MootdxProvider(allow_network=True)
    with pytest.raises(ProviderUnavailableError):
        provider.fetch_daily_bars(["000001"], "2023-01-01", "2023-12-31")


def test_provider_tushare_permission_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from quantcore.providers.tushare import TUSHARE_PERMISSION

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    assert not TUSHARE_PERMISSION.credentials_present()
    monkeypatch.setenv("TUSHARE_TOKEN", "abc")
    assert TUSHARE_PERMISSION.credentials_present()
    assert TUSHARE_PERMISSION.resolve_credential() == "abc"
