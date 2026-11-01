"""Shared server workspace: settings, snapshot cache and JSON-safe helpers."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..data.panel import PANEL_FIELDS, PanelData
from ..data.state import SQLiteState
from ..data.synthetic import generate_quick_panel
from ..snapshot.manifest import SnapshotManifest
from ..snapshot.reader import Snapshot, find_snapshot, list_snapshots, load_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_SNAPSHOTS_ROOT = DEFAULT_DATA_ROOT / "snapshots"
DEFAULT_EXPERIMENTS_ROOT = REPO_ROOT / "experiments"
DEFAULT_UI_DIR = REPO_ROOT / "ui" / "dist"


@dataclass(frozen=True)
class Settings:
    """Filesystem locations for one local workspace."""

    data_root: Path = DEFAULT_DATA_ROOT
    snapshots_root: Path = DEFAULT_SNAPSHOTS_ROOT
    experiments_root: Path = DEFAULT_EXPERIMENTS_ROOT
    state_path: Path = DEFAULT_DATA_ROOT / "state.sqlite"
    ui_dir: Path = DEFAULT_UI_DIR
    snapshot_cache_size: int = 4

    @classmethod
    def create(
        cls,
        *,
        data_root: str | Path | None = None,
        snapshots_root: str | Path | None = None,
        experiments_root: str | Path | None = None,
        state_path: str | Path | None = None,
        ui_dir: str | Path | None = None,
    ) -> Settings:
        root = Path(data_root) if data_root is not None else DEFAULT_DATA_ROOT
        return cls(
            data_root=root,
            snapshots_root=Path(snapshots_root)
            if snapshots_root is not None
            else root / "snapshots",
            experiments_root=Path(experiments_root)
            if experiments_root is not None
            else DEFAULT_EXPERIMENTS_ROOT,
            state_path=Path(state_path) if state_path is not None else root / "state.sqlite",
            ui_dir=Path(ui_dir) if ui_dir is not None else DEFAULT_UI_DIR,
        )


def json_safe(value: Any) -> Any:
    """Recursively make numpy/pandas/nan/inf values JSON-safe."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return str(value)
    return str(value)


@dataclass
class Workspace:
    """Per-app state shared by routes and the job runner."""

    settings: Settings
    state: SQLiteState
    queue: Any = field(default=None, repr=False)
    _cache: OrderedDict[str, Snapshot] = field(default_factory=OrderedDict, repr=False)
    _panel_cache: OrderedDict[str, PanelData] = field(default_factory=OrderedDict, repr=False)
    _synthetic: PanelData | None = field(default=None, repr=False)

    def list_snapshot_manifests(self) -> list[SnapshotManifest]:
        return list_snapshots(self.settings.snapshots_root)

    def snapshot(self, reference: str | None = None) -> Snapshot:
        if reference is None:
            manifests = self.list_snapshot_manifests()
            if not manifests:
                raise FileNotFoundError(
                    f"no snapshots under {self.settings.snapshots_root}; build one first"
                )
            reference = manifests[0].snapshot_id
        manifest = find_snapshot(self.settings.snapshots_root, reference).manifest
        key = manifest.snapshot_id
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        snapshot = load_snapshot(self.settings.snapshots_root, key)
        self._cache[key] = snapshot
        while len(self._cache) > self.settings.snapshot_cache_size:
            self._cache.popitem(last=False)
        return snapshot

    def snapshot_panel(self, snapshot: Snapshot) -> PanelData:
        """Materialise a snapshot panel once (UI pages hit the same snapshot repeatedly)."""
        key = snapshot.snapshot_id
        cached = self._panel_cache.get(key)
        if cached is not None:
            self._panel_cache.move_to_end(key)
            return cached
        panel = snapshot.to_panel_data()
        self._panel_cache[key] = panel
        while len(self._panel_cache) > self.settings.snapshot_cache_size:
            self._panel_cache.popitem(last=False)
        return panel

    def synthetic_panel(self) -> PanelData:
        if self._synthetic is None:
            self._synthetic = generate_quick_panel(n_sec=40)
        return self._synthetic

    def panel(
        self, reference: str | None = None, *, allow_synthetic: bool = True
    ) -> tuple[PanelData, dict[str, Any]]:
        """Load a snapshot panel, or a small synthetic fallback for first-run UX."""
        try:
            snapshot = self.snapshot(reference)
        except FileNotFoundError:
            if not allow_synthetic:
                raise
            panel = self.synthetic_panel()
            return panel, {
                "snapshot_id": "synthetic",
                "content_hash": panel.content_hash(),
                "synthetic": True,
                "source": "SYNTHETIC",
                "provider": "synthetic",
                "n_sec": panel.n_sec,
                "n_time": panel.n_time,
                "start": int(panel.calendar.dates[0]),
                "end": int(panel.calendar.dates[-1]),
                "panel_available": False,
                "datasets": {},
                "created_at": "",
                "fields": [field for field in PANEL_FIELDS if field in panel.bars.columns],
            }
        meta = snapshot.describe()
        meta.setdefault("fields", list((snapshot.manifest.panel or {}).get("fields", [])))
        meta.setdefault("created_at", snapshot.manifest.created_at)
        return self.snapshot_panel(snapshot), meta
