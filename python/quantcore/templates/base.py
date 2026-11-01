"""Shared helpers for the built-in strategy templates."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..data.panel import PanelData
from ..strategy.base import PanelView, UniverseFilter, universe_mask
from ..strategy.expr import (
    cross_sectional_rank,
    cross_sectional_zscore,
    shift,
)


def daily_return(close: np.ndarray) -> np.ndarray:
    """Simple daily returns along the time axis; first row is NaN."""
    values = np.asarray(close, dtype=np.float64)
    previous = shift(values, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return values / previous - 1.0


def rolling_return(close: np.ndarray, window: int, skip: int = 0) -> np.ndarray:
    """Return over ``window`` days ending ``skip`` days before the decision date."""
    values = np.asarray(close, dtype=np.float64)
    if skip <= 0:
        past = shift(values, window)
    else:
        past = shift(values, window + skip)
        values = shift(values, skip)
    with np.errstate(divide="ignore", invalid="ignore"):
        return values / past - 1.0


def cs_zscore(values: np.ndarray) -> np.ndarray:
    return cross_sectional_zscore(np.asarray(values, dtype=np.float64))


def cs_rank(values: np.ndarray) -> np.ndarray:
    return cross_sectional_rank(np.asarray(values, dtype=np.float64))


def combine_scores(*matrices: np.ndarray, min_valid: int = 1) -> np.ndarray:
    """Sum z-scored factor matrices, ignoring missing cells (NaN stays NaN)."""
    if not matrices:
        raise ValueError("combine_scores needs at least one matrix")
    stacked = np.stack([np.asarray(matrix, dtype=np.float64) for matrix in matrices], axis=0)
    valid = np.isfinite(stacked).sum(axis=0)
    with np.errstate(invalid="ignore"):
        total = np.nansum(stacked, axis=0)
    return np.where(valid >= max(1, min_valid), total, np.nan)


def cs_quantile(values: np.ndarray, q: float) -> np.ndarray:
    """Per-row NaN-aware quantile; returns a ``(n_time,)`` threshold vector."""
    array = np.asarray(values, dtype=np.float64)
    out = np.full(array.shape[0], np.nan)
    for row in range(array.shape[0]):
        line = array[row]
        valid = line[np.isfinite(line)]
        if valid.size:
            out[row] = float(np.quantile(valid, q))
    return out


def pit_value_matrix(
    view: PanelView,
    column: str,
    *,
    annual_only: bool = True,
) -> np.ndarray:
    """Latest PIT financial *column* available at each decision date.

    Announcement dates become available on the **next trading day** (default PIT rule),
    so a strategy can never read a disclosure on the day it was announced.  Values are
    forward-filled until the next announcement.
    """
    n_time, n_sec = view.n_time, view.n_sec
    empty = np.full((n_time, n_sec), np.nan, dtype=np.float64)
    frame = view.financials()
    if frame.empty or column not in frame.columns:
        return empty
    if annual_only:
        frame = frame[frame["end_date"] % 10000 == 1231]
    frame = frame.dropna(subset=["ann_date"]).sort_values("ann_date", kind="stable")
    if frame.empty:
        return empty
    dates = view.dates
    sec_index = {str(sec): i for i, sec in enumerate(view.sec_ids)}
    positions = np.searchsorted(dates, frame["ann_date"].to_numpy(dtype=np.int64), side="right")
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=np.float64)
    matrix = empty.copy()
    for position, sec_id, value in zip(
        positions, frame["sec_id"].astype(str).tolist(), values, strict=False
    ):
        if position >= n_time or not np.isfinite(value):
            continue
        column_index = sec_index.get(sec_id)
        if column_index is None:
            continue
        matrix[int(position), column_index] = value
    filled = pd.DataFrame(matrix).ffill().to_numpy(dtype=np.float64)
    return filled


def select_targets(
    view: PanelView,
    flags: np.ndarray,
    mask: np.ndarray,
    score: np.ndarray | None = None,
    top_n: int | None = None,
    weighting: str = "equal",
) -> np.ndarray:
    """Build a target-weight matrix from per-date selection flags.

    ``flags`` is a ``(n_time,)`` boolean rebalance flag; ``mask`` is the eligible/selected
    security mask; ``score`` (optional) ranks candidates (higher is better).  Dates
    without a rebalance are ``NaN`` rows ("no rebalance"); dates with no eligible security
    are all-zero rows ("target cash").
    """
    n_time, n_sec = view.n_time, view.n_sec
    weights = np.full((n_time, n_sec), np.nan, dtype=np.float64)
    flag_array = np.asarray(flags, dtype=bool)
    mask_array = np.asarray(mask, dtype=bool)
    if mask_array.shape != (n_time, n_sec):
        raise ValueError(f"mask shape {mask_array.shape} != {(n_time, n_sec)}")
    score_array = None if score is None else np.asarray(score, dtype=np.float64)
    if score_array is not None and score_array.shape != (n_time, n_sec):
        raise ValueError(f"score shape {score_array.shape} != {(n_time, n_sec)}")
    if weighting not in {"equal", "score"}:
        raise ValueError(f"unsupported weighting: {weighting!r}")
    if weighting == "score" and score_array is None:
        raise ValueError("score weighting requires a score matrix")
    for day in np.flatnonzero(flag_array):
        eligible = mask_array[day].copy()
        if score_array is not None:
            eligible &= np.isfinite(score_array[day])
        chosen = np.flatnonzero(eligible)
        row = np.zeros(n_sec, dtype=np.float64)
        if chosen.size:
            if top_n is not None and chosen.size > top_n:
                assert score_array is not None
                ordering = np.argsort(-score_array[day, chosen], kind="stable")[:top_n]
                chosen = chosen[ordering]
            if weighting == "equal":
                row[chosen] = 1.0 / chosen.size
            else:
                assert score_array is not None
                raw = np.maximum(score_array[day, chosen], 0.0)
                total = float(raw.sum())
                row[chosen] = raw / total if total > 0 else 1.0 / chosen.size
        weights[day] = row
    return weights


def template_eligibility(view: PanelView, universe: UniverseFilter | None = None) -> np.ndarray:
    """Convenience wrapper around :func:`universe_mask`."""
    return universe_mask(view, universe)


def panel_synthetic_note(panel: PanelData) -> dict[str, Any]:
    """Provenance fragment embedded into template strategy metadata."""
    return {
        "synthetic": bool(panel.meta.get("synthetic", False)),
        "source": panel.meta.get("source", "unknown"),
    }
