"""Data layer: synthetic panels, canonical schema, Parquet store, DuckDB, snapshots."""

from __future__ import annotations

from .panel import (
    BOARD_CODES,
    PANEL_FIELDS,
    SCHEMA_VERSION,
    PanelData,
    normalize_bars,
    normalize_corporate_actions,
    normalize_financials,
    normalize_securities,
)

__all__ = [
    "BOARD_CODES",
    "PANEL_FIELDS",
    "SCHEMA_VERSION",
    "PanelData",
    "normalize_bars",
    "normalize_corporate_actions",
    "normalize_financials",
    "normalize_securities",
]
