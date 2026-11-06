"""Data identities and provenance remain consistent across local entry points."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from quantcore.cli import app
from quantcore.data.panel import CORPORATE_ACTION_COLUMNS, FINANCIAL_COLUMNS, PanelData
from quantcore.data.state import SQLiteState
from quantcore.data.store import ParquetStore
from quantcore.errors import ProviderError
from quantcore.ingest import ProviderIngestor
from quantcore.providers.localfile import LocalFileProvider
from quantcore.server.runner import run_data_update_job, run_snapshot_job
from quantcore.snapshot import load_snapshot


def _synthetic_payload(root: Path) -> dict:
    return {
        "data_root": str(root),
        "provider": "synthetic",
        "n_sec": 3,
        "start": "2023-01-03",
        "end": "2023-12-29",
        "seed": 42,
    }


@pytest.mark.parametrize("change", [{"provider": "local"}, {"seed": 43}, {"n_sec": 4}])
def test_incremental_rejects_different_source_identity(tmp_path: Path, change: dict) -> None:
    payload = _synthetic_payload(tmp_path)
    run_data_update_job(payload)
    store = ParquetStore(tmp_path / "warehouse")
    before = store.manifest_hash()
    if change.get("provider") == "local":
        source = tmp_path / "local"
        source.mkdir()
        for name in ("calendar", "securities", "bars"):
            store.read_dataset(name).to_parquet(source / f"{name}.parquet", index=False)
        change = {**change, "local_dir": str(source)}
    with pytest.raises(ProviderError, match=r"reset|non-incremental"):
        run_data_update_job({**payload, **change})
    assert ParquetStore(tmp_path / "warehouse").manifest_hash() == before


def test_incremental_rejects_expanded_codes(tmp_path: Path, monkeypatch) -> None:
    from quantcore.providers.base import ProviderQuota
    from quantcore.providers.tushare import TushareProvider
    from tests.test_tushare_live import _install_fake

    _install_fake(monkeypatch, [])
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")
    monkeypatch.setenv("QC_ALLOW_NETWORK", "1")
    monkeypatch.setattr(TushareProvider, "quota", ProviderQuota(max_calls=10000, window_seconds=1))
    payload = {
        "data_root": str(tmp_path),
        "provider": "tushare",
        "start": "2023-01-03",
        "end": "2023-01-03",
        "codes": ["600000.SH"],
    }
    run_data_update_job(payload)
    with pytest.raises(ProviderError, match=r"reset|non-incremental"):
        run_data_update_job({**payload, "codes": ["600000.SH", "000001.SZ"]})
    bars = ParquetStore(tmp_path / "warehouse").read_dataset("bars")
    assert bars["code"].tolist() == ["600000"]


@pytest.mark.parametrize("import_entry", ["cli", "job"])
def test_cross_entry_snapshot_preserves_synthetic_provenance(
    tmp_path: Path, import_entry: str
) -> None:
    args = ["--data-root", str(tmp_path)]
    if import_entry == "cli":
        result = CliRunner().invoke(
            app,
            [
                "data",
                "update",
                *args,
                "--n-sec",
                "3",
                "--start",
                "2023-01-03",
                "--end",
                "2023-12-29",
            ],
        )
        assert result.exit_code == 0, (result.output, result.exception)
        output = run_snapshot_job({"data_root": str(tmp_path)})
    else:
        run_data_update_job(_synthetic_payload(tmp_path))
        result = CliRunner().invoke(
            app,
            [
                "snapshot",
                "build",
                *args,
                "--snapshots-root",
                str(tmp_path / "snapshots"),
            ],
        )
        assert result.exit_code == 0, (result.output, result.exception)
        output = json.loads(result.stdout)
    snapshot = load_snapshot(tmp_path / "snapshots", output["snapshot_id"])
    assert snapshot.synthetic is True
    assert snapshot.manifest.provider == "synthetic"
    assert snapshot.manifest.source == "SYNTHETIC"
    assert snapshot.manifest.disclaimer
    status = CliRunner().invoke(app, ["data", "status", *args])
    assert status.exit_code == 0, (status.output, status.exception)
    assert json.loads(status.stdout)["last_ingest"]["synthetic"] is True


def test_local_optional_datasets_can_be_absent(tmp_path: Path, small_panel: PanelData) -> None:
    source = tmp_path / "local"
    source.mkdir()
    frames = {
        "calendar": pd.DataFrame({"date": small_panel.calendar.dates}),
        "securities": small_panel.securities,
        "bars": small_panel.bars,
    }
    for name, frame in frames.items():
        frame.to_parquet(source / f"{name}.parquet", index=False)
    store = ParquetStore(tmp_path / "warehouse")
    result = ProviderIngestor(LocalFileProvider(source), store).update(20220104, 20241231)
    assert result.quality_passed
    panel = store.load_panel()
    assert panel.financials.empty and list(panel.financials) == list(FINANCIAL_COLUMNS)
    assert panel.corporate_actions.empty and list(panel.corporate_actions) == list(
        CORPORATE_ACTION_COLUMNS
    )


def test_quality_failure_keeps_previous_warehouse_and_ingest(tmp_path: Path) -> None:
    payload = _synthetic_payload(tmp_path)
    run_data_update_job(payload)
    state = SQLiteState(tmp_path / "state.sqlite")
    store = ParquetStore(tmp_path / "warehouse", state=state)
    before = store.manifest_hash()
    last_ingest = state.get_meta("last_ingest")
    source = tmp_path / "local"
    source.mkdir()
    for name in ("calendar", "securities", "bars", "financials", "corporate_actions"):
        frame = store.read_dataset(name)
        if name == "bars":
            frame.loc[0, "close"] = -1
        elif name == "financials":
            frame["ann_date"] = frame["end_date"] - 1
        frame.to_parquet(source / f"{name}.parquet", index=False)
    with pytest.raises(ValueError, match="quality checks failed"):
        run_data_update_job(
            {**payload, "provider": "local", "local_dir": str(source), "reset": True}
        )
    restored = ParquetStore(tmp_path / "warehouse", state=state)
    assert restored.manifest_hash() == before
    assert state.get_meta("last_ingest") == last_ingest
    assert "quarantine" not in restored.list_datasets()


@pytest.mark.parametrize("replacement", [{"reset": True}, {"incremental": False}])
def test_explicit_replacement_accepts_new_identity(tmp_path: Path, replacement: dict) -> None:
    payload = _synthetic_payload(tmp_path)
    run_data_update_job(payload)
    result = run_data_update_job({**payload, **replacement, "seed": 43, "n_sec": 4})
    assert result["quality_passed"]
    store = ParquetStore(tmp_path / "warehouse")
    assert store.load_panel().n_sec == 4
    assert store.load_panel().meta["seed"] == 43


def test_local_time_extension_keeps_same_identity(tmp_path: Path, small_panel: PanelData) -> None:
    source = tmp_path / "local"
    source.mkdir()
    for name, frame in {
        "calendar": pd.DataFrame({"date": small_panel.calendar.dates}),
        "securities": small_panel.securities,
        "bars": small_panel.bars,
    }.items():
        frame.to_parquet(source / f"{name}.parquet", index=False)
    store = ParquetStore(tmp_path / "warehouse")
    ProviderIngestor(LocalFileProvider(source), store).update(20220104, 20220630)
    identity = store.get_metadata("ingest_identity")
    result = ProviderIngestor(LocalFileProvider(source), store).update(20220104, 20221230)
    assert result.quality_passed
    assert store.read_dataset("bars")["date"].max() == 20221230
    assert store.get_metadata("ingest_identity") == identity


def test_legacy_metadata_only_migrates_matching_warehouse(
    tmp_path: Path, small_panel: PanelData
) -> None:
    root = tmp_path / "warehouse"
    legacy = SQLiteState(root / "state.sqlite")
    store = ParquetStore(root, state=legacy)
    store.write_panel(small_panel)
    job = legacy.enqueue_job("data_update", {"marker": "legacy-job"})
    payload = json.loads(store.manifest_path.read_text())
    payload.pop("metadata")  # Simulate the pre-metadata manifest schema.
    store.manifest_path.write_text(json.dumps(payload))
    application = SQLiteState(tmp_path / "custom-application.sqlite")
    restored = ParquetStore(root, state=application)
    assert restored.load_panel().meta == json.loads(json.dumps(small_panel.meta))
    assert application.get_job(job) is None
    assert legacy.get_job(job) is not None

    from quantcore.data.synthetic import SyntheticConfig
    from quantcore.providers.synthetic import SyntheticProvider

    provider = SyntheticProvider(SyntheticConfig(**small_panel.meta["config"]))
    unchanged = ProviderIngestor(provider, restored).update(20220104, 20241231)
    assert unchanged.quality["note"] == "no new trading days"
    assert restored.get_metadata("ingest_identity")["options"]["seed"] == 11

    other = ParquetStore(tmp_path / "other-warehouse", state=application)
    other.write_panel(
        PanelData(
            calendar=small_panel.calendar,
            securities=small_panel.securities,
            bars=small_panel.bars,
            meta={**small_panel.meta, "seed": 999},
        )
    )
    # Same bar contents in another warehouse must not override the original metadata.
    assert ParquetStore(root, state=application).load_panel().meta["seed"] == 11


def test_legacy_synthetic_bars_remain_labelled_without_state(
    tmp_path: Path, small_panel: PanelData
) -> None:
    store = ParquetStore(tmp_path / "warehouse")
    store.write_panel(small_panel)
    payload = json.loads(store.manifest_path.read_text())
    payload.pop("metadata")
    store.manifest_path.write_text(json.dumps(payload))
    with store.state.connect() as connection:
        connection.execute("DELETE FROM meta")
        connection.commit()
    panel = ParquetStore(store.root).load_panel()
    assert panel.meta["synthetic"] is True
    assert panel.meta["source"] == "SYNTHETIC"
    assert panel.meta["disclaimer"]


def test_local_reimport_keeps_synthetic_provenance(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    run_data_update_job(_synthetic_payload(generated))
    original = ParquetStore(generated / "warehouse")
    source = tmp_path / "local"
    source.mkdir()
    for name in ("calendar", "securities", "bars", "financials", "corporate_actions"):
        original.read_dataset(name).to_parquet(source / f"{name}.parquet", index=False)
    imported = tmp_path / "imported"
    payload = {
        **_synthetic_payload(imported),
        "provider": "local",
        "local_dir": str(source),
    }
    result = run_data_update_job(payload)
    assert result["synthetic"] is True
    assert run_data_update_job(payload)["synthetic"] is True  # no new trading days
    store = ParquetStore(imported / "warehouse")
    panel = store.load_panel()
    assert panel.meta["provider"] == "local"
    assert panel.meta["synthetic"] is True
    assert panel.meta["source"] == "SYNTHETIC"
    assert "SYNTHETIC" in panel.meta["disclaimer"]
    assert store.get_metadata("last_ingest")["synthetic"] is True
    output = run_snapshot_job({"data_root": str(imported)})
    snapshot = load_snapshot(imported / "snapshots", output["snapshot_id"])
    assert snapshot.synthetic is True
    assert snapshot.manifest.provider == "local"
    assert snapshot.manifest.source == "SYNTHETIC"


def test_legacy_local_metadata_cannot_hide_synthetic_bars(
    tmp_path: Path, small_panel: PanelData
) -> None:
    store = ParquetStore(tmp_path / "warehouse")
    store.write_panel(small_panel)
    store.set_metadata("panel_meta", {"provider": "local", "source": "LOCAL", "synthetic": False})
    panel = ParquetStore(store.root).load_panel()
    assert panel.meta["provider"] == "local"
    assert panel.meta["source"] == "SYNTHETIC"
    assert panel.meta["synthetic"] is True
    assert "SYNTHETIC" in panel.meta["disclaimer"]
