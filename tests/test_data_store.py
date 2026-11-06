"""Warehouse (Parquet + DuckDB + SQLite), quality checks and ingest pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantcore.data.panel import (
    CORPORATE_ACTION_COLUMNS,
    FINANCIAL_COLUMNS,
    PanelData,
)
from quantcore.data.state import MIGRATIONS, SQLiteState
from quantcore.data.store import ParquetStore
from quantcore.ingest import ProviderIngestor
from quantcore.providers import SyntheticProvider
from quantcore.quality import quarantine_bad_rows, run_quality_checks


def test_parquet_roundtrip_and_manifest(warehouse: ParquetStore) -> None:
    frame = pd.DataFrame({"date": [20230103, 20230104, 20240102], "value": [1.0, 2.0, 3.0]})
    stats = warehouse.write_dataset("custom", frame)
    assert stats.rows == 3
    assert warehouse.list_datasets() == ["custom"]
    restored = warehouse.read_dataset("custom")
    assert restored.sort_values("date")["value"].tolist() == [1.0, 2.0, 3.0]
    problems = warehouse.verify()
    assert problems == []
    payload = json.loads(warehouse.manifest_path.read_text(encoding="utf-8"))
    assert "custom" in payload["datasets"]
    assert payload["datasets"]["custom"]["files"][0]["sha256"]


def test_parquet_write_is_idempotent(warehouse: ParquetStore) -> None:
    frame = pd.DataFrame({"date": [20230103, 20230104], "value": [1.0, 2.0]})
    first = warehouse.write_dataset("idem", frame)
    hash_one = warehouse.manifest_hash()
    second = warehouse.write_dataset("idem", frame)
    assert first.content_hash == second.content_hash
    assert warehouse.manifest_hash() == hash_one


def test_parquet_duckdb_query(warehouse: ParquetStore) -> None:
    frame = pd.DataFrame({"date": [20230103, 20230104, 20230105], "close": [10.0, 11.0, 12.0]})
    warehouse.write_dataset("bars", frame)
    result = warehouse.query("SELECT count(*) AS n, sum(close) AS total FROM bars")
    assert int(result.loc[0, "n"]) == 3
    assert float(result.loc[0, "total"]) == 33.0


def test_store_verify_detects_corruption(warehouse: ParquetStore) -> None:
    warehouse.write_dataset("bars", pd.DataFrame({"date": [20230103], "close": [10.0]}))
    path = next((warehouse.root / "dataset=bars").rglob("*.parquet"))
    path.write_bytes(path.read_bytes()[:-10])
    problems = warehouse.verify()
    assert problems


def test_store_reset(warehouse: ParquetStore) -> None:
    warehouse.write_dataset("bars", pd.DataFrame({"date": [20230103], "close": [1.0]}))
    warehouse.reset()
    assert warehouse.list_datasets() == []
    with pytest.raises(FileNotFoundError):
        warehouse.read_dataset("bars")


def test_replacing_panel_clears_optional_datasets(
    warehouse: ParquetStore, small_panel: PanelData
) -> None:
    warehouse.write_panel(small_panel)
    assert not warehouse.load_panel().financials.empty
    assert not warehouse.load_panel().corporate_actions.empty
    replacement = PanelData(
        calendar=small_panel.calendar,
        securities=small_panel.securities,
        bars=small_panel.bars,
        meta=small_panel.meta,
    )
    warehouse.write_panel(replacement)

    reopened = ParquetStore(warehouse.root)
    restored = reopened.load_panel()
    assert restored.financials.empty
    assert restored.corporate_actions.empty
    assert list(restored.financials.columns) == list(FINANCIAL_COLUMNS)
    assert list(restored.corporate_actions.columns) == list(CORPORATE_ACTION_COLUMNS)
    assert reopened.state.dataset_rows()["financials"] == 0
    assert reopened.state.dataset_rows()["corporate_actions"] == 0
    assert reopened.verify() == []


def test_sqlite_migrations_idempotent(tmp_path: Path) -> None:
    state = SQLiteState(tmp_path / "state.sqlite")
    assert state.current_version() == len(MIGRATIONS)
    assert state.migrate() == len(MIGRATIONS)
    state.set_meta("hello", {"a": 1})
    assert state.get_meta("hello") == {"a": 1}
    state.upsert_dataset("bars", "dataset=bars", 10, "abc", 20240101)
    assert state.dataset_rows() == {"bars": 10}
    assert state.watermark("bars") == 20240101


def test_sqlite_job_lifecycle(tmp_path: Path) -> None:
    state = SQLiteState(tmp_path / "state.sqlite")
    job_id = state.enqueue_job("backtest", {"template": "x"})
    job = state.get_job(job_id)
    assert job is not None and job["status"] == "pending"
    claimed = state.claim_job()
    assert claimed is not None and claimed["id"] == job_id
    assert state.claim_job() is None
    state.complete_job(job_id, {"ok": True})
    done = state.get_job(job_id)
    assert done is not None and done["status"] == "done"
    assert done["result"] == {"ok": True}
    other = state.enqueue_job("backtest", {})
    state.claim_job()
    state.fail_job(other, "boom")
    assert state.get_job(other)["status"] == "failed"
    assert state.recover_running_jobs() >= 0


def test_ingest_synthetic_panel(warehouse: ParquetStore) -> None:
    provider = SyntheticProvider()
    store = warehouse
    result = ProviderIngestor(provider, store).update("2023-01-03", "2023-12-29")
    assert result.quality_passed is True
    assert result.datasets["bars"] > 0
    assert result.synthetic is True
    panel = store.load_panel()
    assert panel.n_sec > 0
    report = run_quality_checks(panel)
    assert report.passed
    assert store.state.get_meta("last_ingest")["provider"] == "synthetic"


def test_ingest_incremental_is_idempotent(warehouse: ParquetStore) -> None:
    provider = SyntheticProvider()
    ingestor = ProviderIngestor(provider, warehouse)
    ingestor.update("2023-01-03", "2023-12-29")
    hash_before = warehouse.manifest_hash()
    second = ingestor.update("2023-01-03", "2023-12-29")
    assert second.quality["note"] == "no new trading days"
    assert second.manifest_hash == hash_before
    assert warehouse.manifest_hash() == hash_before


def test_quality_detects_injected_problems(small_panel: PanelData) -> None:
    bars = small_panel.bars.copy()
    duplicate = bars.iloc[[0]].copy()
    bad = bars.iloc[[1]].copy()
    bad["high"] = bad["low"] - 1.0
    bad["close"] = -5.0
    tampered = pd.concat([bars, duplicate, bad], ignore_index=True)
    panel = PanelData(
        calendar=small_panel.calendar,
        securities=small_panel.securities,
        bars=tampered,
        financials=small_panel.financials,
        corporate_actions=small_panel.corporate_actions,
        meta=dict(small_panel.meta),
    )
    report = run_quality_checks(panel)
    assert not report.passed
    check_names = {issue.check for issue in report.errors}
    assert "duplicates" in check_names or "price_consistency" in check_names
    result = quarantine_bad_rows(panel)
    assert result.dropped == 2  # one duplicate + one invalid OHLC/price row
    assert len(result.clean.bars) == len(tampered) - 2
    assert not result.bad_rows.empty


def test_quality_clean_panel_passes(small_panel: PanelData) -> None:
    report = run_quality_checks(small_panel)
    assert report.passed
    assert report.to_dict()["error_count"] == 0
