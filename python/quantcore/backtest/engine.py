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
    if result.engine_backend != "cpp":  # pragma: no cover - defensive
        raise BacktestError(f"engine_backend must be 'cpp', got {result.engine_backend!r}")
    return result


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
