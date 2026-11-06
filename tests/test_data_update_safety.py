"""Replacement imports preserve the last usable warehouse until data is ready."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from quantcore.cli import app
from quantcore.data.store import ParquetStore
from quantcore.errors import ProviderError
from quantcore.server.runner import run_data_update_job


@pytest.mark.parametrize("entry", ["cli", "job"])
@pytest.mark.parametrize("failure", ["arguments", "fetch", "dates"])
def test_failed_replacement_preserves_existing_data(
    tmp_path: Path, entry: str, failure: str
) -> None:
    data_root = tmp_path / "data"
    store = ParquetStore(data_root / "warehouse")
    original = pd.DataFrame({"date": [20230103], "close": [12.34]})
    store.write_dataset("bars", original)
    manifest = store.manifest_hash()
    payload = {"data_root": str(data_root), "reset": True, "provider": "local"}
    args = ["data", "update", "--data-root", str(data_root), "--reset", "--provider", "local"]
    if failure == "fetch":
        payload["local_dir"] = str(tmp_path / "missing")
        args += ["--local-dir", str(tmp_path / "missing")]
    elif failure == "dates":
        payload.update(provider="synthetic", start="2024-02-01", end="2024-01-01")
        args = [*args[:-1], "synthetic", "--start", "2024-02-01", "--end", "2024-01-01"]
    if entry == "cli":
        assert CliRunner().invoke(app, args).exit_code != 0
    else:
        with pytest.raises((ValueError, FileNotFoundError, ProviderError)):
            run_data_update_job(payload)
    restored = ParquetStore(data_root / "warehouse")
    assert restored.manifest_hash() == manifest
    pd.testing.assert_frame_equal(restored.read_dataset("bars"), original)


@pytest.mark.parametrize("entry", ["cli", "job"])
def test_replacement_ignores_old_incremental_watermark(tmp_path: Path, entry: str) -> None:
    data_root = tmp_path / "data"
    store = ParquetStore(data_root / "warehouse")
    store.write_dataset("bars", pd.DataFrame({"date": [20250101], "close": [12.34]}))
    payload = {
        "data_root": str(data_root),
        "reset": True,
        "provider": "synthetic",
        "start": "2023-01-03",
        "end": "2023-12-29",
        "n_sec": 3,
    }
    if entry == "cli":
        result = CliRunner().invoke(
            app,
            [
                "data",
                "update",
                "--data-root",
                str(data_root),
                "--reset",
                "--start",
                "2023-01-03",
                "--end",
                "2023-12-29",
                "--n-sec",
                "3",
            ],
        )
        assert result.exit_code == 0, (result.output, result.exception)
        output = json.loads(result.stdout)
    else:
        output = run_data_update_job(payload)
    assert output["quality_passed"]
    bars = ParquetStore(data_root / "warehouse").read_dataset("bars")
    assert bars["date"].max() <= 20231229
    assert bars["sec_id"].nunique() == 3


@pytest.mark.parametrize("entry", ["cli_flag", "cli_env", "job"])
def test_tushare_network_opt_in_reaches_real_adapter(
    tmp_path: Path, monkeypatch, entry: str
) -> None:
    from quantcore.providers.base import ProviderQuota
    from quantcore.providers.tushare import TushareProvider
    from tests.test_tushare_live import _install_fake

    calls = []
    _install_fake(monkeypatch, calls)
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")
    monkeypatch.setenv("QC_ALLOW_NETWORK", "1" if entry != "cli_flag" else "0")
    monkeypatch.setattr(TushareProvider, "quota", ProviderQuota(max_calls=10000, window_seconds=1))
    payload = {
        "data_root": str(tmp_path),
        "provider": "tushare",
        "start": "2023-01-01",
        "end": "2023-01-31",
        "codes": ["600000.SH", "000001.SZ"],
    }
    if entry.startswith("cli"):
        args = [
            "data",
            "update",
            "--provider",
            "tushare",
            "--data-root",
            str(tmp_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-31",
            "--codes",
            "600000.SH,000001.SZ",
        ]
        if entry == "cli_flag":
            args.append("--allow-network")
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, (result.output, result.exception)
    else:
        run_data_update_job(payload)
    assert {name for name, _ in calls} >= {"daily", "adj_factor", "stock_basic"}
    assert ParquetStore(tmp_path / "warehouse").read_dataset("bars")["close"].tolist() == [
        10.2,
        10.2,
    ]
