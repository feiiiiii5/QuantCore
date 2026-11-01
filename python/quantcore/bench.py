"""Python-side benchmarks for ingest, ``.qpanel`` I/O and C++ engine runs.

Run via ``qc bench`` or ``python scripts/bench.py``.  Thresholds follow the PLAN M0-M3
gates where they apply to the Python control plane; failures are reported, not faked.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

import quantcore


def _timed(function: Any, repeats: int = 1) -> tuple[float, Any]:
    best = float("inf")
    value: Any = None
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        value = function()
        best = min(best, time.perf_counter() - started)
    return best * 1000.0, value


def run_benchmarks(n_sec: int = 200, n_time_years: int = 5) -> dict[str, Any]:
    """Measure the Python-side data path and one engine run."""
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.snapshot.qpanel import panel_available, write_qpanel

    results: dict[str, Any] = {
        "synthetic_n_sec": n_sec,
        "engine_backend": quantcore.engine_backend(),
        "checks": {},
    }
    config = SyntheticConfig(
        n_sec=n_sec,
        start=f"{2025 - n_time_years}-01-02",
        end="2024-12-31",
        seed=42,
    )
    generation_ms, panel = _timed(lambda: generate_synthetic_panel(config))
    results["synthetic_generate_ms"] = round(generation_ms, 2)
    results["synthetic_rows"] = len(panel.bars)
    results["checks"]["synthetic_under_10s"] = generation_ms < 10_000

    if not panel_available():
        results["error"] = "C++ .qpanel writer unavailable; engine benchmarks skipped"
        return results

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="qc-bench-") as directory:
        path = Path(directory) / "panel.qpanel"
        write_ms, info = _timed(lambda: write_qpanel(panel, path))
        results["qpanel_write_ms"] = round(write_ms, 2)
        results["qpanel_mb"] = round(float(info["bytes"]) / (1024 * 1024), 2)

        open_ms, panel_object = _timed(lambda: quantcore.require_panel().Panel.open(str(path)), 3)
        results["qpanel_open_ms"] = round(open_ms, 2)
        results["checks"]["qpanel_open_under_200ms"] = open_ms < 200.0

        module = quantcore.extension()
        if quantcore.engine_available() and panel_object is not None:
            weights = np.full((panel.n_time, panel.n_sec), np.nan, dtype=np.float64)
            flags = panel.calendar.month_start_flags()
            for day, flag in enumerate(flags):
                if flag:
                    weights[day] = 0.0
                    weights[day, : min(20, panel.n_sec)] = 1.0 / min(20, panel.n_sec)
            cpp_config = module.BacktestConfig(
                start=int(panel.calendar.dates[0]),
                end=int(panel.calendar.dates[-1]),
                initial_cash=1_000_000.0,
                seed=42,
            )
            engine = module.Engine(panel_object, cpp_config)
            run_ms, result = _timed(lambda: engine.run(np.ascontiguousarray(weights)), 3)
            results["engine_run_ms"] = round(run_ms, 2)
            results["engine_trades"] = len(result.trades)
            results["engine_equity_last_yuan"] = float(result.equity[-1]) / 10000.0
            results["checks"]["engine_run_under_1000ms"] = run_ms < 1000.0
            # Determinism: the same inputs must produce identical arrays.
            again = engine.run(np.ascontiguousarray(weights))
            results["checks"]["engine_deterministic"] = bool(
                np.array_equal(np.asarray(result.equity), np.asarray(again.equity))
            )
    return results
