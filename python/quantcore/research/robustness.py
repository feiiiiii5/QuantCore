"""M7 robustness analytics: deflated Sharpe, PBO/CSCV, cost, Monte Carlo and capacity.

Everything is computed from persisted experiment artefacts (equity curve, trades, config and
the referenced snapshot).  Nothing is written back, no network is used and no order is placed.
"""

from __future__ import annotations

import itertools
import math
from statistics import NormalDist
from typing import Any

import numpy as np

from ..backtest.config import CostModelConfig
from ..backtest.engine import run_backtest
from ..experiments.store import ExperimentStore
from .experiment_data import (
    ResearchDataError,
    clean_returns,
    daily_returns,
    load_bundle,
    load_panel,
)

EULER_GAMMA = 0.5772156649015329
MIN_RETURNS = 30
COST_RATE_FIELDS = (
    "commission_rate",
    "stamp_duty_rate",
    "transfer_fee_rate",
    "exchange_fee_rate",
    "reg_fee_rate",
)


# --------------------------------------------------------------------------- helpers
def _norm_cdf(value: float) -> float:
    return NormalDist().cdf(value)


def _norm_ppf(quantile: float) -> float:
    clipped = min(max(float(quantile), 1e-12), 1.0 - 1e-12)
    return NormalDist().inv_cdf(clipped)


def sharpe_ratio(returns: np.ndarray, periods_per_year: int = 244) -> float:
    values = np.asarray(returns, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return 0.0
    std = float(np.std(values, ddof=1))
    if std <= 0:
        return 0.0
    return float(np.mean(values) / std * math.sqrt(float(periods_per_year)))


def _column_sharpe(matrix: np.ndarray, rows: np.ndarray) -> np.ndarray:
    sample = matrix[rows]
    mean = np.nanmean(sample, axis=0)
    std = np.nanstd(sample, axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        values = np.where(std > 0, mean / std, -np.inf)
    return np.asarray(values, dtype=np.float64)


def _moments(returns: np.ndarray) -> tuple[float, float]:
    values = np.asarray(returns, dtype=np.float64)
    mean = float(np.mean(values))
    centered = values - mean
    m2 = float(np.mean(centered**2))
    if m2 <= 0:
        return 0.0, 3.0
    skew = float(np.mean(centered**3) / m2**1.5)
    kurt = float(np.mean(centered**4) / m2**2)
    return skew, kurt


def deflated_sharpe_stats(
    returns: np.ndarray, n_trials: int = 1, periods_per_year: int = 244
) -> dict[str, Any]:
    """Bailey/López de Prado deflated Sharpe ratio (single-run approximation)."""
    values = np.asarray(returns, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < MIN_RETURNS:
        raise ResearchDataError(
            f"need at least {MIN_RETURNS} daily returns for a deflated Sharpe; got {values.size}"
        )
    trials = max(1, int(n_trials))
    count = int(values.size)
    std = float(np.std(values, ddof=1))
    if std <= 0:
        raise ResearchDataError("experiment returns have zero volatility")
    sr_period = float(np.mean(values) / std)
    sr_annual = sr_period * math.sqrt(float(periods_per_year))
    skew, kurt = _moments(values)
    # Sampling variance of the Sharpe estimator under a zero-mean null (approx).
    variance = (1.0 + 0.5 * sr_period**2) / max(count - 1, 1)
    if trials <= 1:
        expected_max = 0.0
    else:
        z_hi = _norm_ppf(1.0 - 1.0 / trials)
        z_lo = _norm_ppf(1.0 - 1.0 / (trials * math.e))
        expected_max = math.sqrt(variance) * ((1.0 - EULER_GAMMA) * z_hi + EULER_GAMMA * z_lo)
    denominator_sq = 1.0 - skew * sr_period + (kurt - 1.0) / 4.0 * sr_period**2
    denominator = math.sqrt(max(denominator_sq, 1e-12))
    z_stat = (sr_period - expected_max) * math.sqrt(max(count - 1, 1)) / denominator
    dsr = float(min(max(_norm_cdf(z_stat), 0.0), 1.0))
    if dsr >= 0.95:
        verdict = "robust"
    elif dsr >= 0.5:
        verdict = "inconclusive"
    else:
        verdict = "likely_overfit"
    return {
        "observations": count,
        "periods_per_year": int(periods_per_year),
        "sharpe": round(sr_annual, 6),
        "deflated_sharpe": round(dsr, 6),
        "expected_max_sharpe": round(expected_max * math.sqrt(float(periods_per_year)), 6),
        "n_trials": trials,
        "skew": round(skew, 6),
        "kurtosis": round(kurt, 6),
        "verdict": verdict,
    }


def compute_overfitting(store: ExperimentStore, run_id: str, n_trials: int = 1) -> dict[str, Any]:
    bundle = load_bundle(store, run_id)
    returns = clean_returns(bundle.result, minimum=MIN_RETURNS)
    stats = deflated_sharpe_stats(returns, n_trials, bundle.config.annual_days)
    return {"run_id": run_id, **stats}


# --------------------------------------------------------------------------- PBO
def _aligned_returns(store: ExperimentStore, run_ids: list[str]) -> tuple[list[int], np.ndarray]:
    maps: list[dict[int, float]] = []
    for run_id in run_ids:
        bundle = load_bundle(store, run_id)
        dates, returns = daily_returns(bundle.result)
        mapping = {
            int(date): float(value)
            for date, value in zip(dates.tolist(), returns.tolist(), strict=False)
            if math.isfinite(float(value))
        }
        maps.append(mapping)
    common = sorted(set.intersection(*[set(mapping) for mapping in maps]))
    matrix = np.asarray([[mapping[date] for mapping in maps] for date in common], dtype=np.float64)
    return common, matrix


def compute_pbo(store: ExperimentStore, run_ids: list[str], n_splits: int = 8) -> dict[str, Any]:
    """Combinatorially Symmetric Cross-Validation probability of backtest overfitting."""
    unique = list(dict.fromkeys(str(value) for value in run_ids))
    if len(unique) < 2:
        raise ResearchDataError("PBO needs at least two distinct experiment runs")
    splits = int(n_splits)
    if splits < 2 or splits > 20 or splits % 2 != 0:
        raise ResearchDataError("n_splits must be an even number between 2 and 20")
    _, matrix = _aligned_returns(store, unique)
    observations, strategies = matrix.shape
    if observations < splits * 2:
        raise ResearchDataError(
            f"runs share only {observations} return dates; at least {splits * 2} are required"
        )
    blocks = np.array_split(np.arange(observations), splits)
    combinations = list(itertools.combinations(range(splits), splits // 2))
    if not combinations:  # pragma: no cover - guarded by the even/range check
        raise ResearchDataError("not enough split combinations")
    selected_ranks: list[int] = []
    selected_lambdas: list[float] = []
    logits: list[list[float]] = []
    for combo in combinations:
        chosen = set(combo)
        train_rows = np.concatenate([blocks[index] for index in sorted(chosen)])
        test_rows = np.concatenate(
            [blocks[index] for index in range(splits) if index not in chosen]
        )
        train_sharpe = _column_sharpe(matrix, train_rows)
        best = 0 if not np.isfinite(train_sharpe).any() else int(np.nanargmax(train_sharpe))
        test_sharpe = _column_sharpe(matrix, test_rows)
        ranks = np.asarray(
            [1 + int(np.sum(test_sharpe > value + 1e-12)) for value in test_sharpe],
            dtype=np.int64,
        )
        # Algorithm 2.3(f,g) uses higher relative ranks for better OOS performance:
        # https://carmamaths.org/jon/backtest2.pdf
        # Keep public 1 = best ranks, but use tie midranks for the internal logit.
        tie_counts = np.asarray(
            [
                np.count_nonzero(np.isclose(test_sharpe, value, rtol=0, atol=1e-12))
                for value in test_sharpe
            ]
        )
        midranks = ranks + (tie_counts - 1) / 2.0
        omega = (strategies + 1 - midranks) / float(strategies + 1)
        combo_logits = [float(math.log(float(value) / (1.0 - float(value)))) for value in omega]
        logits.append(combo_logits)
        selected_ranks.append(int(ranks[best]))
        selected_lambdas.append(combo_logits[best])
    # Retain our <= 0 policy: an OOS median tie has not beaten the median.
    pbo = float(np.mean([1.0 if value <= 0.0 else 0.0 for value in selected_lambdas]))
    return {
        "run_ids": unique,
        "n_splits": splits,
        "combinations": len(combinations),
        "pbo": round(pbo, 6),
        "median_oos_rank": float(np.median(selected_ranks)),
        "logits": [[round(value, 6) for value in row] for row in logits],
    }


# --------------------------------------------------------------------------- costs
def _scaled_costs(costs: CostModelConfig, multiplier: float) -> CostModelConfig:
    updates: dict[str, float] = {
        field: float(getattr(costs, field)) * multiplier for field in COST_RATE_FIELDS
    }
    updates["min_commission"] = float(costs.min_commission) * multiplier
    return costs.model_copy(update=updates)


def _breakeven(points: list[dict[str, Any]]) -> float | None:
    ordered = sorted(
        ((float(point["multiplier"]), float(point["total_return"])) for point in points),
        key=lambda item: item[0],
    )
    for (m1, r1), (m2, r2) in itertools.pairwise(ordered):
        if r1 == 0:
            return m1
        if (r1 < 0 < r2) or (r1 > 0 > r2):
            span = r2 - r1
            if abs(span) < 1e-15:
                return m2
            return round(m1 + (0.0 - r1) * (m2 - m1) / span, 6)
    if ordered and ordered[-1][1] == 0:
        return ordered[-1][0]
    return None


def compute_cost_sensitivity(
    store: ExperimentStore,
    run_id: str,
    multipliers: list[float] | None = None,
    *,
    snapshots_root: str = "data/snapshots",
) -> dict[str, Any]:
    values = [0.0, 0.5, 1.0, 2.0, 3.0] if multipliers is None else list(multipliers)
    if not values or len(values) > 10:
        raise ResearchDataError("multipliers must contain between 1 and 10 values")
    cleaned: list[float] = []
    for value in values:
        number = float(value)
        if not math.isfinite(number) or number < 0 or number > 100:
            raise ResearchDataError("multipliers must be finite numbers in [0, 100]")
        cleaned.append(number)
    bundle = load_bundle(store, run_id)
    if bundle.spec is None:
        raise ResearchDataError(f"experiment {run_id} has no strategy spec to re-run")
    panel, snapshot = load_panel(bundle.record, snapshots_root)
    strategy = bundle.spec.load()
    weights = strategy.generate_targets(panel)
    target: Any = snapshot if snapshot is not None else panel
    points: list[dict[str, Any]] = []
    for multiplier in cleaned:
        config = bundle.config.model_copy(deep=True)
        config.costs = _scaled_costs(config.costs, multiplier)
        result = run_backtest(
            target,
            weights,
            config,
            strategy_metadata=bundle.spec.specification(),
            snapshot_metadata=dict(bundle.record.metadata.get("snapshot") or {}),
        )
        metrics = dict(result.metrics)
        points.append(
            {
                "multiplier": float(multiplier),
                "total_return": float(metrics.get("total_return", 0.0)),
                "annualized_return": float(metrics.get("annualized_return", 0.0)),
                "sharpe": float(metrics.get("sharpe", 0.0)),
                "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
                "total_fees": int(metrics.get("total_fees", 0)),
            }
        )
    return {
        "run_id": run_id,
        "points": points,
        "breakeven_multiplier": _breakeven(points),
    }


# --------------------------------------------------------------------------- Monte Carlo
def compute_monte_carlo(
    store: ExperimentStore,
    run_id: str,
    n_paths: int = 500,
    horizon: int = 250,
    *,
    block: int = 20,
    seed: int = 42,
) -> dict[str, Any]:
    paths_count = int(n_paths)
    days = int(horizon)
    if paths_count < 1 or paths_count > 5000:
        raise ResearchDataError("n_paths must be between 1 and 5000")
    if days < 1 or days > 5000:
        raise ResearchDataError("horizon must be between 1 and 5000")
    bundle = load_bundle(store, run_id)
    returns = clean_returns(bundle.result, minimum=block + 5)
    rng = np.random.default_rng(seed)
    max_start = returns.size - block
    terminal = np.empty(paths_count, dtype=np.float64)
    drawdowns = np.empty(paths_count, dtype=np.float64)
    paths: list[list[float]] = []
    for index in range(paths_count):
        pieces: list[np.ndarray] = []
        filled = 0
        while filled < days:
            start = int(rng.integers(0, max_start + 1))
            pieces.append(returns[start : start + block])
            filled += block
        sample = np.concatenate(pieces)[:days]
        wealth = np.cumprod(1.0 + sample)
        terminal[index] = float(wealth[-1] - 1.0)
        # The initial unit of capital is a peak before the first sampled return.
        peak = np.maximum(1.0, np.maximum.accumulate(wealth))
        drawdowns[index] = float(np.max(1.0 - wealth / peak))
        if index < min(paths_count, 50):
            paths.append([0.0, *[float(value - 1.0) for value in wealth]])
    return {
        "run_id": run_id,
        "n_paths": paths_count,
        "horizon": days,
        "terminal_return": {
            key: round(float(np.percentile(terminal, quantile)), 6)
            for key, quantile in (("p05", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95))
        },
        "max_drawdown": {
            key: round(float(np.percentile(drawdowns, quantile)), 6)
            for key, quantile in (("p05", 5), ("p50", 50), ("p95", 95))
        },
        "paths": paths,
    }


# --------------------------------------------------------------------------- capacity
def compute_capacity(
    store: ExperimentStore,
    run_id: str,
    adv_participation: float = 0.1,
    *,
    snapshots_root: str = "data/snapshots",
) -> dict[str, Any]:
    participation = float(adv_participation)
    if not 0.0 < participation <= 1.0:
        raise ResearchDataError("adv_participation must be in (0, 1]")
    bundle = load_bundle(store, run_id)
    trades = bundle.result.trades
    if trades.empty:
        raise ResearchDataError(f"experiment {run_id} has no trades to estimate capacity")
    panel, _ = load_panel(bundle.record, snapshots_root)
    notional = trades["amount_yuan"].astype(float)
    total_notional = float(notional.sum())
    days = int(np.asarray(bundle.result.dates).size)
    equity = np.asarray(bundle.result.equity_yuan, dtype=np.float64)
    average_equity = float(np.mean(equity)) if equity.size else 0.0
    if total_notional <= 0 or average_equity <= 0 or days <= 0:
        raise ResearchDataError(f"experiment {run_id} has no usable trade/equity data")
    daily_turnover = total_notional / average_equity / days
    if daily_turnover <= 0:  # pragma: no cover - guarded by the check above
        raise ResearchDataError(f"experiment {run_id} has zero turnover")

    sec_index = panel.sec_index()
    amount_matrix = panel.matrix("amount")
    codes = {
        str(record["sec_id"]): str(record.get("code", ""))
        for record in panel.securities.to_dict(orient="records")
    }
    traded = trades.groupby("sec_id", as_index=True)["amount_yuan"].sum()
    candidates: list[tuple[float, str, float, float]] = []  # capacity, sec_id, adv, share
    for sec_id, value in traded.items():
        index = sec_index.get(str(sec_id))
        if index is None or float(value) <= 0:
            continue
        column = amount_matrix[:, index]
        finite = column[np.isfinite(column) & (column > 0)]
        adv = float(np.mean(finite)) if finite.size else 0.0
        if adv <= 0:
            continue
        share = float(value) / total_notional
        capacity = participation * adv / (share * daily_turnover)
        candidates.append((capacity, str(sec_id), adv, share))
    if not candidates:
        raise ResearchDataError(
            f"experiment {run_id} has no traded security with snapshot ADV data"
        )
    capacity_cny, limiting_sec, _, _ = min(candidates, key=lambda item: item[0])
    average_adv = float(np.mean([item[2] for item in candidates]))
    return {
        "run_id": run_id,
        "capacity_cny": round(capacity_cny, 2),
        "participation": round(participation, 6),
        "avg_turnover": round(daily_turnover, 6),
        "avg_adv_cny": round(average_adv, 2),
        "limiting_sec": codes.get(limiting_sec, limiting_sec),
        "notes": (
            "Approximate capacity from snapshot ADV and trade-notional shares: "
            "capacity = participation * ADV / (trade_share * daily_turnover). "
            "Assumes linear participation and no market impact; research estimate only."
        ),
    }


__all__ = [
    "compute_capacity",
    "compute_cost_sensitivity",
    "compute_monte_carlo",
    "compute_overfitting",
    "compute_pbo",
    "deflated_sharpe_stats",
    "sharpe_ratio",
]
