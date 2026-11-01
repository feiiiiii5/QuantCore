"""Minute-bar canonical schema and deterministic synthetic intraday bars (M8-002).

The C++ engine remains daily-bar driven; this module provides a local, synthetic minute
view derived from a snapshot's daily OHLC so the data layer/API can be developed and
tested without a vendor intraday feed.  Every row is labelled SYNTHETIC.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..errors import DataValidationError
from .panel import PanelData

MINUTE_BAR_COLUMNS: dict[str, str] = {
    "datetime": "int64",
    "date": "int32",
    "sec_id": "object",
    "code": "object",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
    "amount": "float64",
    "source": "object",
}

# A-share trading sessions represented by five synthetic intraday buckets.
INTRADAY_TIMES: tuple[int, ...] = (930, 1030, 1130, 1400, 1500)
VOLUME_WEIGHTS: tuple[float, ...] = (0.16, 0.22, 0.17, 0.20, 0.25)


def _daily_row(panel: PanelData, sec: int, day: int) -> dict[str, float]:
    def value(field: str) -> float:
        column = panel.matrix(field)[day, sec] if field in panel.bars.columns else np.nan
        return float(column)

    return {
        "open": value("open"),
        "high": value("high"),
        "low": value("low"),
        "close": value("close"),
        "volume": value("volume"),
        "amount": value("amount"),
    }


def synthetic_minute_bars(
    panel: PanelData,
    code: str,
    date: int | str | None = None,
    *,
    seed: int = 42,
) -> pd.DataFrame:
    """Split one synthetic daily bar into deterministic 5-minute buckets.

    The split preserves the daily open/close/volume/amount and keeps each minute bar's
    OHLC internally consistent.  It is explicitly synthetic, not an intraday vendor feed.
    """
    securities = panel.securities.reset_index(drop=True)
    matches = securities[securities["code"].astype(str) == str(code)]
    if matches.empty:
        raise DataValidationError(f"unknown security code: {code!r}")
    sec = int(matches.index[0])
    dates = [int(value) for value in panel.calendar.dates]
    if date is None:
        day = len(dates) - 1
    else:
        target = int(str(date).replace("-", ""))
        if target not in dates:
            raise DataValidationError(f"date {target} is not in the snapshot calendar")
        day = dates.index(target)
    if day < 0 or day >= len(dates):
        raise DataValidationError("minute-bar date is outside the snapshot")
    row = _daily_row(panel, sec, day)
    if not np.isfinite([row["open"], row["high"], row["low"], row["close"]]).all():
        raise DataValidationError(f"daily bar for {code} on {dates[day]} is incomplete")
    rng = np.random.default_rng(int(seed) + day * 131 + sec)
    open_px = max(row["open"], 0.01)
    close_px = max(row["close"], 0.01)
    high = max(row["high"], open_px, close_px)
    low = min(row["low"], open_px, close_px)
    anchor = np.linspace(open_px, close_px, len(INTRADAY_TIMES) + 1)
    volume_total = max(int(row["volume"]), 0)
    amount_total = max(float(row["amount"]), 0.0)
    volumes = np.floor(np.asarray(VOLUME_WEIGHTS) * volume_total).astype(np.int64)
    volumes[-1] = max(0, volume_total - int(volumes[:-1].sum()))
    records: list[dict[str, Any]] = []
    for index, time in enumerate(INTRADAY_TIMES):
        bucket_open = float(anchor[index])
        bucket_close = float(anchor[index + 1])
        wiggle = float(rng.uniform(-0.003, 0.003)) * (high - low if high > low else open_px * 0.01)
        bucket_high = min(high, max(bucket_open, bucket_close) + abs(wiggle))
        bucket_low = max(low, min(bucket_open, bucket_close) - abs(wiggle))
        volume = int(volumes[index])
        if amount_total > 0 and volume_total > 0:
            amount = amount_total * volume / volume_total
        else:
            amount = volume * (bucket_open + bucket_close) / 2.0
        records.append(
            {
                "datetime": int(f"{dates[day]:08d}{time:04d}"),
                "date": dates[day],
                "sec_id": str(matches.iloc[0]["sec_id"]),
                "code": str(code),
                "open": round(bucket_open, 2),
                "high": round(max(bucket_high, bucket_open, bucket_close), 2),
                "low": round(min(bucket_low, bucket_open, bucket_close), 2),
                "close": round(bucket_close, 2),
                "volume": volume,
                "amount": round(amount, 2),
                "source": "SYNTHETIC_MINUTE",
            }
        )
    frame = pd.DataFrame.from_records(records)
    return frame[list(MINUTE_BAR_COLUMNS)].astype(MINUTE_BAR_COLUMNS)


__all__ = ["INTRADAY_TIMES", "MINUTE_BAR_COLUMNS", "synthetic_minute_bars"]
