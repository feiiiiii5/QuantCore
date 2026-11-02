"""One-command SYNTHETIC demo pipeline for 'qc demo'.

Provider -> Parquet warehouse -> immutable snapshot -> C++ backtest -> HTML report.
Everything runs offline under a dedicated demo root (default 'data/demo'), so the
existing data/warehouse and experiments are never overwritten.  All data is SYNTHETIC.
"""

# ruff: noqa: B008 -- typer's documented API uses function calls in argument defaults

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer

import quantcore

from .errors import DemoError, QuantCoreError

DEFAULT_DATA_ROOT = Path("data/demo")
DEFAULT_EXPERIMENTS_ROOT = Path("experiments")
DEFAULT_TEMPLATE = "dual_ma"
SERVE_HINT = "uv run qc serve --port 8000 --open"
SYNTHETIC_NOTICE = (
    "SYNTHETIC data: every price and result is fabricated; not a real market result "
    "and not investment advice"
)

__all__ = [
    "DEFAULT_DATA_ROOT",
    "DEFAULT_EXPERIMENTS_ROOT",
    "DemoResult",
    "demo_command",
    "run_demo",
]


@dataclass
class DemoResult:
    """Summary of one demo run (paths are strings for JSON friendliness)."""

    snapshot_id: str
    run_id: str
    engine_backend: str
    metrics: dict[str, Any]
    report: str | None
    data_root: str
    snapshots_root: str
    experiments_root: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "run_id": self.run_id,
            "engine_backend": self.engine_backend,
            "metrics": self.metrics,
            "report": self.report,
            "data_root": self.data_root,
            "snapshots_root": self.snapshots_root,
            "experiments_root": self.experiments_root,
            "steps": self.steps,
            "warnings": self.warnings,
        }


def _step(name: str, status: str, started: float, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "seconds": round(time.perf_counter() - started, 3),
        "detail": detail,
    }


def run_demo(
    *,
    data_root: str | Path = "data/demo",
    snapshots_root: str | Path | None = None,
    experiments_root: str | Path = "experiments",
    n_sec: int = 120,
    start: str = "2020-01-02",
    end: str = "2024-12-31",
    seed: int = 42,
    template: str = "dual_ma",
    params: dict[str, Any] | None = None,
    report: bool = True,
) -> DemoResult:
    """Run the full offline demo and return its summary.

    Raises :class:'DemoError' when the C++ engine is unavailable (hint: make build).
    """
    data_path = Path(data_root)
    snapshots_path = Path(snapshots_root) if snapshots_root is not None else data_path / "snapshots"
    experiments_path = Path(experiments_root)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = [SYNTHETIC_NOTICE]

    started = time.perf_counter()
    backend = quantcore.engine_backend()
    if backend != "cpp" or not quantcore.engine_available():
        raise DemoError(
            f"C++ backtest engine unavailable (engine_backend={backend}); run 'make build' first"
        )
    panel_ready = quantcore.panel_available()
    steps.append(
        _step(
            "preflight",
            "pass",
            started,
            f"engine_backend={backend} panel_available={panel_ready}",
        )
    )
    if not panel_ready:
        warnings.append(
            "C++ .qpanel writer unavailable: the demo snapshot has no .qpanel file; "
            "run 'make build' for the fast path"
        )

    started = time.perf_counter()
    from quantcore.data.store import ParquetStore
    from quantcore.data.synthetic import SyntheticConfig
    from quantcore.ingest import ProviderIngestor
    from quantcore.providers import create_provider

    config = SyntheticConfig(n_sec=n_sec, start=start, end=end, seed=seed)
    store = ParquetStore(data_path / "warehouse")
    ingestor = ProviderIngestor(create_provider("synthetic", config=config), store)
    ingest = ingestor.update(start, end, incremental=False)
    for issue in (ingest.quality or {}).get("issues", []):
        if issue.get("severity") == "warning":
            warnings.append(f"quality warning: {issue.get('message')} (count={issue.get('count')})")
    total_rows = sum(int(rows) for rows in ingest.datasets.values())
    steps.append(
        _step(
            "ingest",
            "pass",
            started,
            f"synthetic n_sec={n_sec} datasets={len(ingest.datasets)} rows={total_rows} "
            f"quality_passed={ingest.quality_passed}",
        )
    )

    started = time.perf_counter()
    from quantcore.snapshot import build_snapshot_from_store, load_snapshot

    manifest = build_snapshot_from_store(store, snapshots_path)
    snapshot = load_snapshot(snapshots_path, manifest.snapshot_id)
    qpanel = bool((manifest.panel or {}).get("available", False))
    steps.append(
        _step(
            "snapshot",
            "pass",
            started,
            f"{manifest.snapshot_id} synthetic={manifest.synthetic} qpanel={qpanel}",
        )
    )

    started = time.perf_counter()
    from quantcore.backtest.config import BacktestConfig
    from quantcore.experiments import ExperimentStore, run_experiment
    from quantcore.strategy.spec import StrategySpec

    spec = StrategySpec(name=f"demo_{template}", template=template, params=dict(params or {}))
    experiment_store = ExperimentStore(experiments_path)
    backtest_config = BacktestConfig(start=start, end=end, seed=seed)
    if panel_ready:
        record = run_experiment(
            experiment_store,
            spec,
            snapshot=snapshot,
            config=backtest_config,
            report=report,
        )
    else:
        record = run_experiment(
            experiment_store,
            spec,
            panel=snapshot.to_panel_data(),
            config=backtest_config,
            report=report,
        )
    result = experiment_store.load_result(record.run_id)
    summary = result.summary()
    metrics: dict[str, Any] = dict(summary.get("metrics") or {})
    steps.append(
        _step(
            "experiment",
            "pass",
            started,
            f"run_id={record.run_id} trades={summary.get('trade_count')} "
            f"final_equity={summary.get('final_equity')}",
        )
    )

    started = time.perf_counter()
    report_path = record.directory / "report.html"
    report_text: str | None = None
    if not report:
        steps.append(_step("report", "skip", started, "HTML report disabled (report=False)"))
    elif report_path.is_file():
        report_text = str(report_path)
        steps.append(_step("report", "pass", started, report_text))
    else:  # pragma: no cover - rendering failures raise inside run_experiment
        steps.append(_step("report", "warn", started, f"report not found: {report_path}"))

    return DemoResult(
        snapshot_id=manifest.snapshot_id,
        run_id=record.run_id,
        engine_backend=result.engine_backend,
        metrics=metrics,
        report=report_text,
        data_root=str(data_path),
        snapshots_root=str(snapshots_path),
        experiments_root=str(experiments_path),
        steps=steps,
        warnings=warnings,
    )


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _render_text(result: DemoResult) -> str:
    lines = ["QuantCore demo (SYNTHETIC data; not investment advice)", ""]
    for step in result.steps:
        lines.append(
            f"  [{str(step['status']).upper()}] {step['name']:<11} "
            f"{float(step['seconds']):>7.3f}s  {step['detail']}"
        )
    lines.append("")
    lines.append(f"snapshot: {result.snapshot_id}")
    lines.append(f"run_id:   {result.run_id}")
    metrics = ", ".join(f"{key}={_format_value(value)}" for key, value in result.metrics.items())
    lines.append(f"metrics:  {metrics}")
    lines.append(f"report:   {result.report or '(disabled)'}")
    for warning in result.warnings:
        lines.append(f"warning:  {warning}")
    return "\n".join(lines)


def demo_command(
    data_root: Path = typer.Option(
        DEFAULT_DATA_ROOT, help="demo data directory (warehouse + snapshots)"
    ),
    experiments_root: Path = typer.Option(DEFAULT_EXPERIMENTS_ROOT, help="experiment store root"),
    n_sec: int = typer.Option(120, min=1, help="synthetic universe size"),
    start: str = typer.Option("2020-01-02", help="first trading day (YYYY-MM-DD)"),
    end: str = typer.Option("2024-12-31", help="last trading day (YYYY-MM-DD)"),
    seed: int = typer.Option(42, help="synthetic generator seed"),
    template: str = typer.Option(DEFAULT_TEMPLATE, help="built-in strategy template"),
    json_output: bool = typer.Option(True, help="emit the JSON summary"),
) -> None:
    """One-command SYNTHETIC demo: warehouse -> snapshot -> backtest -> HTML report."""
    try:
        result = run_demo(
            data_root=data_root,
            experiments_root=experiments_root,
            n_sec=n_sec,
            start=start,
            end=end,
            seed=seed,
            template=template,
        )
    except QuantCoreError as exc:
        typer.echo(f"qc demo: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
        typer.echo(f"next: {SERVE_HINT}", err=True)
    else:
        typer.echo(_render_text(result))
        typer.echo(f"next: {SERVE_HINT}")
