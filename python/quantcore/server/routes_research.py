"""Research routes (M7 basics): factor diagnostics, sweep, walk-forward, attribution."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from ..backtest.config import BacktestConfig
from ..errors import CppUnavailableError, ExperimentError, QuantCoreError, StrategyValidationError
from ..experiments import ExperimentStore
from ..research.attribution import attribute_by_industry
from ..research.experiment_data import ResearchDataError
from ..research.factors import analyze_factor, analyze_factor_correlation
from ..research.robustness import (
    compute_capacity,
    compute_cost_sensitivity,
    compute_monte_carlo,
    compute_overfitting,
    compute_pbo,
)
from ..research.sweep import MAX_SWEEP_POINTS, run_api_sweep
from ..research.walk_forward import run_walk_forward
from ..snapshot.reader import Snapshot, find_snapshot
from .schemas import (
    AttributionRequest,
    CapacityRequest,
    CostSensitivityRequest,
    FactorCorrelationRequest,
    FactorRequest,
    MonteCarloRequest,
    OverfittingRequest,
    PBORequest,
    SweepRequest,
    WalkForwardRequest,
)
from .workspace import Workspace, json_safe


def _panel_with_snapshot(
    ctx: Workspace, reference: str | None
) -> tuple[Any, dict[str, Any], Snapshot | None]:
    panel, meta = ctx.panel(reference, allow_synthetic=True)
    snapshot: Snapshot | None = None
    try:
        snapshot = ctx.snapshot(reference)
    except (FileNotFoundError, QuantCoreError):
        snapshot = None
    if snapshot is None and reference:
        snapshot = find_snapshot(ctx.settings.snapshots_root, reference)
    return panel, meta, snapshot


def _bad_request(exc: Exception) -> HTTPException:
    if isinstance(exc, CppUnavailableError):
        return HTTPException(status_code=503, detail=f"engine unavailable: {exc}")
    return HTTPException(status_code=400, detail=str(exc))


def register_research_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.post("/api/research/factor")
    def factor(payload: FactorRequest) -> Any:
        panel, meta, _ = _panel_with_snapshot(ctx, payload.snapshot)
        try:
            report = analyze_factor(
                panel,
                payload.expression,
                forward_days=payload.forward_days,
                quantiles=payload.quantiles,
                name=payload.name,
            )
        except (StrategyValidationError, ValueError) as exc:
            raise _bad_request(exc) from exc
        report["snapshot"] = meta.get("snapshot_id")
        report["synthetic"] = bool(meta.get("synthetic", False))
        return json_safe(report)

    @app.post("/api/research/factor_correlation")
    def factor_correlation(payload: FactorCorrelationRequest) -> Any:
        panel, meta, _ = _panel_with_snapshot(ctx, payload.snapshot)
        try:
            report = analyze_factor_correlation(
                panel,
                list(payload.expressions),
                method=payload.method,
                start=payload.start,
                end=payload.end,
            )
        except (StrategyValidationError, ValueError) as exc:
            raise _bad_request(exc) from exc
        report["snapshot"] = meta.get("snapshot_id")
        report["synthetic"] = bool(meta.get("synthetic", False))
        return json_safe(report)

    @app.post("/api/research/sweep")
    def sweep(payload: SweepRequest) -> Any:
        panel, meta, _ = _panel_with_snapshot(ctx, payload.snapshot)
        config = BacktestConfig(
            start=payload.start, end=payload.end, initial_cash=payload.initial_cash
        )
        try:
            report = run_api_sweep(
                panel,
                payload.template,
                payload.param_grid,
                config=config,
                workers=payload.workers,
                sample_size=payload.sample_size,
                mode=payload.mode,
                seed=payload.seed,
            )
        except (QuantCoreError, StrategyValidationError, ValueError) as exc:
            raise _bad_request(exc) from exc
        report["snapshot"] = meta.get("snapshot_id")
        report["synthetic"] = bool(meta.get("synthetic", False))
        report["bounded_points"] = MAX_SWEEP_POINTS
        return json_safe(report)

    @app.post("/api/research/walk_forward")
    def walk_forward(payload: WalkForwardRequest) -> Any:
        panel, meta, snapshot = _panel_with_snapshot(ctx, payload.snapshot)
        try:
            report = run_walk_forward(
                panel,
                payload.template,
                payload.params,
                folds=payload.folds,
                initial_cash=payload.initial_cash,
                snapshot=snapshot,
            )
        except (QuantCoreError, StrategyValidationError, ValueError) as exc:
            raise _bad_request(exc) from exc
        report["snapshot"] = meta.get("snapshot_id")
        report["synthetic"] = bool(meta.get("synthetic", False))
        return json_safe(report)

    @app.post("/api/research/attribution")
    def attribution(payload: AttributionRequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            record = store.get(payload.run_id)
            result = store.load_result(payload.run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        snapshot_info = record.metadata.get("snapshot") or {}
        panel = None
        if snapshot_info.get("snapshot_id"):
            try:
                snapshot = find_snapshot(
                    str(snapshot_info.get("snapshot_root") or ctx.settings.snapshots_root),
                    str(snapshot_info["snapshot_id"]),
                )
                panel = snapshot.to_panel_data()
            except (FileNotFoundError, QuantCoreError) as exc:
                raise HTTPException(
                    status_code=409, detail=f"snapshot unavailable for attribution: {exc}"
                ) from exc
        else:
            panel_dir = record.directory / str(snapshot_info.get("panel_dir", "panel"))
            if not (panel_dir / "bars.parquet").exists():
                raise HTTPException(
                    status_code=409,
                    detail="experiment has no snapshot or persisted panel for attribution",
                )
            from ..experiments.runner import _load_panel_data

            panel = _load_panel_data(panel_dir)
        report = attribute_by_industry(result, panel)
        report.update(
            {
                "run_id": payload.run_id,
                "strategy_name": record.metadata.get("strategy_name"),
                "synthetic": bool(record.metadata.get("synthetic", False)),
            }
        )
        return json_safe(report)

    # -- M7 robustness: overfitting / PBO / costs / Monte Carlo / capacity -------------
    @app.post("/api/research/overfitting")
    def overfitting(payload: OverfittingRequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            return json_safe(compute_overfitting(store, payload.run_id, payload.n_trials))
        except (ResearchDataError, ValueError) as exc:
            raise _bad_request(exc) from exc

    @app.post("/api/research/pbo")
    def pbo(payload: PBORequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            return json_safe(compute_pbo(store, list(payload.run_ids), payload.n_splits))
        except (ResearchDataError, ValueError) as exc:
            raise _bad_request(exc) from exc

    @app.post("/api/research/cost_sensitivity")
    def cost_sensitivity(payload: CostSensitivityRequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            return json_safe(
                compute_cost_sensitivity(
                    store,
                    payload.run_id,
                    payload.multipliers,
                    snapshots_root=str(ctx.settings.snapshots_root),
                )
            )
        except (ResearchDataError, ValueError) as exc:
            raise _bad_request(exc) from exc

    @app.post("/api/research/monte_carlo")
    def monte_carlo(payload: MonteCarloRequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            return json_safe(
                compute_monte_carlo(store, payload.run_id, payload.n_paths, payload.horizon)
            )
        except (ResearchDataError, ValueError) as exc:
            raise _bad_request(exc) from exc

    @app.post("/api/research/capacity")
    def capacity(payload: CapacityRequest) -> Any:
        store = ExperimentStore(ctx.settings.experiments_root)
        try:
            return json_safe(
                compute_capacity(
                    store,
                    payload.run_id,
                    payload.adv_participation,
                    snapshots_root=str(ctx.settings.snapshots_root),
                )
            )
        except (ResearchDataError, ValueError) as exc:
            raise _bad_request(exc) from exc
