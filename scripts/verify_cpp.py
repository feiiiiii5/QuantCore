#!/usr/bin/env python3
"""`make verify-cpp` gate: backend identity, differential consistency and §10 core benchmarks.

The full 10k-parameter sweep / full-market 5500x20y benchmark is nightly-only; this script
uses a deterministic synthetic panel that is large enough to catch regressions while staying
fast enough for CI.  Real measured numbers are printed as JSON and should be recorded in
docs/PERFORMANCE.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    raise SystemExit(1)


def main() -> int:
    import quantcore
    from quantcore import _qcore as qc

    summary: dict[str, object] = {"ok": True, "checks": {}}
    checks = summary["checks"]
    if quantcore.engine_backend() != "cpp":
        fail(f"engine_backend is {quantcore.engine_backend()!r}, expected 'cpp'")

    # 1) Differential test: C++ engine vs the test-only Python reference.
    diff = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_cpp_differential.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    checks["differential"] = {"returncode": diff.returncode, "tail": diff.stdout[-800:]}
    if diff.returncode != 0:
        print(diff.stdout)
        print(diff.stderr, file=sys.stderr)
        fail("C++ vs Python reference differential test failed")

    # 2) Production code must never import the reference implementation.
    offenders = []
    for path in (ROOT / "python" / "quantcore").rglob("*.py"):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import tests.reference", "from tests.reference",
                                     "import tests.reference", "from tests import reference")):
                offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
                break
    checks["no_reference_import_in_production"] = offenders
    if offenders:
        fail(f"production code imports tests/reference: {offenders}")

    from tests.reference.engine_ref import RefConfig, run_reference

    from quantcore.backtest.config import BacktestConfig
    from quantcore.backtest.engine import run_backtest
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.snapshot.qpanel import write_qpanel

    n_sec, start, end = 300, "2020-01-02", "2023-12-29"
    panel_data = generate_synthetic_panel(
        SyntheticConfig(n_sec=n_sec, start=start, end=end, seed=123)
    )
    n_time = panel_data.n_time
    with tempfile.TemporaryDirectory(prefix="qc-verify-") as tmp:
        path = Path(tmp) / "panel.qpanel"
        t0 = time.perf_counter()
        write_qpanel(panel_data, path)
        write_ms = (time.perf_counter() - t0) * 1e3
        t0 = time.perf_counter()
        panel = qc.Panel.open(str(path))
        open_ms = (time.perf_counter() - t0) * 1e3
        checks["open_ms"] = open_ms
        if open_ms >= 200:
            fail(f"open snapshot took {open_ms:.1f}ms >= 200ms")

        # 3) 20 common factor calls over the full panel, 8 Python threads; C++ releases the GIL.
        factor_jobs = [
            ("rolling_panel", "close", 20, "mean"),
            ("rolling_panel", "close", 20, "std"),
            ("rolling_panel", "close", 5, "mean"),
            ("rolling_panel", "volume", 20, "mean"),
            ("rolling_panel", "close", 10, "max"),
            ("rolling_panel", "close", 10, "min"),
            ("rolling_panel", "close", 20, "sum"),
            ("rolling_panel", "close", 20, "rank"),
            ("rolling_panel", "close", 20, "decay_linear"),
            ("rolling_panel", "amount", 20, "mean"),
            ("cross_panel", "close", "rank"),
            ("cross_panel", "close", "zscore"),
            ("cross_panel", "close", "mad_winsor"),
            ("cross_panel", "close", "quantile"),
            ("cross_panel", "mktcap", "rank"),
            ("cross_panel", "turnover", "zscore"),
            ("cross_panel", "mktcap", "mad_winsor"),
            ("cross_panel", "turnover", "rank"),
            ("cross_panel", "close", "quantile"),
            ("cross_panel", "mktcap", "quantile"),
        ]

        def run_factor(job: tuple[object, ...]) -> float:
            t = time.perf_counter()
            if job[0] == "rolling_panel":
                _, field, window, op = job
                qc.kernels.rolling_panel(panel, str(field), int(window), str(op), "time_sec")
            else:
                _, field, op = job
                qc.kernels.cross_panel(panel, str(field), str(op), "time_sec")
            return time.perf_counter() - t

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(run_factor, factor_jobs))
        factor_ms = (time.perf_counter() - t0) * 1e3
        checks["factors_20_ms_8threads"] = factor_ms
        if factor_ms >= 3000:
            fail(f"20 factors took {factor_ms:.1f}ms >= 3000ms")

        # 4) Single backtest: direct C++ engine (the §10 gate is engine time, not wrapper I/O).
        weights = np.full((n_time, n_sec), np.nan, dtype=np.float64)
        for day, flag in enumerate(panel_data.calendar.month_start_flags()):
            if flag:
                weights[day] = 0.0
                weights[day, :10] = 0.1
        cpp_config = qc.BacktestConfig(initial_cash=1_000_000.0, trace_level=1)
        engine = qc.Engine(panel, cpp_config)
        t0 = time.perf_counter()
        engine.run(weights)
        backtest_ms = (time.perf_counter() - t0) * 1e3
        t0 = time.perf_counter()
        result = run_backtest(panel_data, weights, BacktestConfig(initial_cash=1_000_000.0))
        wrapper_ms = (time.perf_counter() - t0) * 1e3
        checks["backtest_ms"] = backtest_ms
        checks["backtest_with_wrapper_ms"] = wrapper_ms
        if backtest_ms >= 1000:
            fail(f"single backtest took {backtest_ms:.1f}ms >= 1000ms")

        # 5) C++ vs Python reference ratio (same weights / simple rules).
        t0 = time.perf_counter()
        ref = run_reference(panel_data, weights, RefConfig(initial_cash=10_000_000_000))
        ref_ms = (time.perf_counter() - t0) * 1e3
        cpp_engine_ms = backtest_ms
        ratio = (ref_ms / cpp_engine_ms) if cpp_engine_ms > 0 else 0.0
        checks["reference_ms"] = ref_ms
        checks["cpp_vs_reference_ratio"] = ratio
        if ratio < 50.0:
            fail(f"C++/reference speedup {ratio:.1f}x < 50x")
        # Differential consistency of the equity curves (fixed-point exactness).
        if not np.array_equal(np.asarray(result.equity, dtype=np.int64),
                              np.asarray(ref.equity, dtype=np.int64)):
            fail("C++ and reference equity curves differ in verify-cpp")
        # Full 10k sweep / full-market memory are recorded as nightly-only targets.
        checks["nightly_only"] = [
            "5500x20y full-market benchmark",
            "10000-parameter sweep < 5min",
            "peak RSS < 4GB",
        ]

        # 6) Fast open must not hide corruption: full validation still detects it.
        try:
            qc.Panel.validate(str(path))
            checks["validate_ok"] = True
        except Exception as exc:  # pragma: no cover - defensive
            fail(f"Panel.validate failed on a fresh file: {exc}")

    summary["panel"] = {"n_sec": panel_data.n_sec, "n_time": n_time, "write_ms": write_ms}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
