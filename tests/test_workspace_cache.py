"""Immutable snapshot reuse without repeated full-file reads."""

from pathlib import Path

import pytest

from quantcore.data.state import SQLiteState
from quantcore.errors import SnapshotError
from quantcore.server.workspace import Settings, Workspace
from quantcore.snapshot import Snapshot, reader


def test_snapshot_cache_reuses_verified_files_and_detects_changes(
    synthetic_snapshot: Snapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    snapshot_root = tmp_path / "snapshots"
    directory = snapshot_root / synthetic_snapshot.snapshot_id
    shutil.copytree(synthetic_snapshot.root, directory)
    workspace = Workspace(
        Settings.create(data_root=tmp_path), SQLiteState(tmp_path / "state.sqlite")
    )
    checksum = reader.sha256_file
    reads: list[Path] = []

    def counted(path: Path) -> str:
        reads.append(path)
        return checksum(path)

    monkeypatch.setattr(reader, "sha256_file", counted)
    snapshot = workspace.snapshot(synthetic_snapshot.snapshot_id)
    assert len(reads) == len(snapshot.manifest.datasets) + int(
        snapshot.manifest.panel.get("available", False)
    )
    panel = workspace.snapshot_panel(snapshot)
    reads.clear()
    assert workspace.snapshot() is snapshot
    assert workspace.snapshot("latest") is snapshot
    assert workspace.snapshot(snapshot.snapshot_id[:12]) is snapshot
    assert workspace.snapshot_panel(snapshot) is panel
    assert reads == []

    # A real same-size on-disk mutation must invalidate the verified cache.
    path = directory / snapshot.manifest.datasets["bars"].file
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(data)
    with pytest.raises(SnapshotError, match="sha256 mismatch"):
        workspace.snapshot(snapshot.snapshot_id)


def test_snapshot_cache_rechecks_changed_manifest(
    synthetic_snapshot: Snapshot, tmp_path: Path
) -> None:
    import json
    import shutil

    snapshot_root = tmp_path / "snapshots"
    directory = snapshot_root / synthetic_snapshot.snapshot_id
    shutil.copytree(synthetic_snapshot.root, directory)
    workspace = Workspace(
        Settings.create(data_root=tmp_path), SQLiteState(tmp_path / "state.sqlite")
    )
    original = workspace.snapshot()
    panel = workspace.snapshot_panel(original)
    manifest_path = directory / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    payload["provider"] = "updated-provider"
    manifest_path.write_text(json.dumps(payload))
    updated = workspace.snapshot()
    assert updated is not original
    assert updated.manifest.provider == "updated-provider"
    assert workspace.snapshot_panel(updated) is not panel
