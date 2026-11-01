"""Immutable-ish Parquet warehouse with manifest, DuckDB query layer and SQLite state.

Layout::

    <root>/
      dataset=bars/year=2024/part-0000.parquet
      dataset=securities/part-0000.parquet
      ...
      warehouse_manifest.json      # dataset -> files, rows, sha256, content hash
      state.sqlite                 # application state (see quantcore.data.state)

Parquet is the authoritative copy of ingested data; DuckDB provides SQL over the
partitioned files; ``.qpanel`` snapshots are built from a frozen Parquet copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..calendar import TradingCalendar
from .panel import PanelData, normalize_bars, normalize_securities
from .state import SQLiteState

DATASET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

CANONICAL_DATASETS: tuple[str, ...] = (
    "calendar",
    "securities",
    "bars",
    "financials",
    "corporate_actions",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


@dataclass(frozen=True)
class FileStat:
    relative_path: str
    sha256: str
    rows: int
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "rows": int(self.rows),
            "bytes": int(self.bytes),
        }


@dataclass
class DatasetStats:
    dataset: str
    partition_column: str | None
    rows: int
    files: list[FileStat] = field(default_factory=list)
    content_hash: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "partition_column": self.partition_column,
            "rows": int(self.rows),
            "files": [item.to_dict() for item in self.files],
            "content_hash": self.content_hash,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DatasetStats:
        return cls(
            dataset=payload["dataset"],
            partition_column=payload.get("partition_column"),
            rows=int(payload["rows"]),
            files=[FileStat(**item) for item in payload.get("files", [])],
            content_hash=payload.get("content_hash", ""),
            updated_at=payload.get("updated_at", ""),
        )


def _content_hash(files: list[FileStat]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda stats: stats.relative_path):
        digest.update(item.relative_path.encode())
        digest.update(item.sha256.encode())
        digest.update(str(item.rows).encode())
    return digest.hexdigest()


@dataclass
class WarehouseManifest:
    schema_version: str = "1"
    created_at: str = ""
    updated_at: str = ""
    datasets: dict[str, DatasetStats] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "datasets": {name: stats.to_dict() for name, stats in sorted(self.datasets.items())},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)

    def content_hash(self) -> str:
        """Hash of dataset content only (stable across manifest timestamp changes)."""
        digest = hashlib.sha256()
        digest.update(self.schema_version.encode())
        for name, stats in sorted(self.datasets.items()):
            digest.update(name.encode())
            digest.update(stats.content_hash.encode())
        return digest.hexdigest()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WarehouseManifest:
        return cls(
            schema_version=payload.get("schema_version", "1"),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            datasets={
                name: DatasetStats.from_dict(item)
                for name, item in payload.get("datasets", {}).items()
            },
        )


class ParquetStore:
    """Partitioned Parquet warehouse plus manifest and DuckDB views."""

    def __init__(self, root: str | Path, state: SQLiteState | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "warehouse_manifest.json"
        self.state = state or SQLiteState(self.root / "state.sqlite")
        self._manifest = self._load_manifest()

    # -- manifest ---------------------------------------------------------
    def _load_manifest(self) -> WarehouseManifest:
        if self.manifest_path.exists():
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return WarehouseManifest.from_dict(payload)
        return WarehouseManifest(created_at=_now(), updated_at=_now())

    @property
    def manifest(self) -> WarehouseManifest:
        return self._manifest

    def _save_manifest(self, manifest: WarehouseManifest) -> None:
        manifest.updated_at = _now()
        _atomic_write_text(self.manifest_path, manifest.to_json())
        self._manifest = manifest

    def manifest_hash(self) -> str:
        return self.manifest.content_hash()

    # -- write path -------------------------------------------------------
    @staticmethod
    def _dataset_dir(root: Path, name: str) -> Path:
        return root / f"dataset={name}"

    def _existing_files(self, name: str) -> list[Path]:
        directory = self._dataset_dir(self.root, name)
        if not directory.exists():
            return []
        return sorted(directory.rglob("*.parquet"))

    def _write_frame(self, frame: pd.DataFrame, target: Path) -> tuple[str, int, int]:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        frame.to_parquet(temporary, engine="pyarrow", compression="zstd", index=False)
        os.replace(temporary, target)
        sha = _sha256_file(target)
        return sha, len(frame), target.stat().st_size

    def _partition_frames(
        self,
        frame: pd.DataFrame,
        partition_column: str | None,
        date_column: str = "date",
    ) -> list[tuple[str | None, pd.DataFrame]]:
        if partition_column is None:
            return [(None, frame)]
        if partition_column == "year":
            if date_column not in frame.columns:
                raise ValueError(f"year partitioning requires a {date_column!r} column")
            years = (frame[date_column].astype("int64") // 10000).astype(str)
            return [(year, frame[years == year]) for year in sorted(years.unique())]
        if partition_column not in frame.columns:
            raise ValueError(f"partition column not found: {partition_column}")
        keys = frame[partition_column].astype(str)
        return [(key, frame[keys == key]) for key in sorted(keys.unique())]

    def write_dataset(
        self,
        name: str,
        frame: pd.DataFrame,
        partition_column: str | None = "year",
        date_column: str = "date",
    ) -> DatasetStats:
        """Write a dataset atomically; replacing existing partitions of the same name."""
        if not DATASET_NAME_RE.match(name):
            raise ValueError(f"invalid dataset name: {name!r}")
        parts = self._partition_frames(frame, partition_column, date_column)
        desired: list[FileStat] = []
        dataset_dir = self._dataset_dir(self.root, name)
        desired_paths: set[Path] = set()
        for key, part in parts:
            relative = Path(f"dataset={name}") / (
                "part-0000.parquet" if key is None else f"year={key}/part-0000.parquet"
            )
            target = self.root / relative
            desired_paths.add(target)
            sha, rows, size = self._write_frame(part, target)
            desired.append(FileStat(str(relative), sha, rows, size))
        for stale in self._existing_files(name):
            if stale not in desired_paths:
                stale.unlink()
                parent = stale.parent
                while parent != dataset_dir and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
        stats = DatasetStats(
            dataset=name,
            partition_column=partition_column,
            rows=len(frame),
            files=sorted(desired, key=lambda item: item.relative_path),
            content_hash=_content_hash(desired),
            updated_at=_now(),
        )
        manifest = self._manifest
        manifest.datasets[name] = stats
        self._save_manifest(manifest)
        watermark = None
        if date_column in frame.columns and len(frame):
            watermark = int(frame[date_column].astype("int64").max())
        self.state.upsert_dataset(name, str(dataset_dir), stats.rows, stats.content_hash, watermark)
        return stats

    def write_panel(self, panel: PanelData) -> dict[str, DatasetStats]:
        """Write the five canonical datasets of a :class:`PanelData`."""
        stats: dict[str, DatasetStats] = {}
        stats["calendar"] = self.write_dataset(
            "calendar", pd.DataFrame({"date": list(panel.calendar.dates)}), partition_column=None
        )
        stats["securities"] = self.write_dataset(
            "securities", normalize_securities(panel.securities), partition_column=None
        )
        stats["bars"] = self.write_dataset("bars", normalize_bars(panel.bars), "year")
        if not panel.financials.empty:
            stats["financials"] = self.write_dataset(
                "financials", panel.financials, "year", date_column="end_date"
            )
        if not panel.corporate_actions.empty:
            stats["corporate_actions"] = self.write_dataset(
                "corporate_actions", panel.corporate_actions, "year", date_column="ex_date"
            )
        self.state.set_meta("panel_meta", panel.meta)
        return stats

    # -- read path --------------------------------------------------------
    def dataset_files(self, name: str) -> list[Path]:
        return self._existing_files(name)

    def list_datasets(self) -> list[str]:
        return sorted(self._manifest.datasets)

    def read_dataset(self, name: str, columns: list[str] | None = None) -> pd.DataFrame:
        files = self._existing_files(name)
        if not files:
            raise FileNotFoundError(f"dataset not found in warehouse: {name}")
        frames = [pd.read_parquet(path, columns=columns) for path in files]
        return pd.concat(frames, ignore_index=True)

    def load_panel(self) -> PanelData:
        """Reassemble the canonical panel from the warehouse datasets."""
        required = {"calendar", "securities", "bars"}
        missing = required - set(self.list_datasets())
        if missing:
            raise FileNotFoundError(f"warehouse is missing datasets: {sorted(missing)}")
        calendar_frame = self.read_dataset("calendar")
        calendar = TradingCalendar.from_dates(calendar_frame["date"].tolist())
        financials = (
            self.read_dataset("financials")
            if "financials" in self.list_datasets()
            else pd.DataFrame()
        )
        actions = (
            self.read_dataset("corporate_actions")
            if "corporate_actions" in self.list_datasets()
            else pd.DataFrame()
        )
        return PanelData(
            calendar=calendar,
            securities=self.read_dataset("securities"),
            bars=self.read_dataset("bars"),
            financials=financials,
            corporate_actions=actions,
            meta=self.state.get_meta("panel_meta", {}) or {},
        )

    def query(self, sql: str) -> pd.DataFrame:
        """Run SQL over dataset names as views (DuckDB over the Parquet files)."""
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - declared dependency
            raise RuntimeError("duckdb is required for warehouse queries") from exc
        connection = duckdb.connect(database=":memory:")
        try:
            for name in self.list_datasets():
                files = self._existing_files(name)
                if not files:
                    continue
                literals = ", ".join("'" + str(path).replace("'", "''") + "'" for path in files)
                connection.execute(
                    f'CREATE OR REPLACE VIEW "{name}" AS '
                    f"SELECT * FROM read_parquet([{literals}], union_by_name=true)"
                )
            return connection.execute(sql).fetch_df()
        finally:
            connection.close()

    # -- integrity --------------------------------------------------------
    def verify(self) -> list[str]:
        problems: list[str] = []
        for name, stats in self._manifest.datasets.items():
            files = self._existing_files(name)
            by_relative = {str(path.relative_to(self.root)): path for path in files}
            if len(files) != len(stats.files):
                problems.append(f"{name}: file count {len(files)} != manifest {len(stats.files)}")
            for item in stats.files:
                path = by_relative.get(item.relative_path)
                if path is None:
                    problems.append(f"{name}: missing file {item.relative_path}")
                    continue
                if _sha256_file(path) != item.sha256:
                    problems.append(f"{name}: sha256 mismatch for {item.relative_path}")
                try:
                    rows = len(pd.read_parquet(path, columns=[]))
                except Exception as exc:  # pragma: no cover - corrupt parquet
                    problems.append(f"{name}: unreadable parquet {item.relative_path}: {exc}")
                    continue
                if rows != item.rows:
                    problems.append(
                        f"{name}: row count mismatch for {item.relative_path} "
                        f"({rows} != {item.rows})"
                    )
            if _content_hash(stats.files) != stats.content_hash:
                problems.append(f"{name}: content hash mismatch")
        return problems

    def describe(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "manifest_hash": self.manifest_hash(),
            "datasets": {
                name: {
                    "rows": stats.rows,
                    "files": len(stats.files),
                    "content_hash": stats.content_hash,
                }
                for name, stats in sorted(self._manifest.datasets.items())
            },
            "state_schema_version": self.state.current_version(),
        }

    def reset(self) -> None:
        """Delete all datasets and the manifest (used by tests and ``qc data reset``)."""
        for name in self.list_datasets():
            shutil.rmtree(self._dataset_dir(self.root, name), ignore_errors=True)
        if self.manifest_path.exists():
            self.manifest_path.unlink()
        self._manifest = WarehouseManifest(created_at=_now(), updated_at=_now())
