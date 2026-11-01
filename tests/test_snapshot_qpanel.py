"""Snapshot / .qpanel tests: content addressing, C++ writer/reader, manifests and verify."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import quantcore
from quantcore.errors import CppUnavailableError, SnapshotError
from quantcore.snapshot import (
    build_snapshot,
    find_snapshot,
    list_snapshots,
    load_snapshot,
    qpanel_available,
)

pytestmark = pytest.mark.skipif(
    not qpanel_available(), reason="C++ .qpanel writer/reader is unavailable"
)


def test_snapshot_layout_and_manifest(small_panel, tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    manifest = build_snapshot(small_panel, root)
    assert manifest.snapshot_id.startswith("snap_")
    assert manifest.synthetic is True
    directory = root / manifest.snapshot_id
    assert directory.is_dir()
    for name in ("bars", "securities", "calendar", "financials", "corporate_actions"):
        assert (directory / f"{name}.parquet").exists(), name
    assert (directory / "panel.qpanel").exists()
    assert (directory / "manifest.json").exists()
    assert (directory / "quality_report.json").exists()
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert payload["panel"]["available"] is True
    assert payload["panel"]["writer"] == "_qcore.PanelWriter"
    assert payload["quality"]["passed"] is True

    snap = load_snapshot(root, manifest.snapshot_id)
    assert snap.snapshot_id == manifest.snapshot_id
    assert snap.verify() == []
    described = snap.describe()
    assert described["n_sec"] == small_panel.n_sec
    assert described["n_time"] == small_panel.n_time
    assert described["panel_available"] is True


def test_snapshot_is_content_addressed(small_panel, tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    first = build_snapshot(small_panel, root)
    second = build_snapshot(small_panel, root)
    assert first.snapshot_id == second.snapshot_id
    changed_data = small_panel.select(end="2024-06-28")
    third = build_snapshot(changed_data, root)
    assert third.snapshot_id != first.snapshot_id
    assert len(list_snapshots(root)) == 2


def test_qpanel_roundtrip_matches_panel(small_panel, synthetic_snapshot) -> None:
    panel_object = synthetic_snapshot.open_panel()
    assert panel_object.n_sec == small_panel.n_sec
    assert panel_object.n_time == small_panel.n_time
    assert [int(value) for value in panel_object.dates] == list(small_panel.calendar.dates)
    assert "close" in panel_object.field_names()
    close = synthetic_snapshot.matrix("close")
    expected = small_panel.matrix("close")
    assert close.shape == expected.shape == (small_panel.n_time, small_panel.n_sec)
    mask = np.isfinite(expected)
    assert np.allclose(close[mask], expected[mask], rtol=0, atol=1e-9)
    assert np.array_equal(np.isnan(close), np.isnan(expected))
    securities = panel_object.securities
    assert len(securities) == small_panel.n_sec
    assert securities[0]["sec_id"] == small_panel.sec_ids[0]


def test_snapshot_to_panel_data(small_panel, synthetic_snapshot) -> None:
    restored = synthetic_snapshot.to_panel_data()
    assert restored.n_sec == small_panel.n_sec
    assert restored.n_time == small_panel.n_time
    assert set(restored.meta) >= {"synthetic", "snapshot_id", "content_hash"}
    assert len(restored.bars) == len(small_panel.bars)
    assert restored.calendar.dates == small_panel.calendar.dates


def test_find_snapshot_prefix_and_latest(small_panel, tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    manifest = build_snapshot(small_panel, root)
    by_prefix = find_snapshot(root, manifest.snapshot_id[:12])
    assert by_prefix.snapshot_id == manifest.snapshot_id
    latest = find_snapshot(root, "latest")
    assert latest.snapshot_id == manifest.snapshot_id
    with pytest.raises(SnapshotError):
        find_snapshot(root, "snap_does_not_exist")


def test_verify_detects_tampering(small_panel, tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    manifest = build_snapshot(small_panel, root)
    snap = load_snapshot(root, manifest.snapshot_id)
    bars_path = snap.path / "bars.parquet"
    bars_path.write_bytes(bars_path.read_bytes() + b"tamper")
    problems = snap.verify()
    assert any("sha256" in problem for problem in problems)


def test_require_qpanel_fails_when_writer_missing(
    small_panel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quantcore.snapshot import builder

    monkeypatch.setattr(builder, "panel_available", lambda: False)
    with pytest.raises(CppUnavailableError):
        build_snapshot(small_panel, tmp_path / "snapshots", require_qpanel=True)
    optional = build_snapshot(small_panel, tmp_path / "snapshots", require_qpanel=False)
    assert optional.panel["available"] is False


def test_snapshot_immutability_error_paths(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError):
        load_snapshot(tmp_path / "missing", "snap_0000000000000000")
    assert quantcore.panel_available()
