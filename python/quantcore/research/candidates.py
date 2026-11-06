"""Offline fixed-parameter candidate studies; results are research artefacts, not promises."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..backtest.result import BacktestResult
from ..calendar import from_date_int, to_date_int
from ..data.panel import PanelData
from ..data.store import ParquetStore
from ..errors import ExperimentError
from ..experiments.runner import _load_panel_data, _save_panel_data, capture_environment
from ..experiments.store import ExperimentStore
from ..strategy.base import PanelView, universe_mask
from ..strategy.spec import StrategySpec

if TYPE_CHECKING:
    from ..experiments.runner import ReplayResult

BASELINE = "equal_weight_buy_hold"
COST_CASES = ("base", "stress")


def candidate_specs() -> list[StrategySpec]:
    """Predeclared parameters: no fitting or selection using development/holdout results."""
    parameters = {
        "trend_momentum": {
            "lookback": 252,
            "skip": 21,
            "trend_window": 200,
            "top_n": 3,
            "rebalance": "monthly",
        },
        "liquid_reversal": {
            "lookback": 5,
            "amount_lookback": 20,
            "liquidity_quantile": 0.5,
            "trend_lookback": 60,
            "top_n": 3,
            "rebalance": "weekly",
        },
        "defensive_low_vol": {
            "lookback": 60,
            "trend_lookback": 120,
            "top_n": 3,
            "rebalance": "monthly",
        },
    }
    return [
        StrategySpec(name=name, template=name, params=values) for name, values in parameters.items()
    ]


def _config(start: int, end: int, initial_cash: float, case: str) -> BacktestConfig:
    config = BacktestConfig(start=start, end=end, initial_cash=initial_cash)
    config.exec.slippage_bps = 5.0 if case == "base" else 10.0
    if case == "stress":
        for field in (
            "commission_rate",
            "min_commission",
            "stamp_duty_rate",
            "transfer_fee_rate",
            "exchange_fee_rate",
            "reg_fee_rate",
        ):
            setattr(config.costs, field, 2 * getattr(config.costs, field))
    return config


def _json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def _signal_hash(weights: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(weights, dtype="<f8").tobytes()).hexdigest()


def _phases(
    panel: PanelData,
    annual: bool,
    development_start: int | str = 20210101,
    holdout_start: int | str = 20230101,
) -> list[tuple[str, int, int]]:
    development_start, holdout_start = to_date_int(development_start), to_date_int(holdout_start)
    if development_start >= holdout_start:
        raise ValueError("development_start must be before holdout_start")
    development_end = to_date_int(from_date_int(holdout_start) - timedelta(days=1))
    phases = [
        ("development", development_start, development_end),
        ("holdout", holdout_start, int(panel.dates[-1])),
    ]
    if annual:
        phases.extend(
            (
                f"holdout_{year}",
                max(holdout_start, year * 10000 + 101),
                min(year * 10000 + 1231, int(panel.dates[-1])),
            )
            for year in range(holdout_start // 10000, int(panel.dates[-1]) // 10000 + 1)
        )
    selected = []
    for name, start, end in phases:
        dates = panel.dates[(panel.dates >= start) & (panel.dates <= end)]
        if len(dates) < 2:
            raise ValueError(f"{name} requires at least two trading days within {start}..{end}")
        selected.append((name, int(dates[0]), int(dates[-1])))
    return selected


def _warmup(valid: np.ndarray, index: int, sec_ids: list[str]) -> dict[str, Any]:
    trailing = np.cumprod(valid[:index][::-1], axis=0).sum(axis=0)
    return {
        "required_preceding_bars": 252,
        "available_preceding_rows": index,
        "valid_preceding_by_security": dict(zip(sec_ids, map(int, trailing), strict=True)),
        "sufficient": bool((trailing >= 252).all()),
    }


def _baseline(panel: PanelData, start: int) -> np.ndarray:
    weights = np.full((panel.n_time, panel.n_sec), np.nan)
    index = panel.calendar.index_of(start)
    eligible = universe_mask(PanelView(panel))[index]
    weights[index] = 0.0
    if eligible.any():
        weights[index, eligible] = 1.0 / int(eligible.sum())
    return weights


def _row(
    result: BacktestResult,
    phase: str,
    candidate: str,
    case: str,
    run_id: str,
    signal_hash: str,
    synthetic: bool,
) -> dict[str, Any]:
    metrics = result.metrics
    exposure = np.divide(
        result.market_value,
        result.equity,
        out=np.zeros(len(result.equity), dtype=float),
        where=result.equity > 0,
    )
    return {
        "phase": phase,
        "candidate": candidate,
        "cost_case": case,
        "run_id": run_id,
        "start": int(result.dates[0]),
        "end": int(result.dates[-1]),
        "total_return": float(metrics["total_return"]),
        "annualized_return": float(metrics["annualized_return"]),
        "sharpe": float(metrics["sharpe"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "fees_cny": float(metrics["total_fees"]) / 10000.0,
        "trade_count": int(metrics["trade_count"]),
        "average_exposure": float(exposure.mean()),
        "excess_equal_weight": None,
        "signal_hash": signal_hash,
        "engine_version": result.engine_version,
        "synthetic": synthetic,
    }


def _report(study: dict[str, Any]) -> str:
    label = "SYNTHETIC" if study["data"]["synthetic"] else "REAL DATA"
    windows = "; ".join(f"{p['name']} {p['start']}-{p['end']}" for p in study["phase_definitions"])
    parameters = json.dumps({s["name"]: s["params"] for s in study["candidate_specs"]})
    warmup = "; ".join(
        f"{p['name']}: {'sufficient' if p['warmup']['sufficient'] else 'INSUFFICIENT'} "
        f"(minimum {min(p['warmup']['valid_preceding_by_security'].values())} valid preceding bars)"
        for p in study["phase_definitions"]
    )
    header = f"""# Fixed candidate study: {label}

No parameters were fitted or selected from these results. No profitability claim is made. Synthetic results are software checks and cannot support investment conclusions.

Source: {study["data"]["source"]}; securities: {study["data"]["n_sec"]}; data range: {study["data"]["first_date"]}-{study["data"]["last_date"]}. Data hash: `{study["data"]["content_hash"]}`.
Predeclared dates: {json.dumps(study["date_protocol"], sort_keys=True)}.
Windows: {windows}.
Fixed parameters: {parameters}.
Warmup (252 valid preceding bars required): {warmup}. Insufficient history is not backfilled; affected candidates wait for complete trailing data.

Each window starts with separate flat capital and full-history causal warmup. Candidates wait for their own rebalance; the equal-weight control signals at each window start and executes next bar. Annual holdout windows also restart independently.
Base costs: defaults plus 5 bps slippage. Stress doubles commission, minimum commission, stamp duty, transfer, exchange and regulatory fees, with 10 bps slippage. Signals are identical.

| Window | Candidate | Costs | Return | Annualized | Sharpe | Max DD | Fees CNY | Trades | Mean exposure | Equal-weight excess |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
"""
    lines = []
    for row in study["results"]:
        lines.append(
            f"| {row['phase']} | {row['candidate']} | {row['cost_case']} | "
            f"{row['total_return']:.2%} | {row['annualized_return']:.2%} | {row['sharpe']:.3f} | "
            f"{row['max_drawdown']:.2%} | {row['fees_cny']:.2f} | {row['trade_count']} | "
            f"{row['average_exposure']:.2%} | {row['excess_equal_weight']:.2%} |"
        )
    footer = """Limitations: input-universe selection/survivorship, vendor adjustment and corporate-action coverage, liquidity and execution assumptions remain material. This is a fixed-candidate comparison, not a trained model or live-trading validation.
Unclosed holdings are marked at the final close; terminal liquidation costs are not added. Dividends use the pre-tax event model.
Replay uses persisted phase signals and compares saved equity, trades and metrics, including the window-start control intervention. Use standard experiment replay or `replay_candidate_run(ExperimentStore(output / 'experiments'), run_id)`.
"""
    return header + "\n".join(lines) + "\n\n" + footer


def run_candidate_study(
    source: PanelData | ParquetStore,
    output: str | Path,
    *,
    initial_cash: float = 1_000_000,
    annual_holdout: bool = False,
    development_start: int | str = 20210101,
    holdout_start: int | str = 20230101,
) -> dict[str, Any]:
    """Run fixed candidates through native C++, storing one shared panel and all signals."""
    panel = source.load_panel() if isinstance(source, ParquetStore) else source
    phases = _phases(panel, annual_holdout, development_start, holdout_start)
    protocol = {
        "development_start": to_date_int(development_start),
        "holdout_start": to_date_int(holdout_start),
    }
    close, factor = panel.matrix("close"), panel.matrix("adj_factor")
    valid = np.isfinite(close) & (close > 0) & np.isfinite(factor) & (factor > 0)
    warmups = {
        name: _warmup(valid, panel.calendar.index_of(start), panel.sec_id_list)
        for name, start, _ in phases
    }
    destination = Path(output)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("study output must be a new or empty directory")
    destination.mkdir(parents=True, exist_ok=True)
    synthetic = bool(panel.meta.get("synthetic")) or "SYNTHETIC" in set(panel.bars["source"])
    reference = {
        "content_hash": panel.content_hash(),
        "source": str(panel.meta.get("source", "unknown")),
        "synthetic": synthetic,
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
        "first_date": int(panel.dates[0]),
        "last_date": int(panel.dates[-1]),
        "universe": panel.securities[
            ["sec_id", "code", "name", "board", "list_date", "delist_date"]
        ].to_dict("records"),
    }
    _save_panel_data(panel, destination / "data")
    _json(destination / "data_reference.json", reference)
    environment = capture_environment()
    store = ExperimentStore(destination / "experiments")
    specs = candidate_specs()
    _json(
        destination / "protocol.json",
        {**protocol, "candidate_specs": [spec.to_dict() for spec in specs]},
    )
    signals = {spec.name: spec.load().generate_targets(panel) for spec in specs}
    signal_directory = destination / "signals"
    signal_directory.mkdir()
    for name, weights in signals.items():
        np.save(signal_directory / f"{name}.npy", weights, allow_pickle=False)
    specs.append(StrategySpec(name=BASELINE, template="buy_and_hold"))
    rows: list[dict[str, Any]] = []
    for phase, start, end in phases:
        baseline = _baseline(panel, start)
        baseline_file = signal_directory / f"{phase}_{BASELINE}.npy"
        np.save(baseline_file, baseline, allow_pickle=False)
        for spec in specs:
            weights = baseline if spec.name == BASELINE else signals[spec.name]
            signal_file = (
                baseline_file if spec.name == BASELINE else signal_directory / f"{spec.name}.npy"
            )
            digest = _signal_hash(weights)
            for case in COST_CASES:
                config = _config(start, end, initial_cash, case)
                snapshot = {**reference, "panel_dir": "../../data"}
                result = run_backtest(
                    panel,
                    weights,
                    config,
                    strategy_metadata={"spec": spec.to_dict(), "signal_hash": digest},
                    snapshot_metadata=snapshot,
                )
                if result.engine_backend != "cpp":
                    raise RuntimeError("candidate studies require the native C++ engine")
                metadata = {
                    "strategy": spec.to_dict(),
                    "strategy_name": spec.name,
                    "strategy_hash": spec.content_hash(),
                    "params": spec.validate_params(),
                    "phase": phase,
                    "date_protocol": protocol,
                    "warmup": warmups[phase],
                    "cost_case": case,
                    "config": config.to_dict(),
                    "snapshot": snapshot,
                    "data_reference": "../../data_reference.json",
                    "signal_hash": digest,
                    "phase_start_flat": True,
                    "replay_method": "quantcore.research.candidates.replay_candidate_run",
                    "engine_backend": result.engine_backend,
                    "engine_version": result.engine_version,
                    "environment": environment,
                    "metrics": result.metrics,
                    "synthetic": synthetic,
                    "status": "running",
                }
                run_id = store.create("candidate_study", metadata, content_hash=digest)
                directory = store.path(run_id)
                store.update_metadata(run_id, {"signals": os.path.relpath(signal_file, directory)})
                store.save_text(run_id, "strategy.yaml", spec.to_yaml())
                store.save_result(run_id, result)
                store.save_json(run_id, "summary.json", result.summary())
                store.update_metadata(run_id, {"status": "completed"})
                rows.append(_row(result, phase, spec.name, case, run_id, digest, synthetic))
    controls = {
        (row["phase"], row["cost_case"]): row["total_return"]
        for row in rows
        if row["candidate"] == BASELINE
    }
    for row in rows:
        row["excess_equal_weight"] = row["total_return"] - controls[row["phase"], row["cost_case"]]
    study = {
        "schema_version": 1,
        "data": reference,
        "initial_cash": initial_cash,
        "candidate_specs": [spec.to_dict() for spec in specs],
        "date_protocol": protocol,
        "phase_definitions": [
            {"name": name, "start": start, "end": end, "warmup": warmups[name]}
            for name, start, end in phases
        ],
        "selection_policy": "fixed_parameters_no_fitting_no_result_based_selection",
        "results": rows,
    }
    _json(destination / "results.json", study)
    for phase, _, _ in phases:
        _json(
            destination / "phases" / f"{phase}.json", [row for row in rows if row["phase"] == phase]
        )
    with (destination / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (destination / "report.md").write_text(_report(study), encoding="utf-8")
    return study


def replay_candidate_run(store: ExperimentStore, run_id: str) -> ReplayResult:
    """Replay persisted signals against the single shared panel with native C++."""
    from ..experiments.runner import ReplayResult

    record = store.get(run_id)
    metadata = record.metadata
    if record.kind != "candidate_study":
        raise ExperimentError("not a candidate-study run")
    panel = _load_panel_data(record.directory / metadata["snapshot"]["panel_dir"])
    if panel.content_hash() != metadata["snapshot"]["content_hash"]:
        raise ExperimentError("candidate-study panel content hash changed")
    weights = np.load(record.directory / metadata["signals"], allow_pickle=False)
    if _signal_hash(weights) != metadata["signal_hash"]:
        raise ExperimentError("candidate-study signal hash changed")
    fresh = run_backtest(
        panel,
        weights,
        BacktestConfig.from_dict(metadata["config"]),
        strategy_metadata={"spec": metadata["strategy"], "signal_hash": metadata["signal_hash"]},
        snapshot_metadata=metadata["snapshot"],
    )
    stored = store.load_result(run_id)
    checks = {
        "equity": np.array_equal(fresh.equity, stored.equity),
        "trades": fresh.trades.equals(stored.trades),
        "metrics": json.dumps(fresh.metrics, sort_keys=True)
        == json.dumps(stored.metrics, sort_keys=True),
    }
    return ReplayResult(
        run_id=run_id,
        matched=all(checks.values()),
        equity_match=checks["equity"],
        trades_match=checks["trades"],
        metrics_match=checks["metrics"],
        differences=[f"{key} differs" for key, matched in checks.items() if not matched],
        metadata={
            "engine_backend": fresh.engine_backend,
            "engine_version": fresh.engine_version,
            "signal_hash": metadata["signal_hash"],
        },
    )
