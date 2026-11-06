"""Network acquisition and checkpoint replay produce the same causal sample."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from quantcore.data.store import ParquetStore


@pytest.fixture()
def sample(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("scripts.fetch_research_sample")
    monkeypatch.setattr(module.signal, "alarm", lambda _: None)
    monkeypatch.setattr(module.signal, "signal", lambda *_: None)
    monkeypatch.setattr(
        module,
        "SinaProvider",
        lambda **_: SimpleNamespace(limiter=SimpleNamespace(acquire=lambda: None)),
    )
    monkeypatch.setattr(
        module,
        "parse_sina_payload",
        lambda _: [SimpleNamespace(code=code, name="Sample") for code in module.CODES],
    )
    return module


def install_fake_transport(sample, monkeypatch):
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    closes, offsets = [10.0, 10.0, 9.5, 9.6], [0.5, 0.5, 0.0, 0.0]
    calls = []

    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, url, *, params, headers):
            calls.append(dict(params))
            if "param" in params:
                symbol = params["param"].split(",")[0]
                rows = [
                    [
                        day,
                        f"{c - d:.3f}",
                        f"{c - d:.3f}",
                        f"{c + 0.02 - d:.3f}",
                        f"{c - 0.02 - d:.3f}",
                        "1000",
                    ]
                    for day, c, d in zip(dates, closes, offsets, strict=True)
                ]
                payload = {"data": {symbol: {"qfqday": rows}}}
            elif "symbol" in params:
                payload = [
                    {
                        "day": day,
                        "open": c,
                        "high": c + 0.02,
                        "low": c - 0.02,
                        "close": c,
                        "volume": 1000000,
                    }
                    for day, c in zip(dates, closes, strict=True)
                ]
            else:
                payload = "recorded quote fixture"
            return SimpleNamespace(
                content=json.dumps(payload).encode(), raise_for_status=lambda: None
            )

    monkeypatch.setattr(sample.httpx, "AsyncClient", Client)
    return calls


def invoke(sample, monkeypatch, output, mode, *, start="2024-01-02"):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_research_sample.py",
            mode,
            "--output",
            str(output),
            "--start",
            start,
            "--end",
            "2024-01-05",
        ],
    )
    sample.main()


def test_download_is_causal_and_offline_finalization_is_identical(sample, monkeypatch, tmp_path):
    calls = install_fake_transport(sample, monkeypatch)
    invoke(sample, monkeypatch, tmp_path, "--allow-network")
    store = ParquetStore(tmp_path / "warehouse")
    downloaded = store.load_panel()
    first_hash = downloaded.content_hash()
    assert len(calls) == 18  # quote + eight raw/qfq pairs + calendar
    assert downloaded.meta["signal_adjustment"] == "causal_ex_date_events"
    assert downloaded.meta["raw_requested_start"] == "2024-01-02"
    assert len(downloaded.corporate_actions) == 8
    close = downloaded.matrix("close")
    factor = downloaded.matrix("adj_factor")
    np.testing.assert_array_equal(factor[:2], np.ones((2, 8)))
    np.testing.assert_allclose(factor[2:], np.full((2, 8), 10 / 9.5))
    np.testing.assert_allclose((close * factor)[:3], np.full((3, 8), 10.0))

    def reject_network(**_):
        raise AssertionError("offline finalization attempted a network request")

    monkeypatch.setattr(sample.httpx, "AsyncClient", reject_network)
    invoke(sample, monkeypatch, tmp_path, "--finalize-offline")
    rebuilt = ParquetStore(tmp_path / "warehouse").load_panel()
    assert rebuilt.content_hash() == first_hash
    np.testing.assert_array_equal(rebuilt.matrix("adj_factor"), factor)


@pytest.mark.parametrize(
    "changed",
    [
        {"source": "OTHER"},
        {"curated_sample": False},
        {"raw_requested_start": "2000-01-01"},
        {"signal_adjustment": "vendor_qfq"},
    ],
)
def test_offline_refuses_a_different_warehouse(sample, monkeypatch, tmp_path, changed):
    install_fake_transport(sample, monkeypatch)
    invoke(sample, monkeypatch, tmp_path, "--allow-network")
    manifest = tmp_path / "warehouse/warehouse_manifest.json"
    payload = json.loads(manifest.read_text())
    payload["metadata"]["panel_meta"].update(changed)
    manifest.write_text(json.dumps(payload))
    before = manifest.read_bytes()
    with pytest.raises(SystemExit, match="2"):
        invoke(sample, monkeypatch, tmp_path, "--finalize-offline")
    assert manifest.read_bytes() == before


def test_different_requested_window_and_redownload_cannot_replace_sample(
    sample, monkeypatch, tmp_path
):
    install_fake_transport(sample, monkeypatch)
    invoke(sample, monkeypatch, tmp_path, "--allow-network")
    manifest = tmp_path / "warehouse/warehouse_manifest.json"
    before = manifest.read_bytes()
    for mode, start in [("--allow-network", "2024-01-02"), ("--finalize-offline", "2024-01-03")]:
        with pytest.raises(SystemExit, match="2"):
            invoke(sample, monkeypatch, tmp_path, mode, start=start)
        assert manifest.read_bytes() == before
