"""Latest means the most recently published snapshot, including content reuse."""

from __future__ import annotations

import json
import os

import pytest

from quantcore.data.state import SQLiteState
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
from quantcore.server.workspace import Settings, Workspace
from quantcore.snapshot import build_snapshot, find_snapshot, list_snapshots


@pytest.fixture(scope="module")
def panels():
    return [
        generate_synthetic_panel(
            SyntheticConfig(n_sec=n, start="2023-01-03", end="2023-12-29", seed=n)
        )
        for n in (2, 3)
    ]


def test_republishing_a_keeps_identity_and_selects_a_across_cli_api_and_restart(tmp_path, panels):
    settings = Settings.create(data_root=tmp_path)
    state = SQLiteState(settings.state_path)
    workspace = Workspace(settings, state)
    first = build_snapshot(panels[0], settings.snapshots_root, state=state)
    manifest_path = settings.snapshots_root / first.snapshot_id / "manifest.json"
    original = manifest_path.read_bytes()
    second = build_snapshot(panels[1], settings.snapshots_root, state=state)
    assert workspace.snapshot().snapshot_id == second.snapshot_id
    reused = build_snapshot(panels[0], settings.snapshots_root, state=state)
    assert reused.snapshot_id == first.snapshot_id
    assert manifest_path.read_bytes() == original  # Creation time and data identity stay immutable.
    assert workspace.snapshot().snapshot_id == first.snapshot_id
    assert workspace.snapshot("latest").snapshot_id == first.snapshot_id
    assert find_snapshot(settings.snapshots_root, "latest").snapshot_id == first.snapshot_id
    reopened = Workspace(settings, SQLiteState(settings.state_path))
    assert reopened.snapshot().snapshot_id == first.snapshot_id
    assert reopened.snapshot(second.snapshot_id).snapshot_id == second.snapshot_id


def test_failed_repair_does_not_publish_a_new_latest(tmp_path, panels, monkeypatch):
    first = build_snapshot(panels[0], tmp_path)
    second = build_snapshot(panels[1], tmp_path)
    (tmp_path / first.snapshot_id / "panel.qpanel").unlink(missing_ok=True)
    before = (tmp_path / "latest.json").read_bytes()

    def failure(*_):
        raise OSError("native cache repair failed")

    monkeypatch.setattr("quantcore.snapshot.builder.panel_available", lambda: True)
    monkeypatch.setattr("quantcore.snapshot.builder.write_qpanel", failure)
    with pytest.raises(OSError, match="native cache repair failed"):
        build_snapshot(panels[0], tmp_path, require_qpanel=True)
    assert (tmp_path / "latest.json").read_bytes() == before
    assert find_snapshot(tmp_path, "latest").snapshot_id == second.snapshot_id
    assert not list(tmp_path.glob(".tmp-latest-*"))
    actual_replace = os.replace

    def fail_publication(source, target):
        if target.name == "latest.json":
            raise OSError("publication record failed")
        return actual_replace(source, target)

    monkeypatch.setattr("quantcore.snapshot.builder.os.replace", fail_publication)
    with pytest.raises(OSError, match="publication record failed"):
        build_snapshot(panels[0], tmp_path)
    assert (tmp_path / "latest.json").read_bytes() == before
    assert find_snapshot(tmp_path, "latest").snapshot_id == second.snapshot_id
    assert not list(tmp_path.glob(".tmp-latest-*"))


@pytest.mark.parametrize(
    "pointer", [None, "invalid json", {"snapshot_id": "missing"}, [], "wrong-hash"]
)
def test_missing_or_invalid_publication_record_keeps_legacy_file_fallback(
    tmp_path, panels, pointer
):
    first = build_snapshot(panels[0], tmp_path)
    second = build_snapshot(panels[1], tmp_path)
    path = tmp_path / "latest.json"
    if pointer is None:
        path.unlink()
    else:
        if pointer == "wrong-hash":
            pointer = {"snapshot_id": first.snapshot_id, "content_hash": "wrong"}
        path.write_text(pointer if isinstance(pointer, str) else json.dumps(pointer))
    assert list_snapshots(tmp_path)[0].snapshot_id == second.snapshot_id
    assert find_snapshot(tmp_path, "latest").snapshot_id == second.snapshot_id
