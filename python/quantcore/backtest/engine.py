"""Adapter between the Python control plane and the C++ backtest engine.

The engine contract is defined by ``cpp/include/qcore/engine.h`` and the pybind
bindings: ``_qcore.Engine(panel, config).run(weights)`` where ``weights`` is a
``(n_time, n_sec)`` float64 matrix (NaN row = no rebalance).  Production backtests
*always* go through this adapter; the pure-Python reference engine lives only under
``tests/reference`` and is never imported here.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from .. import engine_available, require_engine
from ..data.panel import PanelData
from ..errors import BacktestError, CppUnavailableError
from ..snapshot.reader import Snapshot
from .config import BacktestConfig
from .result import BacktestResult

_PANEL_CACHE: OrderedDict[str, Path] = OrderedDict()
_PANEL_CACHE_DIR: Path | None = None
_PANEL_CACHE_LIMIT = 8


def _cached_qpanel_path(panel_data: PanelData) -> Path:
    """Write a PanelData to a process-local cached .qpanel file.

    Repeated backtests/sweeps over the same panel reuse the file, so only the first run
    pays the .qpanel write cost.  The cache is keyed by the panel content hash and holds
    at most ``_PANEL_CACHE_LIMIT`` panels.
    """
    global _PANEL_CACHE_DIR
    key = panel_data.content_hash()
    cached = _PANEL_CACHE.get(key)
    if cached is not None and cached.exists():
        _PANEL_CACHE.move_to_end(key)
        return cached
    if _PANEL_CACHE_DIR is None:
        _PANEL_CACHE_DIR = Path(tempfile.mkdtemp(prefix="qc-panel-cache-"))
        atexit.register(shutil.rmtree, _PANEL_CACHE_DIR, True)
    from ..snapshot.qpanel import write_qpanel

    path = _PANEL_CACHE_DIR / f"{key[:16]}.qpanel"
    write_qpanel(panel_data, path)
    _PANEL_CACHE[key] = path
    while len(_PANEL_CACHE) > _PANEL_CACHE_LIMIT:
        _, stale = _PANEL_CACHE.popitem(last=False)
        stale.unlink(missing_ok=True)
    return path


def _cpp_config(module: Any, config: BacktestConfig, calendar: Any) -> Any:
    kwargs = config.cpp_kwargs(calendar)
    if not hasattr(module, "BacktestConfig"):
        raise CppUnavailableError("_qcore.BacktestConfig is not bound; rebuild the extension")
    try:
        return module.BacktestConfig(**kwargs)
    except TypeError as exc:
        raise BacktestError(
            f"could not construct _qcore.BacktestConfig from Python config: {exc}; "
            "the bindings and BacktestConfig.cpp_kwargs() are out of sync"
        ) from exc


class _PanelHandle:
    """Context manager that materialises a ``_qcore.Panel`` for the engine."""

    def __init__(
        self,
        source: PanelData | Snapshot | str | Path | None = None,
        *,
        panel: PanelData | None = None,
    ) -> None:
        self.source = source
        self.panel = panel
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.panel_object: Any = None

    def __enter__(self) -> Any:
        module = require_engine()
        if isinstance(self.source, Snapshot):
            self.panel_object = self.source.open_panel()
            return self.panel_object
        if isinstance(self.source, (str, Path)):
            self.panel_object = module.Panel.open(str(self.source))
            return self.panel_object
        panel_data = self.panel if self.panel is not None else self.source
        if not isinstance(panel_data, PanelData):  # pragma: no cover - defensive
            raise BacktestError("run_backtest needs a PanelData, a Snapshot or a .qpanel path")
        path = _cached_qpanel_path(panel_data)
        self.panel_object = module.Panel.open(str(path))
        return self.panel_object

    def __exit__(self, *exc_info: object) -> None:
        self.panel_object = None
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None


def run_backtest(
    panel: PanelData | Snapshot | str | Path,
    weights: np.ndarray,
    config: BacktestConfig | None = None,
    *,
    strategy_metadata: dict[str, Any] | None = None,
    snapshot_metadata: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run one backtest through the C++ engine and normalise the result."""
    if not engine_available():
        raise CppUnavailableError(
            "QuantCore C++ backtest engine is not available; build the extension first"
        )
    module = require_engine()
    cfg = config or BacktestConfig()
    matrix = np.ascontiguousarray(np.asarray(weights, dtype=np.float64))
    if matrix.ndim != 2:
        raise BacktestError(f"weights must be a 2-D matrix, got shape {matrix.shape}")
    if isinstance(panel, Snapshot):
        calendar = panel.calendar()
        manifest_meta = panel.manifest.metadata
        n_time = int(manifest_meta.get("n_time") or 0)
        n_sec = int(manifest_meta.get("n_sec") or 0)
        sec_ids = [str(value) for value in panel.securities()["sec_id"].tolist()]
        snapshot_info = snapshot_metadata or panel.describe()
    else:
        panel_data = panel if isinstance(panel, PanelData) else None
        if panel_data is None:
            raise BacktestError(
                "run_backtest with a .qpanel path needs an explicit sec_id oracle; "
                "pass a PanelData or Snapshot instead"
            )
        calendar = panel_data.calendar
        n_time, n_sec = panel_data.n_time, panel_data.n_sec
        sec_ids = panel_data.sec_id_list
        snapshot_info = snapshot_metadata or {}
    if matrix.shape != (n_time, n_sec):
        raise BacktestError(
            f"weights shape {matrix.shape} does not match the panel {(n_time, n_sec)}"
        )
    matrix = _apply_risk_limits(matrix, cfg)
    with _PanelHandle(panel) as panel_object:
        cpp_config = _cpp_config(module, cfg, calendar)
        engine = module.Engine(panel_object, cpp_config)
        try:
            raw_result = engine.run(matrix)
        except TypeError as exc:
            raise BacktestError(f"_qcore.Engine.run(weights) signature mismatch: {exc}") from exc
        result = BacktestResult.from_cpp(
            raw_result,
            cfg,
            sec_ids=sec_ids,
            strategy=strategy_metadata or {},
            snapshot=snapshot_info,
        )
        if cfg.benchmark_code:
            _attach_benchmark(result, panel, cfg)
    if result.engine_backend != "cpp":  # pragma: no cover - defensive
        raise BacktestError(f"engine_backend must be 'cpp', got {result.engine_backend!r}")
    return result


def _apply_risk_limits(matrix: np.ndarray, config: BacktestConfig) -> np.ndarray:
    """Apply long-only, max-weight and max-position limits to each rebalance row."""
    risk = config.risk
    output = matrix.copy()
    for row in range(output.shape[0]):
        values = output[row]
        finite = np.isfinite(values)
        if not finite.any():
            continue
        if risk.long_only:
            values[finite & (values < 0.0)] = 0.0
        if risk.max_weight is not None:
            values[finite] = np.minimum(values[finite], float(risk.max_weight))
        if risk.max_positions is not None and int(risk.max_positions) > 0:
            candidates = np.flatnonzero(np.isfinite(values) & (values > 0.0))
            keep = {
                int(index)
                for index in candidates[
                    np.argsort(-values[candidates], kind="stable")[: int(risk.max_positions)]
                ]
            }
            for index in candidates:
                if int(index) not in keep:
                    values[index] = 0.0
        output[row] = values
    return output


def run_backtest_batch(
    panel: PanelData | Snapshot,
    weights_list: list[np.ndarray],
    config: BacktestConfig | None = None,
    *,
    threads: int = 0,
    strategy_metadata: dict[str, Any] | None = None,
    snapshot_metadata: dict[str, Any] | None = None,
) -> list[BacktestResult]:
    """Run several target-weight matrices through the C++ engine's batch entry point.

    The C++ ``qc::parallel_sweep`` thread pool runs independent engines; this is the
    parameter-sweep path (M4-011). Callers should chunk very large grids to bound memory.
    """
    if not engine_available():
        raise CppUnavailableError(
            "QuantCore C++ backtest engine is not available; build the extension first"
        )
    if not weights_list:
        raise BacktestError("run_backtest_batch needs at least one weight matrix")
    module = require_engine()
    cfg = config or BacktestConfig()
    if isinstance(panel, Snapshot):
        calendar = panel.calendar()
        manifest_meta = panel.manifest.metadata
        n_time = int(manifest_meta.get("n_time") or 0)
        n_sec = int(manifest_meta.get("n_sec") or 0)
        sec_ids = [str(value) for value in panel.securities()["sec_id"].tolist()]
        snapshot_info = snapshot_metadata or panel.describe()
    elif isinstance(panel, PanelData):
        calendar = panel.calendar
        n_time, n_sec = panel.n_time, panel.n_sec
        sec_ids = panel.sec_id_list
        snapshot_info = snapshot_metadata or {}
    else:  # pragma: no cover - defensive
        raise BacktestError("run_backtest_batch needs a PanelData or Snapshot")
    matrices = []
    for weights in weights_list:
        matrix = np.ascontiguousarray(np.asarray(weights, dtype=np.float64))
        if matrix.shape != (n_time, n_sec):
            raise BacktestError(
                f"weights shape {matrix.shape} does not match the panel {(n_time, n_sec)}"
            )
        matrices.append(_apply_risk_limits(matrix, cfg))
    batch = np.stack(matrices, axis=0)
    with _PanelHandle(panel) as panel_object:
        cpp_config = _cpp_config(module, cfg, calendar)
        engine = module.Engine(panel_object, cpp_config)
        try:
            raw_results = engine.run_batch(batch, int(threads or 0))
        except TypeError as exc:  # pragma: no cover - old binding
            raise BacktestError(f"_qcore.Engine.run_batch signature mismatch: {exc}") from exc
        results = [
            BacktestResult.from_cpp(
                raw,
                cfg,
                sec_ids=sec_ids,
                strategy=strategy_metadata or {},
                snapshot=snapshot_info,
            )
            for raw in raw_results
        ]
    for result in results:
        if cfg.benchmark_code:
            _attach_benchmark(result, panel, cfg)
        if result.engine_backend != "cpp":  # pragma: no cover - defensive
            raise BacktestError(f"engine_backend must be 'cpp', got {result.engine_backend!r}")
    return results


def _attach_benchmark(
    result: BacktestResult, panel: PanelData | Snapshot | str | Path, config: BacktestConfig
) -> None:
    """Attach a buy-and-hold benchmark curve and comparison metrics to ``result``."""
    code = str(config.benchmark_code or "").strip()
    if not code:
        return
    if isinstance(panel, Snapshot):
        securities = panel.securities()
        bars = panel.bars()
    elif isinstance(panel, PanelData):
        securities = panel.securities
        bars = panel.bars
    else:
        raise BacktestError("benchmark comparison needs a PanelData or Snapshot")
    match = securities[
        (securities["code"].astype(str) == code) | (securities["sec_id"].astype(str) == code)
    ]
    if match.empty:
        raise BacktestError(f"benchmark security not found in panel: {code}")
    row = match.iloc[0]
    sec_id = str(row["sec_id"])
    series = bars[bars["sec_id"].astype(str) == sec_id].sort_values("date")
    if series.empty:
        raise BacktestError(f"benchmark security has no bars: {code}")
    close_by_date = {
        int(day): float(value)
        for day, value in zip(series["date"], series["close"], strict=False)
        if float(value) > 0
    }
    base = 0.0
    equity: list[float | None] = []
    for day in result.dates.tolist():
        close = close_by_date.get(int(day))
        if close is None:
            equity.append(None)
            continue
        if base <= 0.0:
            base = close
        equity.append(round(float(result.equity_yuan[0]) * close / base, 4))
    valid = [(idx, value) for idx, value in enumerate(equity) if value is not None]
    if len(valid) < 2:
        raise BacktestError(f"benchmark series is too short: {code}")
    benchmark_values = [float(value) for _, value in valid]
    first = benchmark_values[0]
    last = benchmark_values[-1]
    benchmark_return = last / first - 1.0 if first else 0.0
    benchmark_returns = np.asarray(
        [
            benchmark_values[index] / benchmark_values[index - 1] - 1.0
            for index in range(1, len(benchmark_values))
        ],
        dtype=np.float64,
    )
    strategy_returns = np.asarray(
        [float(result.returns[i]) for i, _ in valid[1:]], dtype=np.float64
    )
    excess = strategy_returns - benchmark_returns
    tracking_error = (
        float(np.std(excess, ddof=1) * np.sqrt(config.annual_days)) if excess.size > 1 else 0.0
    )
    information_ratio = (
        float(np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(config.annual_days))
        if excess.size > 1 and np.std(excess, ddof=1) > 0
        else 0.0
    )
    result.metrics["benchmark_return"] = round(float(benchmark_return), 8)
    result.metrics["excess_return"] = round(
        float(result.metrics.get("total_return", 0.0)) - benchmark_return, 8
    )
    result.metrics["tracking_error"] = round(tracking_error, 8)
    result.metrics["information_ratio"] = round(information_ratio, 8)
    result.benchmark = {
        "code": str(row.get("code", code)),
        "sec_id": sec_id,
        "name": str(row.get("name", "")),
        "dates": [int(day) for day in result.dates.tolist()],
        "equity": equity,
        "total_return": round(float(benchmark_return), 8),
        "metrics": {
            "benchmark_return": round(float(benchmark_return), 8),
            "excess_return": round(float(result.metrics["excess_return"]), 8),
            "tracking_error": round(tracking_error, 8),
            "information_ratio": round(information_ratio, 8),
        },
    }


def run_strategy_backtest(
    panel: PanelData | Snapshot,
    strategy: Any,
    config: BacktestConfig | None = None,
    *,
    strategy_metadata: dict[str, Any] | None = None,
) -> BacktestResult:
    """Generate targets with ``strategy`` and run them through the engine."""
    panel_data = panel.to_panel_data() if isinstance(panel, Snapshot) else panel
    weights = strategy.generate_targets(panel_data)
    metadata = strategy_metadata or (
        strategy.specification() if hasattr(strategy, "specification") else strategy.metadata()
    )
    snapshot_metadata = panel.describe() if isinstance(panel, Snapshot) else None
    return run_backtest(
        panel,
        weights,
        config,
        strategy_metadata=metadata,
        snapshot_metadata=snapshot_metadata,
    )
