"""Read and verify immutable snapshots produced by :mod:`quantcore.snapshot.builder`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, date_str
from ..data.panel import PanelData
from ..errors import SnapshotError
from .checksums import sha256_file
from .manifest import SnapshotManifest

MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class Snapshot:
    """A frozen dataset directory with its verified manifest."""

    root: Path
    manifest: SnapshotManifest

    @property
    def snapshot_id(self) -> str:
        return self.manifest.snapshot_id

    @property
    def path(self) -> Path:
        return self.root

    @property
    def synthetic(self) -> bool:
        return self.manifest.synthetic

    def read_dataset(self, name: str) -> pd.DataFrame:
        dataset = self.manifest.datasets.get(name)
        if dataset is None:
            raise SnapshotError(f"snapshot {self.snapshot_id} has no dataset {name!r}")
        path = self.root / dataset.file
        if not path.exists():
            raise SnapshotError(f"snapshot file missing: {path}")
        return pd.read_parquet(path)

    def calendar(self) -> TradingCalendar:
        return TradingCalendar.from_dates(self.read_dataset("calendar")["date"].tolist())

    def securities(self) -> pd.DataFrame:
        return self.read_dataset("securities")

    def bars(self) -> pd.DataFrame:
        return self.read_dataset("bars")

    def financials(self) -> pd.DataFrame:
        if "financials" in self.manifest.datasets:
            return self.read_dataset("financials")
        return pd.DataFrame()

    def corporate_actions(self) -> pd.DataFrame:
        if "corporate_actions" in self.manifest.datasets:
            return self.read_dataset("corporate_actions")
        return pd.DataFrame()

    def to_panel_data(self) -> PanelData:
        """Materialise the snapshot as an in-memory :class:`PanelData`."""
        return PanelData(
            calendar=self.calendar(),
            securities=self.securities(),
            bars=self.bars(),
            financials=self.financials(),
            corporate_actions=self.corporate_actions(),
            meta={
                "synthetic": self.manifest.synthetic,
                "source": self.manifest.source,
                "provider": self.manifest.provider,
                "seed": self.manifest.seed,
                "disclaimer": self.manifest.disclaimer,
                "snapshot_id": self.manifest.snapshot_id,
                "content_hash": self.manifest.content_hash,
                "config": self.manifest.metadata.get("config"),
                "scenarios": self.manifest.metadata.get("scenarios"),
            },
        )

    # -- .qpanel access ---------------------------------------------------
    def panel_path(self) -> Path:
        info = self.manifest.panel or {}
        file_name = info.get("file", "panel.qpanel")
        if not info.get("available", False):
            raise SnapshotError(
                f"snapshot {self.snapshot_id} has no .qpanel file (C++ writer was unavailable "
                "when it was built); rebuild after `make build`"
            )
        return self.root / str(file_name)

    def open_panel(self) -> Any:
        from .qpanel import open_qpanel

        return open_qpanel(self.panel_path())

    def matrix(self, field_name: str) -> np.ndarray:
        """Return a ``(n_time, n_sec)`` matrix from the ``.qpanel`` (or Parquet fallback)."""
        if (self.manifest.panel or {}).get("available", False):
            from .qpanel import qpanel_field

            return qpanel_field(self.open_panel(), field_name)
        bars = self.bars()
        pivot = bars.pivot_table(index="date", columns="sec_id", values=field_name, aggfunc="last")
        calendar = self.calendar()
        sec_ids = [str(value) for value in self.securities()["sec_id"].tolist()]
        pivot = pivot.reindex(index=list(calendar.dates), columns=sec_ids)
        return pivot.to_numpy(dtype=np.float64)

    # -- verification -----------------------------------------------------
    def verify(self) -> list[str]:
        problems: list[str] = []
        for name, dataset in self.manifest.datasets.items():
            path = self.root / dataset.file
            if not path.exists():
                problems.append(f"{name}: missing file {dataset.file}")
                continue
            digest = sha256_file(path)
            if digest != dataset.sha256:
                problems.append(f"{name}: sha256 mismatch")
            if path.stat().st_size != dataset.bytes:
                problems.append(f"{name}: size mismatch")
        panel_info = self.manifest.panel or {}
        panel_file = panel_info.get("file")
        if panel_info.get("available") and panel_file:
            path = self.root / str(panel_file)
            if not path.exists():
                problems.append("panel: missing .qpanel file")
            else:
                digest = sha256_file(path)
                if digest != panel_info.get("sha256"):
                    problems.append("panel: .qpanel sha256 mismatch")
        if not self.manifest.snapshot_id.startswith(f"snap_{self.manifest.content_hash[:16]}"):
            problems.append("manifest: snapshot id does not match content hash")
        return problems

    def describe(self) -> dict[str, Any]:
        metadata = self.manifest.metadata
        return {
            "snapshot_id": self.manifest.snapshot_id,
            "content_hash": self.manifest.content_hash,
            "synthetic": self.manifest.synthetic,
            "source": self.manifest.source,
            "provider": self.manifest.provider,
            "seed": self.manifest.seed,
            "n_sec": metadata.get("n_sec"),
            "n_time": metadata.get("n_time"),
            "start": date_str(int(metadata["start"])) if metadata.get("start") else None,
            "end": date_str(int(metadata["end"])) if metadata.get("end") else None,
            "panel_available": bool((self.manifest.panel or {}).get("available", False)),
            "datasets": {
                name: {"rows": item.rows, "bytes": item.bytes}
                for name, item in sorted(self.manifest.datasets.items())
            },
            "created_at": self.manifest.created_at,
        }


def load_snapshot(root: str | Path, snapshot_id: str) -> Snapshot:
    """Load one snapshot directory and validate its file hashes."""
    root_path = Path(root)
    directory = root_path / snapshot_id
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.exists():
        raise SnapshotError(f"snapshot not found: {directory}")
    manifest = SnapshotManifest.read(manifest_path)
    if manifest.snapshot_id != snapshot_id:
        raise SnapshotError(
            f"manifest snapshot_id {manifest.snapshot_id!r} does not match directory {snapshot_id!r}"
        )
    snapshot = Snapshot(root=directory, manifest=manifest)
    problems = snapshot.verify()
    if problems:
        raise SnapshotError(f"snapshot {snapshot_id} failed verification: {problems}")
    return snapshot


def list_snapshots(root: str | Path) -> list[SnapshotManifest]:
    """List snapshot manifests under ``root``, newest first."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    manifests: list[SnapshotManifest] = []
    for directory in sorted(root_path.glob("snap_*")):
        manifest_path = directory / MANIFEST_NAME
        if not manifest_path.exists():
            continue
        try:
            manifests.append(SnapshotManifest.read(manifest_path))
        except (json.JSONDecodeError, KeyError):
            continue
    manifests.sort(key=lambda item: (item.created_at, item.snapshot_id), reverse=True)
    return manifests


def find_snapshot(root: str | Path, reference: str) -> Snapshot:
    """Load a snapshot by id, unique prefix, or the literal ``latest``."""
    if reference == "latest":
        manifests = list_snapshots(root)
        if not manifests:
            raise SnapshotError(f"no snapshots found under {root}")
        return load_snapshot(root, manifests[0].snapshot_id)
    matches = [
        snapshot.snapshot_id
        for snapshot in list_snapshots(root)
        if snapshot.snapshot_id.startswith(reference)
    ]
    if not matches:
        raise SnapshotError(f"snapshot {reference!r} not found under {root}")
    if len(matches) > 1:
        raise SnapshotError(f"snapshot reference {reference!r} is ambiguous: {matches[:5]}")
    return load_snapshot(root, matches[0])
