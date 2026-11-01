"""Snapshot manifest: the immutable, content-addressed description of a dataset freeze."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class SnapshotDataset:
    """One file inside a snapshot directory."""

    name: str
    file: str
    rows: int
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "rows": int(self.rows),
            "sha256": self.sha256,
            "bytes": int(self.bytes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SnapshotDataset:
        return cls(
            name=str(payload["name"]),
            file=str(payload["file"]),
            rows=int(payload.get("rows", 0)),
            sha256=str(payload.get("sha256", "")),
            bytes=int(payload.get("bytes", 0)),
        )


@dataclass(frozen=True)
class SnapshotManifest:
    """Everything needed to verify and replay a snapshot."""

    snapshot_id: str
    content_hash: str
    schema_version: str = MANIFEST_SCHEMA_VERSION
    created_at: str = ""
    synthetic: bool = False
    source: str = "unknown"
    provider: str = "unknown"
    seed: int | None = None
    disclaimer: str = ""
    datasets: dict[str, SnapshotDataset] = field(default_factory=dict)
    panel: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "synthetic": self.synthetic,
            "source": self.source,
            "provider": self.provider,
            "seed": self.seed,
            "disclaimer": self.disclaimer,
            "datasets": {name: item.to_dict() for name, item in sorted(self.datasets.items())},
            "panel": self.panel,
            "quality": self.quality,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def write(self, path: str | Path) -> None:
        target = Path(path)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(self.to_json(), encoding="utf-8")
        temporary.replace(target)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SnapshotManifest:
        return cls(
            snapshot_id=str(payload["snapshot_id"]),
            content_hash=str(payload["content_hash"]),
            schema_version=str(payload.get("schema_version", MANIFEST_SCHEMA_VERSION)),
            created_at=str(payload.get("created_at", "")),
            synthetic=bool(payload.get("synthetic", False)),
            source=str(payload.get("source", "unknown")),
            provider=str(payload.get("provider", "unknown")),
            seed=payload.get("seed"),
            disclaimer=str(payload.get("disclaimer", "")),
            datasets={
                name: SnapshotDataset.from_dict(item)
                for name, item in payload.get("datasets", {}).items()
            },
            panel=dict(payload.get("panel", {})),
            quality=dict(payload.get("quality", {})),
            metadata=dict(payload.get("metadata", {})),
        )

    @classmethod
    def read(cls, path: str | Path) -> SnapshotManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)
