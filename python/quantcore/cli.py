"""``qc`` command line interface: data, snapshots, backtests, sweeps, checks, replay, serve.

Research and simulation only: there is no real trading endpoint anywhere in this CLI.
"""

# ruff: noqa: B008 -- typer's documented API uses function calls in argument defaults

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import click
import typer

import quantcore

_TyperClickException: type[Exception]
try:  # typer vendors its own click; catch both exception hierarchies
    from typer._click import exceptions as _typer_click_exceptions

    _TyperClickException = _typer_click_exceptions.ClickException
except Exception:  # pragma: no cover - fallback for non-vendored typer builds
    _TyperClickException = click.ClickException

DATA_ROOT = Path("data")
SNAPSHOTS_ROOT = DATA_ROOT / "snapshots"
EXPERIMENTS_ROOT = Path("experiments")

app = typer.Typer(
    help="QuantCore research workbench (SYNTHETIC demo data; not investment advice).",
    no_args_is_help=True,
    add_completion=False,
)
data_app = typer.Typer(help="Data update: provider -> quality gate -> Parquet warehouse")
snapshot_app = typer.Typer(help="Snapshots: content-addressed, immutable, with .qpanel")
backtest_app = typer.Typer(help="Backtest runs and queries (C++ engine)")
sweep_app = typer.Typer(help="Deterministic parameter sweeps")
check_app = typer.Typer(help="Data and strategy checks")
app.add_typer(data_app, name="data")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(backtest_app, name="backtest")
app.add_typer(sweep_app, name="sweep")
app.add_typer(check_app, name="check")


from .cli_serve import serve_command  # noqa: E402


def _emit(payload: dict[str, Any], json_output: bool = True) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("expected a JSON object")
    return payload


def _cli_panel(
    snapshot: str | None,
    snapshots_root: Path,
    seed: int,
    n_sec: int,
) -> tuple[Any, Any, dict[str, Any]]:
    """Return ``(panel_data, engine_target, snapshot_metadata)`` for CLI runs."""
    if snapshot:
        from quantcore.snapshot.reader import find_snapshot

        snap = find_snapshot(snapshots_root, snapshot)
        return snap.to_panel_data(), snap, snap.describe()
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel

    panel = generate_synthetic_panel(
        SyntheticConfig(n_sec=n_sec, start="2022-01-04", end="2024-12-31", seed=seed)
    )
    return (
        panel,
        panel,
        {
            "synthetic": True,
            "source": "SYNTHETIC",
            "n_sec": panel.n_sec,
            "n_time": panel.n_time,
            "seed": seed,
        },
    )


def _load_spec(
    spec_path: Path | None,
    template: str | None,
    params: str,
    name: str | None = None,
) -> Any:
    from quantcore.strategy.spec import StrategySpec

    if spec_path is not None:
        return StrategySpec.from_yaml(spec_path)
    if template is None:
        raise typer.BadParameter("provide --spec strategy.yaml or --template <name>")
    return StrategySpec(name=name or template, template=template, params=_parse_json_object(params))


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
@data_app.command("update")
def data_update(
    provider: str = typer.Option("synthetic", help="synthetic | local | tushare | ..."),
    data_root: Path = typer.Option(DATA_ROOT, help="data directory"),
    start: str = typer.Option("2020-01-02"),
    end: str = typer.Option("2024-12-31"),
    n_sec: int = typer.Option(200, min=1),
    seed: int = typer.Option(42),
    local_dir: Path | None = typer.Option(None, help="local provider data directory"),
    fixture_dir: Path | None = typer.Option(None, help="tushare fixture directory"),
    incremental: bool = typer.Option(True),
    reset: bool = typer.Option(False),
    json_output: bool = typer.Option(True),
) -> None:
    """Fetch/normalise data into the Parquet warehouse (quality-gated)."""
    from quantcore.data.store import ParquetStore
    from quantcore.ingest import ProviderIngestor
    from quantcore.providers import create_provider

    store = ParquetStore(data_root / "warehouse")
    if reset:
        store.reset()
    kwargs: dict[str, Any] = {}
    if provider == "synthetic":
        from quantcore.data.synthetic import SyntheticConfig

        kwargs["config"] = SyntheticConfig(n_sec=n_sec, start=start, end=end, seed=seed)
    elif provider == "local":
        if local_dir is None:
            raise typer.BadParameter("--local-dir is required for the local provider")
        kwargs["data_dir"] = local_dir
    elif provider == "tushare" and fixture_dir is not None:
        kwargs["fixture_dir"] = fixture_dir
    prov = create_provider(provider, **kwargs)
    ingestor = ProviderIngestor(prov, store)
    result = ingestor.update(start, end, incremental=incremental)
    payload = result.to_dict()
    payload["manifest_hash"] = store.manifest_hash()
    _emit(payload, json_output)


@data_app.command("status")
def data_status(
    data_root: Path = typer.Option(DATA_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """Show warehouse datasets, manifest hash and ingest metadata."""
    from quantcore.data.store import ParquetStore

    store = ParquetStore(data_root / "warehouse")
    payload = store.describe()
    payload["last_ingest"] = store.state.get_meta("last_ingest")
    _emit(payload, json_output)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------
@snapshot_app.command("build")
def snapshot_build(
    data_root: Path = typer.Option(DATA_ROOT),
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    require_qpanel: bool = typer.Option(True, help="fail if the C++ PanelWriter is unavailable"),
    json_output: bool = typer.Option(True),
) -> None:
    """Freeze the warehouse into a content-addressed immutable snapshot."""
    from quantcore.data.store import ParquetStore
    from quantcore.snapshot import build_snapshot

    store = ParquetStore(data_root / "warehouse")
    panel = store.load_panel()
    manifest = build_snapshot(
        panel, snapshots_root, state=store.state, require_qpanel=require_qpanel
    )
    payload = {
        "snapshot_id": manifest.snapshot_id,
        "content_hash": manifest.content_hash,
        "synthetic": manifest.synthetic,
        "source": manifest.source,
        "qpanel": manifest.panel,
        "datasets": {name: item.rows for name, item in manifest.datasets.items()},
        "quality": manifest.quality,
        "path": str(snapshots_root / manifest.snapshot_id),
    }
    _emit(payload, json_output)


@snapshot_app.command("list")
def snapshot_list(
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """List available snapshots."""
    from quantcore.snapshot import list_snapshots

    manifests = list_snapshots(snapshots_root)
    payload = {
        "snapshots": [
            {
                "snapshot_id": item.snapshot_id,
                "synthetic": item.synthetic,
                "source": item.source,
                "created_at": item.created_at,
                "qpanel": bool((item.panel or {}).get("available", False)),
            }
            for item in manifests
        ],
        "count": len(manifests),
    }
    _emit(payload, json_output)


@snapshot_app.command("verify")
def snapshot_verify(
    snapshot_id: str = typer.Argument(...),
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """Verify a snapshot's file hashes and manifest consistency."""
    from quantcore.snapshot import find_snapshot

    snap = find_snapshot(snapshots_root, snapshot_id)
    payload = {
        "snapshot_id": snap.snapshot_id,
        "problems": snap.verify(),
        "describe": snap.describe(),
    }
    _emit(payload, json_output)


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------
@backtest_app.command("run")
def backtest_run(
    spec: Path | None = typer.Option(None, help="strategy.yaml path"),
    template: str | None = typer.Option(None, help="built-in template id"),
    params: str = typer.Option("{}", help="JSON params for the template"),
    snapshot: str | None = typer.Option(None, help="snapshot id/prefix"),
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    experiments_root: Path = typer.Option(EXPERIMENTS_ROOT),
    start: str | None = typer.Option(None),
    end: str | None = typer.Option(None),
    initial_cash: float = typer.Option(1_000_000.0),
    seed: int = typer.Option(42),
    n_sec: int = typer.Option(60, help="synthetic universe size when no snapshot is given"),
    report: bool = typer.Option(True, help="write an HTML report"),
    json_output: bool = typer.Option(True),
) -> None:
    """Run one backtest through the C++ engine and persist an experiment."""
    from quantcore.backtest.config import BacktestConfig
    from quantcore.experiments import ExperimentStore, run_experiment

    strategy_spec = _load_spec(spec, template, params)
    panel, target, _snapshot_meta = _cli_panel(snapshot, snapshots_root, seed, n_sec)
    config = BacktestConfig(start=start, end=end, initial_cash=initial_cash, seed=seed)
    store = ExperimentStore(experiments_root)
    record = run_experiment(
        store,
        strategy_spec,
        snapshot=target if snapshot else None,
        panel=None if snapshot else panel,
        config=config,
        report=report,
    )
    result = store.load_result(record.run_id)
    summary = result.summary()
    summary["run_id"] = record.run_id
    summary["experiment_dir"] = str(record.directory)
    summary["report"] = str(record.directory / "report.html") if report else None
    _emit(summary, json_output)


@backtest_app.command("list")
def backtest_list(
    experiments_root: Path = typer.Option(EXPERIMENTS_ROOT),
    limit: int = typer.Option(20, min=1),
    json_output: bool = typer.Option(True),
) -> None:
    """List stored backtest experiments."""
    from quantcore.experiments import ExperimentStore

    records = ExperimentStore(experiments_root).list(kind="backtest", limit=limit)
    payload = {
        "experiments": [
            {
                "run_id": record.run_id,
                "strategy": record.metadata.get("strategy_name"),
                "snapshot": (record.metadata.get("snapshot") or {}).get("snapshot_id"),
                "created_at": record.created_at,
                "metrics": record.metadata.get("metrics"),
            }
            for record in records
        ]
    }
    _emit(payload, json_output)


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------
@sweep_app.command("run")
def sweep_run(
    spec: Path | None = typer.Option(None),
    template: str | None = typer.Option(None),
    params: str = typer.Option("{}"),
    grid: str = typer.Option(..., help='JSON grid, e.g. {"top_n":[10,20,30]}'),
    snapshot: str | None = typer.Option(None),
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    experiments_root: Path = typer.Option(EXPERIMENTS_ROOT),
    workers: int = typer.Option(1, min=1),
    seed: int = typer.Option(42),
    n_sec: int = typer.Option(60),
    json_output: bool = typer.Option(True),
) -> None:
    """Run a deterministic parameter sweep through the C++ engine."""
    from quantcore.backtest.sweep import run_sweep
    from quantcore.experiments import ExperimentStore

    strategy_spec = _load_spec(spec, template, params)
    panel, _target, _meta = _cli_panel(snapshot, snapshots_root, seed, n_sec)
    result = run_sweep(
        panel,
        strategy_spec,
        _parse_json_object(grid),
        max_workers=workers,
        progress=lambda done, total: typer.echo(f"sweep {done}/{total}", err=True),
    )
    store = ExperimentStore(experiments_root)
    run_id = store.create("sweep", {"table_rows": len(result.table), "grid": grid})
    table_path = result.to_parquet(store.path(run_id) / "sweep.parquet")
    store.save_json(
        run_id,
        "sweep.json",
        {"table": result.table.to_dict(orient="records")},
    )
    best = result.best("sharpe")
    payload = {
        "run_id": run_id,
        "engine_backend": result.engine_backend,
        "points": len(result.points),
        "failures": len(result.failures),
        "best_sharpe": None if best is None else best.metrics.get("sharpe"),
        "best_params": None if best is None else best.params,
        "table": str(table_path),
    }
    _emit(payload, json_output)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
@check_app.command("lookahead")
def check_lookahead_command(
    spec: Path | None = typer.Option(None),
    template: str | None = typer.Option(None),
    params: str = typer.Option("{}"),
    snapshot: str | None = typer.Option(None),
    snapshots_root: Path = typer.Option(SNAPSHOTS_ROOT),
    seed: int = typer.Option(42),
    cuts: int = typer.Option(5, min=1, max=20),
    n_sec: int = typer.Option(60),
    json_output: bool = typer.Option(True),
) -> None:
    """Detect future-function bugs by truncating data and re-running signals."""
    from quantcore.strategy.lookahead import check_lookahead

    strategy_spec = _load_spec(spec, template, params)
    panel, _target, _meta = _cli_panel(snapshot, snapshots_root, seed, n_sec)
    strategy = strategy_spec.load()
    report = check_lookahead(strategy, panel, n_cuts=cuts)
    payload = report.to_dict()
    payload["engine_backend"] = quantcore.engine_backend()
    _emit(payload, json_output)
    if not report.passed:
        raise typer.Exit(code=1)


@check_app.command("data")
def check_data_command(
    data_root: Path = typer.Option(DATA_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """Run canonical data-quality checks over the warehouse."""
    from quantcore.data.store import ParquetStore
    from quantcore.quality import run_quality_checks

    panel = ParquetStore(data_root / "warehouse").load_panel()
    report = run_quality_checks(panel)
    _emit(report.to_dict(), json_output)
    if not report.passed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# replay / serve / bench / version
# ---------------------------------------------------------------------------
@app.command("replay")
def replay_command(
    run_id: str = typer.Argument(...),
    experiments_root: Path = typer.Option(EXPERIMENTS_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """Re-run a stored experiment and verify bit-for-bit reproducibility."""
    from quantcore.experiments import ExperimentStore, replay_experiment

    replay = replay_experiment(ExperimentStore(experiments_root), run_id)
    _emit(replay.to_dict(), json_output)
    if not replay.matched:
        raise typer.Exit(code=1)


app.command("serve")(serve_command)


@app.command("bench")
def bench_command(
    n_sec: int = typer.Option(200),
    json_output: bool = typer.Option(True),
) -> None:
    """Run Python-side benchmarks (panel ingest, .qpanel write/open, engine run)."""
    from quantcore.bench import run_benchmarks

    started = time.time()
    payload = run_benchmarks(n_sec=n_sec)
    payload["wall_seconds"] = round(time.time() - started, 3)
    _emit(payload, json_output)


@app.command("version")
def version_command() -> None:
    """Print version and backend readiness."""
    _emit(
        {
            "quantcore": quantcore.__version__,
            "engine_backend": quantcore.engine_backend(),
            "engine_available": quantcore.engine_available(),
            "panel_available": quantcore.panel_available(),
            "cpp_version": quantcore.cpp_version(),
        },
        True,
    )


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point (``qc``)."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        result = app(args=args, prog_name="qc", standalone_mode=False)
        return int(result) if isinstance(result, int) else 0
    except (typer.Exit, click.exceptions.Exit) as exc:  # programmatic Exit with a code
        return int(exc.exit_code or 0)
    except (_TyperClickException, click.ClickException) as exc:  # unknown command / bad params
        show = getattr(exc, "show", None)
        if callable(show):
            show()
        return int(getattr(exc, "exit_code", 2))
    except SystemExit as exc:  # --help and click parsing exits
        return int(exc.code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
