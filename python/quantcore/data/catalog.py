"""V2 dataset catalog (M8-005): canonical names, grains, versions and schemas.

The catalog is descriptive: it makes the supported offline datasets explicit for the API,
UI and docs. Daily bars/ETF/metadata are local snapshot data; minute bars are synthetic in
this release (no vendor intraday feed is bundled).
"""

from __future__ import annotations

from typing import Any

from .minute import MINUTE_BAR_COLUMNS
from .panel import (
    BARS_COLUMNS,
    CORPORATE_ACTION_COLUMNS,
    FINANCIAL_COLUMNS,
    SECURITY_COLUMNS,
)

CATALOG_VERSION = "v2"

DATASETS: tuple[dict[str, Any], ...] = (
    {
        "name": "daily_bars",
        "version": CATALOG_VERSION,
        "grain": "security/day",
        "storage": "parquet + qpanel",
        "synthetic": False,
        "fields": sorted(BARS_COLUMNS),
        "description": "Canonical adjusted daily OHLCV/amount/limit/suspension/ST fields.",
    },
    {
        "name": "minute_bars",
        "version": CATALOG_VERSION,
        "grain": "security/intraday-bucket",
        "storage": "synthetic API view",
        "synthetic": True,
        "fields": sorted(MINUTE_BAR_COLUMNS),
        "description": "Synthetic five-bucket minute view derived from daily bars (no vendor feed).",
    },
    {
        "name": "securities",
        "version": CATALOG_VERSION,
        "grain": "security",
        "storage": "parquet/json",
        "synthetic": False,
        "fields": sorted(SECURITY_COLUMNS),
        "description": "Security master including board, sec_type (STOCK/ETF/CONVERTIBLE), listing dates.",
    },
    {
        "name": "financials",
        "version": CATALOG_VERSION,
        "grain": "security/report",
        "storage": "parquet/json",
        "synthetic": False,
        "fields": sorted(FINANCIAL_COLUMNS),
        "description": "PIT financial statements keyed by ann_date/f_ann_date.",
    },
    {
        "name": "corporate_actions",
        "version": CATALOG_VERSION,
        "grain": "security/ex-date",
        "storage": "parquet/json",
        "synthetic": False,
        "fields": sorted(CORPORATE_ACTION_COLUMNS),
        "description": "Cash dividends, splits and rights adjustments.",
    },
    {
        "name": "snapshots",
        "version": CATALOG_VERSION,
        "grain": "immutable snapshot",
        "storage": "manifest.json + .qpanel",
        "synthetic": None,
        "fields": ["snapshot_id", "content_hash", "created_at", "synthetic", "quality"],
        "description": "Content-addressed immutable snapshots with quality reports and PIT metadata.",
    },
)


def catalog_payload() -> dict[str, Any]:
    """Dataset descriptors for ``GET /api/data/catalog``."""
    return {
        "version": CATALOG_VERSION,
        "datasets": [dict(dataset) for dataset in DATASETS],
        "notes": [
            "minute_bars is SYNTHETIC in this build; no vendor intraday feed is bundled.",
            "Daily backtests and the C++ engine remain daily-bar driven.",
            "All synthetic rows carry a `source` label and snapshots carry `synthetic=true`.",
        ],
    }


__all__ = ["CATALOG_VERSION", "DATASETS", "catalog_payload"]
