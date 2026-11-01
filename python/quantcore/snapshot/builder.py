"""Build content-addressed immutable snapshots from a canonical panel.

A snapshot directory is written atomically and named ``snap_<hash16>`` where the hash is
derived from the canonical data payload (frames, schema, calendar, source metadata) but
not from wall-clock timestamps.  Building the same panel twice therefore yields the same
snapshot id, and an existing directory is verified rather than overwritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .. import CppUnavailableError, panel_available
from ..data.panel import SCHEMA_VERSION, PanelData
from ..data.state import SQLiteState
from ..errors import SnapshotError
from ..quality import QualityReport, run_quality_checks
from .manifest import MANIFEST_SCHEMA_VERSION, SnapshotDataset, SnapshotManifest
from .qpanel import write_qpanel

SNAPSHOT_FILE_ORDER: tuple[str, ...] = (
    "calendar",
    "securities",
    "bars",
    "financials",
    "corporate_actions",
)


def _frame_digest(frame: pd.DataFrame) -> str:
    hasher = hashlib.sha256()
    hasher.update("|".join(map(str, frame.columns)).encode())
    hasher.update(str(list(frame.dtypes.astype(str))).encode())
    hasher.update(str(len(frame)).encode())
    hasher.update(pd.util.hash_pandas_object(frame, index=False).values.tobytes())
    return hasher.hexdigest()


def _canonical_frames(panel: PanelData) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {
        "calendar": pd.DataFrame({"date": [int(date) for date in panel.calendar.dates]}),
        "securities": panel.securities.reset_index(drop=True),
        "bars": panel.bars.reset_index(drop=True),
    }
    if not panel.financials.empty:
        frames["financials"] = panel.financials.reset_index(drop=True)
    if not panel.corporate_actions.empty:
        frames["corporate_actions"] = panel.corporate_actions.reset_index(drop=True)
    return frames


def snapshot_content_hash(panel: PanelData) -> tuple[str, dict[str, Any]]:
    """Return ``(content_hash, payload)`` for the canonical snapshot payload."""
    frames = _canonical_frames(panel)
    payload: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "panel_schema_version": SCHEMA_VERSION,
        "synthetic": bool(panel.meta.get("synthetic", False)),
        "source": str(panel.meta.get("source", panel.meta.get("provider", "unknown"))),
        "seed": panel.meta.get("seed"),
        "disclaimer": str(panel.meta.get("disclaimer", "")),
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
        "datasets": {
            name: {
                "rows": len(frame),
                "digest": _frame_digest(frame),
            }
            for name, frame in frames.items()
        },
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest(), payload


def _write_frame(tmp: Path, name: str, frame: pd.DataFrame) -> SnapshotDataset:
    target = tmp / f"{name}.parquet"
    frame.to_parquet(target, engine="pyarrow", compression="zstd", index=False)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return SnapshotDataset(
        name=name,
        file=target.name,
        rows=len(frame),
        sha256=digest,
        bytes=target.stat().st_size,
    )


def build_snapshot(
    panel: PanelData,
    root: str | Path,
    *,
    state: SQLiteState | None = None,
    quality: QualityReport | None = None,
    require_qpanel: bool = False,
) -> SnapshotManifest:
    """Freeze ``panel`` into a content-addressed snapshot directory and return its manifest."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    report = quality or run_quality_checks(panel)
    if not report.passed:
        raise SnapshotError(
            "refusing to build a snapshot from data that fails quality checks: "
            + "; ".join(issue.message for issue in report.errors)
        )
    content_hash, payload = snapshot_content_hash(panel)
    snapshot_id = f"snap_{content_hash[:16]}"
    final = root_path / snapshot_id
    if final.exists():
        manifest_path = final / "manifest.json"
        if not manifest_path.exists():
            raise SnapshotError(f"snapshot directory exists without manifest: {final}")
        manifest = SnapshotManifest.read(manifest_path)
        if manifest.content_hash != content_hash:
            raise SnapshotError(
                f"snapshot id collision/integrity failure for {snapshot_id}: "
                "directory content does not match the requested panel"
            )
        if state is not None:
            state.record_snapshot(snapshot_id, str(final), content_hash, manifest.synthetic)
        return manifest

    temporary = root_path / f".tmp-{snapshot_id}-{uuid.uuid4().hex[:8]}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        frames = _canonical_frames(panel)
        datasets = {
            name: _write_frame(temporary, name, frames[name])
            for name in SNAPSHOT_FILE_ORDER
            if name in frames
        }
        panel_info: dict[str, Any] = {"available": False}
        if panel_available():
            panel_info = write_qpanel(panel, temporary / "panel.qpanel")
            panel_info["available"] = True
        elif require_qpanel:
            raise CppUnavailableError(
                "snapshot requires a .qpanel file but the C++ PanelWriter is not available; "
                "run `make build` and retry"
            )
        quality_dict = report.to_dict()
        quality_path = temporary / "quality_report.json"
        quality_path.write_text(
            json.dumps(quality_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            content_hash=content_hash,
            schema_version=MANIFEST_SCHEMA_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            synthetic=bool(panel.meta.get("synthetic", False)),
            source=str(payload["source"]),
            provider=str(panel.meta.get("provider", payload["source"])),
            seed=panel.meta.get("seed"),
            disclaimer=str(panel.meta.get("disclaimer", "")),
            datasets=datasets,
            panel=panel_info,
            quality={
                "passed": report.passed,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "rows": report.rows,
            },
            metadata={
                "n_sec": panel.n_sec,
                "n_time": panel.n_time,
                "start": int(panel.calendar.dates[0]),
                "end": int(panel.calendar.dates[-1]),
                "config": panel.meta.get("config"),
                "scenarios": panel.meta.get("scenarios"),
                "quality_report": quality_path.name,
            },
        )
        manifest.write(temporary / "manifest.json")
        os.replace(temporary, final)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    if state is not None:
        state.record_snapshot(snapshot_id, str(final), content_hash, manifest.synthetic)
    return manifest


def build_snapshot_from_store(
    store: Any,
    root: str | Path,
    *,
    state: SQLiteState | None = None,
    require_qpanel: bool = False,
) -> SnapshotManifest:
    """Build a snapshot from the canonical datasets currently in a :class:`ParquetStore`."""
    panel = store.load_panel()
    effective_state = state if state is not None else getattr(store, "state", None)
    return build_snapshot(
        panel,
        root,
        state=effective_state,
        require_qpanel=require_qpanel,
    )
