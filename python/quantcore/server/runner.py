"""Job runners for the local API: backtest, data update and snapshot build.

Runners accept an optional :class:`~quantcore.jobs.queue.JobContext` so they can report
coarse progress (0.05 / 0.2 / 0.55 / 0.8 / 1.0) and honour cooperative cancellation
between heavy stages.  Backtests are persisted as experiments so the experiments pages,
replay and export all see the same artefacts as CLI runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..data.panel import PanelData
from ..data.state import SQLiteState
from ..data.store import ParquetStore
from ..data.synthetic import SyntheticConfig, generate_synthetic_panel
from ..experiments import ExperimentStore, capture_environment
from ..ingest import ProviderIngestor
from ..jobs.queue import JobContext
from ..providers import create_provider
from ..report import render_html_report
from ..snapshot.builder import build_snapshot_from_store
from ..snapshot.reader import Snapshot, find_snapshot
from ..strategy.spec import StrategySpec


def _progress(value: float, ctx: JobContext | None = None) -> None:
    if ctx is not None:
        ctx.update_progress(value)


def _check(ctx: JobContext | None = None) -> None:
    if ctx is not None:
        ctx.raise_if_cancelled()


def _panel_spec(payload: dict[str, Any]) -> SyntheticConfig:
    synthetic = dict(payload.get("synthetic") or {})
    return SyntheticConfig(
        n_sec=int(synthetic.get("n_sec", payload.get("n_sec", 40))),
        start=str(synthetic.get("start", payload.get("start", "2023-01-03"))),
        end=str(synthetic.get("end", payload.get("end", "2024-12-29"))),
        seed=int(synthetic.get("seed", payload.get("seed", 42))),
    )


def _snapshot_reference(snapshot: Snapshot | None, panel: PanelData | None) -> dict[str, Any]:
    if snapshot is not None:
        metadata = snapshot.manifest.metadata
        return {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_root": str(snapshot.root.parent),
            "content_hash": snapshot.manifest.content_hash,
            "synthetic": snapshot.manifest.synthetic,
            "source": snapshot.manifest.source,
            "n_sec": metadata.get("n_sec"),
            "n_time": metadata.get("n_time"),
        }
    assert panel is not None
    return {
        "snapshot_id": None,
        "panel_dir": "panel",
        "content_hash": panel.content_hash(),
        "synthetic": bool(panel.meta.get("synthetic", False)),
        "source": panel.meta.get("source", "unknown"),
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
    }


def _save_panel(panel: PanelData, directory: Path) -> None:
    """Persist a synthetic panel inside the experiment so replay works without a snapshot."""
    directory.mkdir(parents=True, exist_ok=True)
    panel.bars.to_parquet(directory / "bars.parquet", index=False)
    panel.securities.to_parquet(directory / "securities.parquet", index=False)
    pd.DataFrame({"date": list(panel.calendar.dates)}).to_parquet(
        directory / "calendar.parquet", index=False
    )
    if not panel.financials.empty:
        panel.financials.to_parquet(directory / "financials.parquet", index=False)
    if not panel.corporate_actions.empty:
        panel.corporate_actions.to_parquet(directory / "corporate_actions.parquet", index=False)
    (directory / "meta.json").write_text(
        json.dumps(panel.meta, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _persist_backtest_experiment(
    store: ExperimentStore,
    spec: StrategySpec,
    result: Any,
    *,
    snapshot: Snapshot | None,
    panel: PanelData | None,
    config: BacktestConfig,
    plugin_name: str | None = None,
) -> Any:
    """Persist a backtest result in the experiment store (UI + replay compatible)."""
    reference = _snapshot_reference(snapshot, panel)
    synthetic = bool(reference.get("synthetic", False))
    metadata: dict[str, Any] = {
        "strategy": spec.to_dict(),
        "strategy_name": spec.name,
        "strategy_hash": spec.content_hash(),
        "params": spec.params,
        "snapshot": reference,
        "config": config.to_dict(),
        "seed": config.seed,
        "engine_backend": result.engine_backend,
        "engine_version": result.engine_version,
        "environment": capture_environment(),
        "metrics": result.metrics,
        "synthetic": synthetic,
        "status": "completed",
    }
    if plugin_name:
        metadata["plugin"] = str(plugin_name)
    run_id = store.create("backtest", metadata, content_hash=spec.content_hash())
    store.save_text(run_id, "strategy.yaml", spec.to_yaml())
    if snapshot is None and panel is not None:
        _save_panel(panel, store.path(run_id) / "panel")
    store.save_result(run_id, result)
    snapshot_meta = snapshot.describe() if snapshot is not None else reference
    report_path = store.path(run_id) / "report.html"
    render_html_report(
        result,
        output_path=report_path,
        strategy_metadata=metadata["strategy"],
        snapshot_metadata=snapshot_meta,
    )
    summary = result.summary()
    summary["report"] = str(report_path)
    store.save_json(run_id, "summary.json", summary)
    return store.get(run_id)


def run_backtest_job(payload: dict[str, Any], ctx: JobContext | None = None) -> dict[str, Any]:
    """Run a research backtest, persist it as an experiment, return the compact summary."""
    _check(ctx)
    _progress(0.05, ctx)
    experiments_root = Path(
        payload.get("experiments_root") or payload.get("default_experiments_root") or "experiments"
    )
    store = ExperimentStore(experiments_root)
    config = BacktestConfig.model_validate(payload.get("config") or {})
    strategy_payload = payload.get("strategy")
    if strategy_payload is not None:
        spec = StrategySpec.model_validate(strategy_payload)
    else:
        template = payload.get("template")
        if not template:
            raise ValueError("backtest requires 'template' or 'strategy'")
        spec = StrategySpec(
            name=str(template), template=str(template), params=dict(payload.get("params") or {})
        )
    snapshot_ref = payload.get("snapshot")
    snapshots_root = Path(
        payload.get("snapshots_root") or payload.get("default_snapshots_root") or "data/snapshots"
    )
    plugin_name = payload.get("plugin")
    snapshot: Snapshot | None = None
    panel: PanelData | None = None
    if snapshot_ref:
        snapshot = find_snapshot(snapshots_root, str(snapshot_ref))
        panel = snapshot.to_panel_data()
        target: Any = snapshot
    else:
        panel = generate_synthetic_panel(_panel_spec(payload))
        target = panel
    _progress(0.2, ctx)
    _check(ctx)
    strategy = spec.load()
    _progress(0.35, ctx)
    weights = strategy.generate_targets(panel)
    _progress(0.55, ctx)
    _check(ctx)
    result = run_backtest(
        target,
        weights,
        config,
        strategy_metadata=spec.specification(),
        snapshot_metadata=_snapshot_reference(snapshot, panel),
    )
    _progress(0.8, ctx)
    _check(ctx)
    record = _persist_backtest_experiment(
        store,
        spec,
        result,
        snapshot=snapshot,
        panel=panel,
        config=config,
        plugin_name=str(plugin_name) if plugin_name else None,
    )
    _progress(0.95, ctx)
    summary_path = record.directory / "summary.json"
    summary: dict[str, Any] = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )
    _progress(1.0, ctx)
    return {
        "kind": "backtest",
        "run_id": record.run_id,
        "engine_backend": summary.get("engine_backend", result.engine_backend),
        "engine_version": summary.get("engine_version", result.engine_version),
        "trade_count": summary.get("trade_count", len(result.trades)),
        "final_equity": summary.get(
            "final_equity", result.equity_yuan[-1] if len(result.equity) else 0.0
        ),
        "metrics": summary.get("metrics", result.metrics),
        "snapshot": summary.get("snapshot", _snapshot_reference(snapshot, panel)),
        "synthetic": summary.get(
            "synthetic", bool(_snapshot_reference(snapshot, panel).get("synthetic", False))
        ),
        "seed": summary.get("seed", config.seed),
        "report": str(record.directory / "report.html"),
        "experiment_dir": str(record.directory),
        "experiments_root": str(experiments_root),
        "plugin": plugin_name,
    }


def run_data_update_job(payload: dict[str, Any], ctx: JobContext | None = None) -> dict[str, Any]:
    """Fetch a provider into the Parquet warehouse (quality-gated)."""
    _check(ctx)
    _progress(0.05, ctx)
    data_root = Path(payload.get("data_root") or "data")
    state = SQLiteState(Path(payload.get("state_path") or data_root / "state.sqlite"))
    store = ParquetStore(data_root / "warehouse", state=state)
    if bool(payload.get("reset")):
        store.reset()
    name = str(payload.get("provider") or "synthetic")
    kwargs: dict[str, Any] = {}
    if name == "synthetic":
        kwargs["config"] = _panel_spec(payload)
    elif name == "local":
        if not payload.get("local_dir"):
            raise ValueError("local provider requires local_dir")
        kwargs["data_dir"] = payload["local_dir"]
        if payload.get("column_mapping"):
            kwargs["column_mapping"] = payload["column_mapping"]
    elif name == "tushare" and payload.get("fixture_dir"):
        kwargs["fixture_dir"] = payload["fixture_dir"]
    _progress(0.2, ctx)
    _check(ctx)
    provider = create_provider(name, **kwargs)
    ingestor = ProviderIngestor(provider, store)
    start = str(payload.get("start") or "2020-01-02")
    end = str(payload.get("end") or "2024-12-31")
    result = ingestor.update(start, end, incremental=bool(payload.get("incremental", True)))
    _progress(0.8, ctx)
    _check(ctx)
    payload_out = {"kind": "data_update", **result.to_dict()}
    _progress(1.0, ctx)
    return payload_out


def run_snapshot_job(payload: dict[str, Any], ctx: JobContext | None = None) -> dict[str, Any]:
    """Freeze the warehouse into an immutable content-addressed snapshot."""
    _check(ctx)
    _progress(0.05, ctx)
    data_root = Path(payload.get("data_root") or "data")
    snapshots_root = Path(payload.get("snapshots_root") or data_root / "snapshots")
    state = SQLiteState(Path(payload.get("state_path") or data_root / "state.sqlite"))
    store = ParquetStore(data_root / "warehouse", state=state)
    _progress(0.2, ctx)
    _check(ctx)
    manifest = build_snapshot_from_store(
        store,
        snapshots_root,
        state=state,
        require_qpanel=bool(payload.get("require_qpanel", True)),
    )
    _progress(0.8, ctx)
    _check(ctx)
    _progress(1.0, ctx)
    return {
        "kind": "snapshot_build",
        "snapshot_id": manifest.snapshot_id,
        "content_hash": manifest.content_hash,
        "path": str(snapshots_root / manifest.snapshot_id),
        "n_sec": manifest.metadata.get("n_sec"),
        "n_time": manifest.metadata.get("n_time"),
        "synthetic": manifest.synthetic,
        "panel_available": bool(manifest.panel.get("available", False)),
    }


def run_job(payload: dict[str, Any], ctx: JobContext | None = None) -> dict[str, Any]:
    """Dispatch one job payload; unknown kinds fail loudly."""
    kind = str(payload.get("kind") or "backtest")
    if kind == "backtest":
        return run_backtest_job(payload, ctx)
    if kind == "data_update":
        return run_data_update_job(payload, ctx)
    if kind == "snapshot_build":
        return run_snapshot_job(payload, ctx)
    raise ValueError(f"unknown job kind: {kind}")


__all__ = ["run_backtest_job", "run_data_update_job", "run_job", "run_snapshot_job"]
