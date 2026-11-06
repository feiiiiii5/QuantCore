"""Read legacy warehouse metadata without importing application jobs or other state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

WAREHOUSE_META_KEYS = ("panel_meta", "last_ingest", "ingest_identity")


def legacy_warehouse_metadata(
    root: Path, dataset_hashes: dict[str, str], state_path: Path
) -> dict[str, Any]:
    """Accept metadata only from a database describing these exact warehouse files."""
    if not dataset_hashes:
        return {}
    entries: dict[str, tuple[str, Any]] = {}
    paths = {
        state_path.resolve(),
        (root / "state.sqlite").resolve(),
        (root.parent / "state.sqlite").resolve(),
    }
    for path in paths:
        if not path.is_file():
            continue
        try:
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                connection.row_factory = sqlite3.Row
                datasets = {
                    row["name"]: row
                    for row in connection.execute("SELECT name, path, content_hash FROM datasets")
                }
                if not all(
                    name in datasets
                    and datasets[name]["content_hash"] == digest
                    and Path(datasets[name]["path"]).resolve()
                    == (root / f"dataset={name}").resolve()
                    for name, digest in dataset_hashes.items()
                ):
                    continue
                placeholders = ",".join("?" for _ in WAREHOUSE_META_KEYS)
                for row in connection.execute(
                    f"SELECT key, value, updated_at FROM meta WHERE key IN ({placeholders})",
                    WAREHOUSE_META_KEYS,
                ):
                    prior = entries.get(row["key"])
                    if prior is None or row["updated_at"] > prior[0]:
                        entries[row["key"]] = (row["updated_at"], json.loads(row["value"]))
        except (sqlite3.DatabaseError, json.JSONDecodeError):
            continue
    return {key: value for key, (_, value) in entries.items()}
