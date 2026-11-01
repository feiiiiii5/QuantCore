"""Experiment runner and replay: strategy + snapshot + config -> reproducible artefacts."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import quantcore

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..backtest.result import BacktestResult
from ..data.panel import PanelData
from ..errors import ExperimentError, SnapshotError
from ..snapshot.reader import Snapshot, find_snapshot, load_snapshot
from ..strategy.spec import StrategySpec
from .store import ExperimentRecord, ExperimentStore


def capture_environment() -> dict[str, Any]:
    """Environment fingerprint recorded with every experiment."""
    environment: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "quantcore_version": quantcore.__version__,
        "engine_backend": quantcore.engine_backend(),
        "cpp_version": quantcore.cpp_version(),
        "numpy": np.__version__,
    }
    try:
        import pandas

        environment["pandas"] = pandas.__version__
    except Exception:  # pragma: no cover - pandas is a required dependency
        pass
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parents[3],
            check=False,
        )
        if commit.returncode == 0:
            environment["git_commit"] = commit.stdout.strip()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git may be absent
        pass
    return environment


def _snapshot_reference(snapshot: Snapshot | None, panel: PanelData | None) -> dict[str, Any]:
    if snapshot is not None:
        return {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_root": str(snapshot.root.parent),
            "content_hash": snapshot.manifest.content_hash,
            "synthetic": snapshot.manifest.synthetic,
            "source": snapshot.manifest.source,
            "n_sec": snapshot.manifest.metadata.get("n_sec"),
            "n_time": snapshot.manifest.metadata.get("n_time"),
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


_PANEL_FILES = ("bars", "securities", "calendar", "financials", "corporate_actions")


def _save_panel_data(panel: PanelData, directory: Path) -> None:
    """Persist an in-memory panel so the experiment can be replayed without a snapshot."""
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


def _load_panel_data(directory: Path) -> PanelData:
    from ..calendar import TradingCalendar

    if not (directory / "bars.parquet").exists():
        raise ExperimentError(f"experiment panel data is missing: {directory}")
    bars = pd.read_parquet(directory / "bars.parquet")
    securities = pd.read_parquet(directory / "securities.parquet")
    calendar = TradingCalendar.from_dates(
        pd.read_parquet(directory / "calendar.parquet")["date"].tolist()
    )
    financials = (
        pd.read_parquet(directory / "financials.parquet")
        if (directory / "financials.parquet").exists()
        else pd.DataFrame()
    )
    actions = (
        pd.read_parquet(directory / "corporate_actions.parquet")
        if (directory / "corporate_actions.parquet").exists()
        else pd.DataFrame()
    )
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return PanelData(
        calendar=calendar,
        securities=securities,
        bars=bars,
        financials=financials,
        corporate_actions=actions,
        meta=meta,
    )


def run_experiment(
    store: ExperimentStore,
    spec: StrategySpec,
    *,
    snapshot: Snapshot | None = None,
    panel: PanelData | None = None,
    config: BacktestConfig | None = None,
    base_dir: str | Path | None = None,
    report: bool = False,
) -> ExperimentRecord:
    """Run a backtest, persist metadata/result/strategy.yaml and return the record."""
    if snapshot is None and panel is None:
        raise ExperimentError("run_experiment needs a snapshot or a PanelData")
    cfg = config or BacktestConfig()
    strategy = spec.load(base_dir)
    panel_data = snapshot.to_panel_data() if snapshot is not None else panel
    assert panel_data is not None
    weights = strategy.generate_targets(panel_data)
    result = run_backtest(
        snapshot if snapshot is not None else panel_data,
        weights,
        cfg,
        strategy_metadata={
            **strategy.metadata(),
            "spec": spec.to_dict(),
            "spec_hash": spec.content_hash(base_dir),
        },
        snapshot_metadata=_snapshot_reference(snapshot, panel_data),
    )
    metadata: dict[str, Any] = {
        "strategy": spec.to_dict(),
        "strategy_name": spec.name,
        "strategy_hash": spec.content_hash(base_dir),
        "params": spec.params,
        "snapshot": _snapshot_reference(snapshot, panel_data),
        "config": cfg.to_dict(),
        "seed": cfg.seed,
        "engine_backend": result.engine_backend,
        "engine_version": result.engine_version,
        "environment": capture_environment(),
        "metrics": result.metrics,
        "synthetic": bool((snapshot.manifest.synthetic if snapshot else panel_data.meta.get("synthetic", False))),
        "status": "completed",
    }
    run_id = store.create("backtest", metadata, content_hash=spec.content_hash(base_dir))
    store.save_text(run_id, "strategy.yaml", spec.to_yaml())
    if snapshot is None and panel_data is not None:
        _save_panel_data(panel_data, store.path(run_id) / "panel")
    store.save_result(run_id, result)
    store.save_json(run_id, "summary.json", result.summary())
    if report:
        from ..report import render_html_report

        render_html_report(
            result,
            output_path=store.path(run_id) / "report.html",
            strategy_metadata=dict(metadata.get("strategy") or {}),
            snapshot_metadata=dict(metadata.get("snapshot") or {}),
        )
    return store.get(run_id)


@dataclass
class ReplayResult:
    run_id: str
    matched: bool
    equity_match: bool
    trades_match: bool
    metrics_match: bool
    differences: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "matched": self.matched,
            "equity_match": self.equity_match,
            "trades_match": self.trades_match,
            "metrics_match": self.metrics_match,
            "differences": self.differences,
            "metadata": self.metadata,
        }


def replay_experiment(store: ExperimentStore, run_id: str) -> ReplayResult:
    """Re-run a stored experiment and compare equity/trades/metrics bit-for-bit."""
    record = store.get(run_id)
    metadata = record.metadata
    stored = store.load_result(run_id)
    strategy_payload = metadata.get("strategy")
    if not strategy_payload:
        raise ExperimentError(f"experiment {run_id} has no strategy metadata")
    spec = StrategySpec.model_validate(strategy_payload)
    snapshot_info = metadata.get("snapshot", {})
    differences: list[str] = []
    if snapshot_info.get("snapshot_id"):
        root = snapshot_info.get("snapshot_root")
        if root is None:
            raise ExperimentError("experiment does not record its snapshot root")
        try:
            snapshot = load_snapshot(root, str(snapshot_info["snapshot_id"]))
        except SnapshotError as exc:
            raise ExperimentError(f"cannot replay: {exc}") from exc
        panel_data = snapshot.to_panel_data()
    else:
        snapshot = None
        panel_dir = snapshot_info.get("panel_dir", "panel")
        panel_data = _load_panel_data(record.directory / str(panel_dir))
    config = BacktestConfig.from_dict(metadata.get("config", {}))
    strategy = spec.load()
    weights = strategy.generate_targets(panel_data)
    fresh = run_backtest(
        snapshot if snapshot is not None else panel_data,
        weights,
        config,
        strategy_metadata=strategy.metadata(),
        snapshot_metadata=snapshot_info,
    )
    equity_match = stored.equity.shape == fresh.equity.shape and bool(
        np.array_equal(stored.equity, fresh.equity)
    )
    trades_match = stored.trades.shape == fresh.trades.shape and bool(
        np.array_equal(
            stored.trades.fillna("").astype(str).to_numpy(),
            fresh.trades.fillna("").astype(str).to_numpy(),
        )
    )
    metrics_match = json.dumps(stored.metrics, sort_keys=True) == json.dumps(
        fresh.metrics, sort_keys=True
    )
    if not equity_match:
        differences.append("equity curve differs")
    if not trades_match:
        differences.append("trade list differs")
    if not metrics_match:
        differences.append("metrics differ")
    return ReplayResult(
        run_id=run_id,
        matched=equity_match and trades_match and metrics_match,
        equity_match=equity_match,
        trades_match=trades_match,
        metrics_match=metrics_match,
        differences=differences,
        metadata={"engine_backend": fresh.engine_backend, "engine_version": fresh.engine_version},
    )

