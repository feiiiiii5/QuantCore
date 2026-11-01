"""Read-only experiment artefact loading for M7 robustness analytics.

All helpers are pure local file reads: no network, no writes to the experiment store and no
change to the original run.  Invalid/missing artefacts raise :class:`ResearchDataError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..backtest.config import BacktestConfig
from ..backtest.result import BacktestResult
from ..data.panel import PanelData
from ..errors import ExperimentError
from ..experiments.store import ExperimentRecord, ExperimentStore
from ..snapshot.reader import Snapshot, find_snapshot
from ..strategy.spec import StrategySpec


class ResearchDataError(ValueError):
    """The experiment cannot support the requested research analysis (HTTP 400)."""


@dataclass(frozen=True)
class ExperimentBundle:
    """One persisted experiment plus its parsed config/strategy spec."""

    record: ExperimentRecord
    result: BacktestResult
    config: BacktestConfig
    spec: StrategySpec | None


def load_bundle(store: ExperimentStore, run_id: str) -> ExperimentBundle:
    """Load an experiment's metadata/result/config without mutating it."""
    try:
        record = store.get(run_id)
        result = store.load_result(run_id)
    except ExperimentError as exc:
        raise ResearchDataError(f"experiment not found or has no result: {run_id}") from exc
    try:
        config = BacktestConfig.model_validate(dict(record.metadata.get("config") or {}))
    except Exception as exc:  # pydantic ValidationError → actionable 400
        raise ResearchDataError(f"experiment {run_id} has an invalid config: {exc}") from exc
    spec_payload = record.metadata.get("strategy")
    spec: StrategySpec | None = None
    if isinstance(spec_payload, dict):
        try:
            spec = StrategySpec.model_validate(spec_payload)
        except Exception as exc:
            raise ResearchDataError(f"experiment {run_id} has an invalid strategy: {exc}") from exc
    return ExperimentBundle(record=record, result=result, config=config, spec=spec)


def daily_returns(result: BacktestResult) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(dates, returns)`` aligned to the equity curve (no leading zero row)."""
    equity = np.asarray(result.equity_yuan, dtype=np.float64)
    dates = np.asarray(result.dates, dtype=np.int64)
    if equity.size < 2:
        return dates[0:0], np.asarray([], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = equity[1:] / equity[:-1] - 1.0
    return dates[1:], returns


def clean_returns(result: BacktestResult, *, minimum: int = 30) -> np.ndarray:
    """Finite daily returns, or raise when the experiment is too short to analyse."""
    _, returns = daily_returns(result)
    finite = returns[np.isfinite(returns)]
    if finite.size < minimum:
        raise ResearchDataError(
            f"experiment has only {int(finite.size)} usable daily returns; "
            f"at least {minimum} are required"
        )
    return finite


def load_panel(
    record: ExperimentRecord, snapshots_root: str | Path
) -> tuple[PanelData, Snapshot | None]:
    """Materialise the experiment's snapshot/panel (read-only)."""
    snapshot_info: dict[str, Any] = dict(record.metadata.get("snapshot") or {})
    snapshot_id = snapshot_info.get("snapshot_id")
    if snapshot_id:
        root = Path(str(snapshot_info.get("snapshot_root") or snapshots_root))
        try:
            snapshot = find_snapshot(root, str(snapshot_id))
        except Exception as exc:
            raise ResearchDataError(
                f"snapshot {snapshot_id} is unavailable for {record.run_id}: {exc}"
            ) from exc
        return snapshot.to_panel_data(), snapshot
    panel_dir = record.directory / str(snapshot_info.get("panel_dir", "panel"))
    if not (panel_dir / "bars.parquet").exists():
        raise ResearchDataError(
            f"experiment {record.run_id} has no snapshot and no persisted panel"
        )
    from ..experiments.runner import _load_panel_data

    return _load_panel_data(panel_dir), None


__all__ = [
    "ExperimentBundle",
    "ResearchDataError",
    "clean_returns",
    "daily_returns",
    "load_bundle",
    "load_panel",
]
