"""Bridge to the C++ ``.qpanel`` writer/reader (``quantcore._qcore``).

The Python control plane never writes the binary format itself: :func:`write_qpanel`
requires ``_qcore.PanelWriter`` and fails with :class:`CppUnavailableError` when the
extension is not built.  Fields are written in ``time_sec`` layout (``n_time x n_sec``)
so the engine can consume them directly as target/price matrices.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .. import panel_available, require_panel
from ..data.panel import BOARD_CODES, PANEL_FIELDS, PanelData
from ..errors import CppUnavailableError, SnapshotError

QPANEL_LAYOUT = "time_sec"
QPANEL_SCHEMA_VERSION = "1"


def qpanel_available() -> bool:
    """True when the compiled extension exposes ``PanelWriter``/``Panel``."""
    return panel_available()


def _securities_payload(panel: PanelData) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for record in panel.securities.to_dict(orient="records"):
        payload.append(
            {
                "sec_id": str(record["sec_id"]),
                "code": str(record["code"]),
                "name": str(record["name"]),
                "board": int(BOARD_CODES.get(str(record["board"]), 0)),
                "list_date": int(record["list_date"] or 0),
                "delist_date": int(record["delist_date"] or 0),
            }
        )
    return payload


def write_qpanel(panel: PanelData, path: str | Path) -> dict[str, Any]:
    """Write ``panel`` as a ``.qpanel`` file through the C++ ``PanelWriter``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    module = require_panel()
    writer = module.PanelWriter(
        panel.n_sec,
        panel.n_time,
        [int(date) for date in panel.calendar.dates],
        _securities_payload(panel),
    )
    for field_name in PANEL_FIELDS:
        matrix = panel.matrix(field_name)
        data = np.ascontiguousarray(matrix, dtype=np.float64)
        writer.add_field(field_name, QPANEL_LAYOUT, data)
    metadata = panel.security_meta()
    metadata["qpanel_schema_version"] = QPANEL_SCHEMA_VERSION
    writer.set_metadata(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    writer.write(str(target))
    if not target.exists():
        raise SnapshotError(f".qpanel writer did not produce {target}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "file": target.name,
        "bytes": target.stat().st_size,
        "sha256": digest.hexdigest(),
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
        "layout": QPANEL_LAYOUT,
        "fields": list(PANEL_FIELDS),
        "writer": "_qcore.PanelWriter",
    }


def open_qpanel(path: str | Path) -> Any:
    """Open a ``.qpanel`` file with the C++ reader."""
    if not qpanel_available():
        raise CppUnavailableError("C++ .qpanel reader is not available; run `make build`")
    module = require_panel()
    return module.Panel.open(str(path))


def qpanel_field(panel_object: Any, name: str) -> np.ndarray:
    """Return a field matrix as ``(n_time, n_sec)`` float64, transposing if needed."""
    if not panel_object.has_field(name):
        raise SnapshotError(f".qpanel has no field {name!r}")
    data = np.asarray(panel_object.field(name))
    layout = getattr(panel_object, "field_layout", None)
    layout_value = str(layout(name)).lower() if callable(layout) else QPANEL_LAYOUT
    if layout_value in {"sec_time", "sectime"}:
        data = data.T
    return np.ascontiguousarray(data, dtype=np.float64)


def qpanel_matrix(panel_object: Any, field_name: str) -> np.ndarray:
    """Alias used by the snapshot reader for engine-layout matrices."""
    return qpanel_field(panel_object, field_name)
