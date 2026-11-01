#!/usr/bin/env python3
"""Python-side benchmark driver: panel I/O, kernels, C++ engine and wrapper overhead.

Run via ``make bench`` (also runs the C++ Google Benchmark suite).  Numbers are machine
specific; record notable results in docs/PERFORMANCE.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from tests.reference.engine_ref import RefConfig, run_reference

    import quantcore
    from quantcore import _qcore as qc
    from quantcore.backtest.config import BacktestConfig
    from quantcore.backtest.engine import run_backtest
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.snapshot.qpanel import write_qpanel

    panel_data = generate_synthetic_panel(
        SyntheticConfig(n_sec=300, start="2020-01-02", end="2023-12-29", seed=123)
    )
    weights = np.full((panel_data.n_time, panel_data.n_sec), np.nan)
    for day, flag in enumerate(panel_data.calendar.month_start_flags()):
        if flag:
            weights[day] = 0.0
            weights[day, :10] = 0.1

    out: dict[str, object] = {"n_sec": panel_data.n_sec, "n_time": panel_data.n_time}
    with tempfile.TemporaryDirectory(prefix="qc-bench-") as tmp:
        path = Path(tmp) / "panel.qpanel"
        t0 = time.perf_counter()
        write_qpanel(panel_data, path)
        out["qpanel_write_ms"] = (time.perf_counter() - t0) * 1e3
        t0 = time.perf_counter()
        panel = qc.Panel.open(str(path))
        out["qpanel_open_ms"] = (time.perf_counter() - t0) * 1e3
        for op_name, fn in [
            ("rolling_mean_close20", lambda: qc.kernels.rolling_panel(panel, "close", 20, "mean", "time_sec")),
            ("rolling_std_close20", lambda: qc.kernels.rolling_panel(panel, "close", 20, "std", "time_sec")),
            ("cross_rank_close", lambda: qc.kernels.cross_panel(panel, "close", "rank", "time_sec")),
            ("cross_zscore_close", lambda: qc.kernels.cross_panel(panel, "close", "zscore", "time_sec")),
        ]:
            t0 = time.perf_counter()
            fn()
            out[f"{op_name}_ms"] = (time.perf_counter() - t0) * 1e3

        config = qc.BacktestConfig(initial_cash=1_000_000.0, trace_level=1)
        engine = qc.Engine(panel, config)
        t0 = time.perf_counter()
        engine.run(weights)
        out["engine_run_ms"] = (time.perf_counter() - t0) * 1e3

        t0 = time.perf_counter()
        run_backtest(panel_data, weights, BacktestConfig(initial_cash=1_000_000.0))
        out["run_backtest_wrapper_ms"] = (time.perf_counter() - t0) * 1e3

        t0 = time.perf_counter()
        run_reference(panel_data, weights, RefConfig(initial_cash=10_000_000_000))
        out["reference_ms"] = (time.perf_counter() - t0) * 1e3

    out["backend"] = quantcore.engine_backend()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
