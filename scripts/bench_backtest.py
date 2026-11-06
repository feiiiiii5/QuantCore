#!/usr/bin/env python3
"""Five-run median timings for native backtests and their local data adapter.

The same fixed-seed panel and precomputed monthly weights are used for every
measurement. Panel generation and signal construction are reported separately.
All generated files live in an automatically removed system temporary directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))


def measure(function: Any, repeats: int = 5) -> dict[str, Any]:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1_000)
    return {"median_ms": statistics.median(samples), "samples_ms": samples}


def main() -> None:
    from quantcore import require_engine
    from quantcore.backtest.config import BacktestConfig
    from quantcore.backtest.engine import (
        _apply_risk_limits,
        _cached_qpanel_path,
        _corporate_actions,
        _cpp_config,
        run_backtest,
        run_backtest_batch,
    )
    from quantcore.data.matrices import MatrixLayout
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.snapshot import build_snapshot, load_snapshot
    from quantcore.snapshot.qpanel import write_qpanel
    from quantcore.templates.registry import create_template

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-sec", type=int, default=200)
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2023-12-29")
    args = parser.parse_args()
    started = time.perf_counter()
    panel = generate_synthetic_panel(
        SyntheticConfig(
            n_sec=args.n_sec,
            start=args.start,
            end=args.end,
            seed=123,
        )
    )
    generated_ms = (time.perf_counter() - started) * 1_000

    def signals() -> np.ndarray:
        weights = np.full((panel.n_time, panel.n_sec), np.nan)
        count = min(10, panel.n_sec)
        for day, flag in enumerate(panel.calendar.month_start_flags()):
            if flag:
                weights[day] = 0.0
                weights[day, :count] = 1.0 / count
        return weights

    weights = signals()
    settings = BacktestConfig()
    module = require_engine()
    output: dict[str, Any] = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "shape": [panel.n_time, panel.n_sec],
        "bars_rows": len(panel.bars),
        "seed": 123,
        "repeats": 5,
        "generated_ms": generated_ms,
        "weights_sha256": hashlib.sha256(weights.tobytes()).hexdigest(),
        "signal_construction": measure(signals),
        "content_hash": measure(panel.content_hash),
        "risk_adapter": measure(lambda: _apply_risk_limits(weights, settings)),
    }

    def pivot_matrix(layout: Any, name: str, fill: float = np.nan) -> np.ndarray:
        pivot = layout.bars[["date", "sec_id", name]].pivot_table(
            index="date", columns="sec_id", values=name, aggfunc="last"
        )
        values = pivot.reindex(index=layout.dates, columns=layout.sec_ids).to_numpy(
            dtype=np.float64
        )
        return values if np.isnan(fill) else np.where(np.isnan(values), fill, values)

    output["candidate_signals"] = {}
    for name in ("trend_momentum", "liquid_reversal", "defensive_low_vol"):
        strategy = create_template(name)
        generate = partial(strategy.generate_targets, panel)
        optimized_weights = generate()
        optimized_timing = measure(generate)
        with patch.object(MatrixLayout, "matrix", pivot_matrix):
            reference_weights = generate()
            reference_timing = measure(generate)
        np.testing.assert_array_equal(optimized_weights, reference_weights)
        output["candidate_signals"][name] = {
            "optimized": optimized_timing,
            "pivot_reference": reference_timing,
            "speedup": reference_timing["median_ms"] / optimized_timing["median_ms"],
            "weights_sha256": hashlib.sha256(optimized_weights.tobytes()).hexdigest(),
            "params": strategy.params.model_dump(mode="json"),
        }
    if sys.platform == "darwin":
        output["machine"]["cpu"] = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            text=True,
            timeout=5,
        ).strip()
    with tempfile.TemporaryDirectory(prefix="qc-backtest-bench-") as temporary:
        path = Path(temporary) / "panel.qpanel"
        output["qpanel_export"] = measure(lambda: write_qpanel(panel, path))
        output["qpanel_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        native_panel = module.Panel.open(str(path))
        native_config = _cpp_config(
            module,
            settings,
            panel.calendar,
            _corporate_actions(panel, settings, panel.sec_id_list),
        )
        engine = module.Engine(native_panel, native_config)
        engine.run(weights)  # warm the mapping before the five timed samples
        output["native_entrypoint"] = measure(lambda: engine.run(weights))
        _cached_qpanel_path(panel)  # warm serialization cache, still rehashes each call
        output["wrapper_warm"] = measure(lambda: run_backtest(panel, weights, settings))
        output["batch_four_threads_two"] = measure(
            lambda: run_backtest_batch(
                panel,
                [weights] * 4,
                settings,
                threads=2,
            )
        )
        result = run_backtest(panel, weights, settings)
        output["equity_sha256"] = hashlib.sha256(result.equity.tobytes()).hexdigest()
        output["trade_count"] = len(result.trades)
        snapshot_root = Path(temporary) / "snapshots"
        manifest = build_snapshot(panel, snapshot_root)
        snapshot = load_snapshot(snapshot_root, manifest.snapshot_id)
        run_backtest(snapshot, weights, settings)
        output["wrapper_snapshot_warm"] = measure(lambda: run_backtest(snapshot, weights, settings))
        snapshot_result = run_backtest(snapshot, weights, settings)
        np.testing.assert_array_equal(snapshot_result.equity, result.equity)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
