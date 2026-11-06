"""An existing immutable snapshot can acquire or repair its native sidecar."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from quantcore import CppUnavailableError, panel_available
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
from quantcore.errors import SnapshotError
from quantcore.snapshot import build_snapshot, load_snapshot


@pytest.fixture(scope="module")
def panel():
    return generate_synthetic_panel(
        SyntheticConfig(n_sec=3, start="2023-01-03", end="2023-12-29", seed=23)
    )


def without_native(panel, tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr("quantcore.snapshot.builder.panel_available", lambda: False)
        return build_snapshot(panel, tmp_path)


@pytest.mark.skipif(not panel_available(), reason="native writer unavailable")
def test_existing_parquet_snapshot_gains_a_usable_native_sidecar(panel, tmp_path, monkeypatch):
    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    datasets = {
        item.file: (directory / item.file).read_bytes() for item in original.datasets.values()
    }
    stats = {
        file: ((directory / file).stat().st_ino, (directory / file).stat().st_mtime_ns)
        for file in datasets
    }
    upgraded = build_snapshot(panel, tmp_path, require_qpanel=True)
    assert upgraded.panel["available"] and upgraded.panel["file"] == "panel.qpanel"
    assert replace(upgraded, panel=original.panel).to_json() == original.to_json()
    snapshot = load_snapshot(tmp_path, original.snapshot_id)
    np.testing.assert_array_equal(snapshot.matrix("close"), panel.matrix("close"))
    assert all((directory / file).read_bytes() == contents for file, contents in datasets.items())
    assert all(
        ((directory / file).stat().st_ino, (directory / file).stat().st_mtime_ns) == stat
        for file, stat in stats.items()
    )
    assert not list(directory.glob(".*tmp*"))


@pytest.mark.skipif(not panel_available(), reason="native writer unavailable")
def test_corrupt_sidecar_is_repaired_and_a_valid_cache_needs_no_writer(
    panel, tmp_path, monkeypatch
):
    original = build_snapshot(panel, tmp_path, require_qpanel=True)
    directory = tmp_path / original.snapshot_id
    target = directory / "panel.qpanel"
    target.write_bytes(b"broken native cache")
    repaired = build_snapshot(panel, tmp_path, require_qpanel=True)
    assert load_snapshot(tmp_path, original.snapshot_id).open_panel() is not None
    before = {file.name: file.read_bytes() for file in directory.iterdir()}
    monkeypatch.setattr("quantcore.snapshot.builder.panel_available", lambda: False)
    reused = build_snapshot(panel, tmp_path, require_qpanel=True)
    assert reused.to_json() == repaired.to_json()
    assert {file.name: file.read_bytes() for file in directory.iterdir()} == before


def test_partial_writer_failure_preserves_manifest_and_cleans_temporary_files(
    panel, tmp_path, monkeypatch
):
    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    before = (directory / "manifest.json").read_bytes()

    def failing_writer(panel, target):
        target.write_bytes(b"partial native file")
        raise OSError("writer failure")

    monkeypatch.setattr("quantcore.snapshot.builder.panel_available", lambda: True)
    monkeypatch.setattr("quantcore.snapshot.builder.write_qpanel", failing_writer)
    with pytest.raises(OSError, match="writer failure"):
        build_snapshot(panel, tmp_path, require_qpanel=True)
    assert (directory / "manifest.json").read_bytes() == before
    assert not (directory / "panel.qpanel").exists()
    assert not list(directory.glob(".*tmp*"))


@pytest.mark.skipif(not panel_available(), reason="native writer unavailable")
def test_manifest_publication_failure_is_not_success_and_retry_recovers(
    panel, tmp_path, monkeypatch
):
    import os

    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    before = (directory / "manifest.json").read_bytes()
    actual_replace = os.replace

    def fail_manifest(source, target):
        if Path(target).name == "manifest.json":
            raise OSError("manifest publication failed")
        return actual_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("quantcore.snapshot.builder.os.replace", fail_manifest)
        with pytest.raises(OSError, match="manifest publication failed"):
            build_snapshot(panel, tmp_path, require_qpanel=True)
    assert (directory / "manifest.json").read_bytes() == before
    assert (directory / "panel.qpanel").exists()  # Derived cache is unadvertised until retry.
    assert not list(directory.glob(".*tmp*"))
    repaired = build_snapshot(panel, tmp_path, require_qpanel=True)
    assert repaired.panel["file"] == "panel.qpanel"
    assert load_snapshot(tmp_path, original.snapshot_id).open_panel() is not None


def test_invalid_native_filename_cannot_escape_snapshot_directory(panel, tmp_path, monkeypatch):
    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    outside = tmp_path / "outside.qpanel"
    outside.write_bytes(b"unrelated generated test file")
    replace(original, panel={"available": True, "file": "../outside.qpanel"}).write(
        directory / "manifest.json"
    )
    before = (directory / "manifest.json").read_bytes()
    with pytest.raises(SnapshotError, match="filename"):
        build_snapshot(panel, tmp_path, require_qpanel=True)
    assert outside.read_bytes() == b"unrelated generated test file"
    assert (directory / "manifest.json").read_bytes() == before
    assert not list(directory.glob(".*tmp*"))


def test_corrupt_immutable_dataset_is_not_hidden_by_a_new_native_cache(
    panel, tmp_path, monkeypatch
):
    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    bars = directory / original.datasets["bars"].file
    before = bars.read_bytes() + b"corrupt"
    bars.write_bytes(before)
    with pytest.raises(SnapshotError, match=r"refusing native sidecar upgrade.*bars"):
        build_snapshot(panel, tmp_path, require_qpanel=True)
    assert bars.read_bytes() == before
    assert not (directory / "panel.qpanel").exists()
    assert not list(directory.glob(".*tmp*"))


@pytest.mark.skipif(not panel_available(), reason="native writer unavailable")
def test_existing_manifest_with_missing_sidecar_is_repaired(panel, tmp_path):
    original = build_snapshot(panel, tmp_path, require_qpanel=True)
    directory = tmp_path / original.snapshot_id
    (directory / "panel.qpanel").unlink()
    repaired = build_snapshot(panel, tmp_path, require_qpanel=True)
    assert replace(repaired, panel=original.panel).to_json() == original.to_json()
    assert load_snapshot(tmp_path, original.snapshot_id).open_panel() is not None
    assert not list(directory.glob(".*tmp*"))


def test_missing_writer_never_returns_false_success_or_changes_the_manifest(
    panel, tmp_path, monkeypatch
):
    original = without_native(panel, tmp_path, monkeypatch)
    directory = tmp_path / original.snapshot_id
    manifest = directory / "manifest.json"
    before = manifest.read_bytes()
    monkeypatch.setattr("quantcore.snapshot.builder.panel_available", lambda: False)
    with pytest.raises(CppUnavailableError, match="PanelWriter"):
        build_snapshot(panel, tmp_path, require_qpanel=True)
    assert manifest.read_bytes() == before
    assert not (directory / "panel.qpanel").exists()
    assert not list(directory.glob(".*tmp*"))
