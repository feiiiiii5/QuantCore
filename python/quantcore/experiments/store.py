"""Experiment storage: immutable run directories with metadata and Parquet artefacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..backtest.result import BacktestResult
from ..errors import ExperimentError


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ExperimentRecord:
    run_id: str
    kind: str
    directory: Path
    metadata: dict[str, Any]

    @property
    def created_at(self) -> str:
        return str(self.metadata.get("created_at", ""))

    @property
    def status(self) -> str:
        return str(self.metadata.get("status", "unknown"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "directory": str(self.directory),
            "metadata": self.metadata,
        }


class ExperimentStore:
    """File-system experiment store (``experiments/<run_id>/``)."""

    def __init__(self, root: str | Path = "experiments") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        return self.root / run_id

    # -- create / load ----------------------------------------------------
    def create(
        self,
        kind: str,
        metadata: dict[str, Any],
        *,
        run_id: str | None = None,
        content_hash: str | None = None,
    ) -> str:
        """Create a new experiment directory and write its metadata."""
        if run_id is None:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            suffix = (content_hash or "0")[:8]
            candidate = f"{kind}_{stamp}_{suffix}"
            index = 1
            while self.path(candidate).exists():
                index += 1
                candidate = f"{kind}_{stamp}_{suffix}_{index}"
            run_id = candidate
        directory = self.path(run_id)
        if directory.exists():
            raise ExperimentError(f"experiment already exists: {run_id}")
        directory.mkdir(parents=True)
        payload = dict(metadata)
        payload.setdefault("created_at", _now())
        payload.setdefault("status", "created")
        payload["run_id"] = run_id
        payload["kind"] = kind
        self._write_metadata(directory, payload)
        return run_id

    def _write_metadata(self, directory: Path, payload: dict[str, Any]) -> None:
        target = directory / "metadata.json"
        temporary = directory / f".metadata.{datetime.now(UTC).timestamp()}.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(target)

    def update_metadata(self, run_id: str, updates: dict[str, Any]) -> ExperimentRecord:
        record = self.get(run_id)
        payload = {**record.metadata, **updates, "updated_at": _now()}
        self._write_metadata(self.path(run_id), payload)
        return ExperimentRecord(
            run_id=run_id,
            kind=str(payload.get("kind", record.kind)),
            directory=record.directory,
            metadata=payload,
        )

    def get(self, run_id: str) -> ExperimentRecord:
        directory = self.path(run_id)
        metadata_path = directory / "metadata.json"
        if not metadata_path.exists():
            raise ExperimentError(f"experiment not found: {run_id}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return ExperimentRecord(
            run_id=run_id,
            kind=str(metadata.get("kind", "unknown")),
            directory=directory,
            metadata=metadata,
        )

    def list(self, kind: str | None = None, limit: int = 100) -> list[ExperimentRecord]:
        records: list[ExperimentRecord] = []
        if not self.root.exists():
            return records
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or not (directory / "metadata.json").exists():
                continue
            try:
                record = self.get(directory.name)
            except (ExperimentError, json.JSONDecodeError):
                continue
            if kind is not None and record.kind != kind:
                continue
            records.append(record)
        records.sort(key=lambda item: item.metadata.get("created_at", ""), reverse=True)
        return records[:limit]

    # -- artefacts --------------------------------------------------------
    def save_result(self, run_id: str, result: BacktestResult) -> Path:
        directory = self.path(run_id) / "result"
        result.to_parquet(directory)
        return directory

    def load_result(self, run_id: str) -> BacktestResult:
        directory = self.path(run_id) / "result"
        if not (directory / "equity.parquet").exists():
            raise ExperimentError(f"experiment {run_id} has no saved backtest result")
        return BacktestResult.from_parquet(directory)

    def save_json(self, run_id: str, name: str, payload: dict[str, Any]) -> Path:
        target = self.path(run_id) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def save_text(self, run_id: str, name: str, text: str) -> Path:
        target = self.path(run_id) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def read_text(self, run_id: str, name: str) -> str:
        target = self.path(run_id) / name
        if not target.exists():
            raise ExperimentError(f"experiment {run_id} has no artefact {name!r}")
        return target.read_text(encoding="utf-8")

    def delete(self, run_id: str) -> None:
        directory = self.path(run_id)
        if not directory.exists():
            raise ExperimentError(f"experiment not found: {run_id}")
        shutil.rmtree(directory)
