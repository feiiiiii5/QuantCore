"""Tushare fixture imports use the same code filters as the live adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quantcore.cli import app
from quantcore.data.store import ParquetStore
from quantcore.providers import TushareProvider
from tests.test_providers import _tushare_fixtures


@pytest.fixture
def tushare_fixture_dir(tmp_path: Path) -> Path:
    root = tmp_path / "tushare"
    _tushare_fixtures(root)
    for dataset in ("securities", "daily_bars", "financials", "corporate_actions"):
        path = root / f"{dataset}.json"
        rows = json.loads(path.read_text())
        extra = [{**row, "ts_code": "600000.SH"} for row in rows]
        if dataset == "securities":
            for row in extra:
                row.update(symbol="600000", name="fixture second security")
        path.write_text(json.dumps([*rows, *extra]))
    return root


@pytest.mark.parametrize("code", ["000001", "000001.SZ", "SZ.000001"])
def test_fixture_filters_all_canonical_tables(tushare_fixture_dir: Path, code: str) -> None:
    provider = TushareProvider(fixture_dir=tushare_fixture_dir)
    for fetch in (
        provider.fetch_daily_bars,
        provider.fetch_financials,
        provider.fetch_corporate_actions,
    ):
        frame = fetch([code], 20230101, 20231231)
        assert not frame.empty
        assert set(frame["sec_id"]) == {"SZ.000001"}


def test_fixture_filter_preserves_date_windows_and_empty_selections(
    tushare_fixture_dir: Path,
) -> None:
    provider = TushareProvider(fixture_dir=tushare_fixture_dir)
    for fetch in (
        provider.fetch_daily_bars,
        provider.fetch_financials,
        provider.fetch_corporate_actions,
    ):
        assert fetch([], 20230101, 20231231).empty
        assert fetch(["000001.SZ"], 20240101, 20241231).empty
        assert set(fetch(None, 20230101, 20231231)["sec_id"]) == {"SZ.000001", "SH.600000"}
    financials = provider.fetch_financials(["000001.SZ"], 20230301, 20230531)
    assert financials["ann_date"].tolist() == [20230315]


@pytest.mark.parametrize("code", ["000001", "000001.SZ", "SZ.000001"])
def test_cli_imports_filtered_fixture_files_offline(
    tmp_path: Path, tushare_fixture_dir: Path, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QC_ALLOW_NETWORK", "0")
    data_root = tmp_path / "data"
    result = CliRunner().invoke(
        app,
        [
            "data",
            "update",
            "--provider",
            "tushare",
            "--fixture-dir",
            str(tushare_fixture_dir),
            "--codes",
            code,
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--data-root",
            str(data_root),
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert json.loads(result.stdout)["quality_passed"] is True
    store = ParquetStore(data_root / "warehouse")
    for dataset in ("bars", "financials", "corporate_actions"):
        assert set(store.read_dataset(dataset)["sec_id"]) == {"SZ.000001"}
