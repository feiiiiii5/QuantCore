"""Immutable, content-addressed dataset snapshots (Parquet + optional .qpanel)."""

from __future__ import annotations

from .builder import build_snapshot, build_snapshot_from_store, snapshot_content_hash
from .manifest import SnapshotDataset, SnapshotManifest
from .qpanel import open_qpanel, qpanel_available, qpanel_field, write_qpanel
from .reader import Snapshot, find_snapshot, list_snapshots, load_snapshot

__all__ = [
    "Snapshot",
    "SnapshotDataset",
    "SnapshotManifest",
    "build_snapshot",
    "build_snapshot_from_store",
    "find_snapshot",
    "list_snapshots",
    "load_snapshot",
    "open_qpanel",
    "qpanel_available",
    "qpanel_field",
    "snapshot_content_hash",
    "write_qpanel",
]
