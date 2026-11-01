"""Factor research: IC / RankIC / ICIR / quantile returns / decay / coverage.

All analytics here are *research only*: forward returns are used to evaluate a factor
signal, never to build one.  The factor itself is evaluated with the same causal
expression engine used by declarative strategies.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..data.panel import PanelData
from ..strategy.base import PanelView
from ..strategy.expr import evaluate_expression

#: Default horizons (trading days) for the factor-decay curve.
DEFAULT_DECAY_HORIZONS: tuple[int, ...] = (1, 2, 3, 5, 10, 20)
MIN_CROSS_SECTION = 5


def factor_matrix(panel: PanelData, expression: str) -> np.ndarray:
    """Evaluate ``expression`` into a ``(n_time, n_sec)`` factor matrix."""
    return evaluate_expression(expression, PanelView(panel))


def forward_returns(close: np.ndarray, days: int) -> np.ndarray:
    """Forward simple returns: ``close[t+days] / close[t] - 1`` (last rows NaN)."""
    if days < 1:
        raise ValueError("forward days must be >= 1")
    values = np.asarray(close, dtype=np.float64)
    future = np.full_like(values, np.nan)
    if days < values.shape[0]:
        future[:-days] = values[days:]
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where((values > 0) & (future > 0), future / values - 1.0, np.nan)
    return result


def tradable_mask(panel: PanelData) -> np.ndarray:
    """Rows where a factor can be evaluated: close finite, not suspended/ST."""
    close = panel.matrix("close")
    mask = np.isfinite(close) & (close > 0)
    mask &= panel.matrix("suspended") < 0.5
    mask &= panel.matrix("st") < 0.5
    return mask


def _pearson(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size < MIN_CROSS_SECTION:
        return None
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    if left_std <= 0 or right_std <= 0:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if np.isfinite(value) else None


def _spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size < MIN_CROSS_SECTION:
        return None
    left_rank = pd.Series(left).rank().to_numpy()
    right_rank = pd.Series(right).rank().to_numpy()
    return _pearson(left_rank, right_rank)


def _bucket_indices(values: np.ndarray, quantiles: int) -> np.ndarray:
    """Assign quantile buckets ``0..quantiles-1`` by rank; -1 marks missing."""
    buckets = np.full(values.shape, -1, dtype=np.int64)
    valid = np.flatnonzero(np.isfinite(values))
    if valid.size == 0:
        return buckets
    ranks = pd.Series(values[valid]).rank(method="first", pct=True).to_numpy()
    buckets[valid] = np.minimum((ranks * quantiles).astype(np.int64), quantiles - 1)
    return buckets


def _horizons(forward_days: int, decay_horizons: tuple[int, ...] | list[int] | None) -> list[int]:
    if decay_horizons:
        return sorted({int(value) for value in decay_horizons if int(value) >= 1})
    horizons = {1, 2, 3, max(1, forward_days)}
    horizons.update(h for h in DEFAULT_DECAY_HORIZONS if h <= max(20, forward_days * 2))
    return sorted(horizons)


def analyze_factor(
    panel: PanelData,
    expression: str,
    *,
    forward_days: int = 5,
    quantiles: int = 5,
    decay_horizons: tuple[int, ...] | list[int] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Compute IC / RankIC / ICIR / quantile returns / decay / coverage for a factor."""
    if forward_days < 1:
        raise ValueError("forward_days must be >= 1")
    if not 2 <= quantiles <= 20:
        raise ValueError("quantiles must be in [2, 20]")
    factor = factor_matrix(panel, expression)
    close = panel.matrix("close")
    base_mask = tradable_mask(panel)
    forward = forward_returns(close, forward_days)
    n_time, n_sec = panel.n_time, panel.n_sec

    ic_values: list[float] = []
    rank_ic_values: list[float] = []
    quantile_sum = np.zeros(quantiles)
    quantile_count = np.zeros(quantiles)
    observations = 0
    for day in range(n_time):
        valid = base_mask[day] & np.isfinite(factor[day]) & np.isfinite(forward[day])
        if int(valid.sum()) < MIN_CROSS_SECTION:
            continue
        factor_row = factor[day][valid]
        return_row = forward[day][valid]
        ic_value = _pearson(factor_row, return_row)
        rank_value = _spearman(factor_row, return_row)
        if ic_value is not None:
            ic_values.append(ic_value)
        if rank_value is not None:
            rank_ic_values.append(rank_value)
        observations += int(valid.sum())
        buckets = _bucket_indices(factor_row, quantiles)
        for bucket in range(quantiles):
            members = buckets == bucket
            if members.any():
                quantile_sum[bucket] += float(return_row[members].mean())
                quantile_count[bucket] += 1.0

    ic_series: list[dict[str, Any]] = []
    ic_pointer = 0
    rank_pointer = 0
    for day in range(n_time):
        valid = base_mask[day] & np.isfinite(factor[day]) & np.isfinite(forward[day])
        if int(valid.sum()) < MIN_CROSS_SECTION:
            continue
        ic_value = _pearson(factor[day][valid], forward[day][valid])
        rank_value = _spearman(factor[day][valid], forward[day][valid])
        entry: dict[str, Any] = {"date": int(panel.calendar.dates[day])}
        if ic_value is not None:
            entry["ic"] = round(ic_value, 8)
            ic_pointer += 1
        if rank_value is not None:
            entry["rank_ic"] = round(rank_value, 8)
            rank_pointer += 1
        if "ic" in entry or "rank_ic" in entry:
            ic_series.append(entry)

    ic_array = np.asarray(ic_values, dtype=np.float64)
    rank_array = np.asarray(rank_ic_values, dtype=np.float64)
    ic_std = float(np.std(ic_array, ddof=1)) if ic_array.size > 1 else 0.0
    icir = float(np.mean(ic_array) / ic_std) if ic_std > 1e-12 else 0.0

    quantile_returns = [
        {
            "bucket": bucket + 1,
            "mean_return": round(float(quantile_sum[bucket] / quantile_count[bucket]), 8)
            if quantile_count[bucket] > 0
            else 0.0,
            "observations": int(quantile_count[bucket]),
        }
        for bucket in range(quantiles)
    ]

    decay: list[dict[str, Any]] = []
    for horizon in _horizons(forward_days, decay_horizons):
        fwd = forward_returns(close, horizon)
        horizon_ics: list[float] = []
        horizon_rank_ics: list[float] = []
        for day in range(n_time):
            valid = base_mask[day] & np.isfinite(factor[day]) & np.isfinite(fwd[day])
            if int(valid.sum()) < MIN_CROSS_SECTION:
                continue
            value = _pearson(factor[day][valid], fwd[day][valid])
            if value is not None:
                horizon_ics.append(value)
            rank_value = _spearman(factor[day][valid], fwd[day][valid])
            if rank_value is not None:
                horizon_rank_ics.append(rank_value)
        decay.append(
            {
                "days": horizon,
                "ic": round(float(np.mean(horizon_ics)), 8) if horizon_ics else 0.0,
                "rank_ic": round(float(np.mean(horizon_rank_ics)), 8) if horizon_rank_ics else 0.0,
                "observations": len(horizon_ics),
            }
        )

    tradable_total = int(base_mask.sum())
    coverage = (
        float(np.sum(np.isfinite(factor) & base_mask)) / tradable_total if tradable_total else 0.0
    )
    return {
        "name": name or expression,
        "expression": expression,
        "forward_days": forward_days,
        "quantiles": quantiles,
        "ic_mean": round(float(np.mean(ic_array)), 8) if ic_array.size else 0.0,
        "rank_ic_mean": round(float(np.mean(rank_array)), 8) if rank_array.size else 0.0,
        "icir": round(icir, 8),
        "rank_icir": round(float(np.mean(rank_array) / np.std(rank_array, ddof=1)), 8)
        if rank_array.size > 1 and float(np.std(rank_array, ddof=1)) > 1e-12
        else 0.0,
        "ic_series": ic_series,
        "quantile_returns": quantile_returns,
        "decay": decay,
        "coverage": round(coverage, 6),
        "observations": observations,
        "periods": int(ic_array.size),
        "n_sec": n_sec,
    }


__all__ = [
    "analyze_factor",
    "factor_matrix",
    "forward_returns",
    "tradable_mask",
]
