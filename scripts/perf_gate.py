#!/usr/bin/env python3
"""Performance regression gate around scripts/verify_cpp.py.

The absolute limits in verify_cpp.py catch gross breakage; this gate compares the
same deterministic 300x965 panel against a recorded local baseline so silent 2-3x
slowdowns fail.  Run ``make perf-gate`` or ``python scripts/perf_gate.py --write-baseline``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "performance-baseline.json"


def _run_verify() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_cpp.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:], file=sys.stderr)
        raise SystemExit("verify_cpp failed; cannot run performance gate")
    start = completed.stdout.find("{")
    if start < 0:
        raise SystemExit("verify_cpp produced no JSON summary")
    return json.loads(completed.stdout[start:])


def _load_baseline() -> dict[str, Any]:
    if not BASELINE.exists():
        raise SystemExit(f"missing {BASELINE}; run --write-baseline once")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    summary = _run_verify()
    checks = summary.get("checks") or {}
    metrics = {
        "open_ms": float(checks["open_ms"]),
        "factors_20_ms_8threads": float(checks["factors_20_ms_8threads"]),
        "backtest_ms": float(checks["backtest_ms"]),
        "cpp_vs_reference_ratio": float(checks["cpp_vs_reference_ratio"]),
    }
    if args.write_baseline:
        payload = {
            "measured_at": "2026-11-02",
            "host": "local",
            "panel": summary.get("panel", {}),
            "baseline": metrics,
            "tolerances": {
                "open_ms_max_factor": 2.5,
                "factors_20_ms_8threads_max_factor": 2.0,
                "backtest_ms_max_factor": 2.0,
                "cpp_vs_reference_ratio_min_factor": 0.5,
            },
        }
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE}: {metrics}")
        return 0
    baseline = _load_baseline()
    limits = baseline["tolerances"]
    failures: list[str] = []
    for key, max_factor_key in (
        ("open_ms", "open_ms_max_factor"),
        ("factors_20_ms_8threads", "factors_20_ms_8threads_max_factor"),
        ("backtest_ms", "backtest_ms_max_factor"),
    ):
        limit = float(baseline["baseline"][key]) * float(limits[max_factor_key])
        ok = metrics[key] <= limit
        print(f"{key}: {metrics[key]:.3f} <= {limit:.3f} {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(key)
    ratio_floor = float(baseline["baseline"]["cpp_vs_reference_ratio"]) * float(
        limits["cpp_vs_reference_ratio_min_factor"]
    )
    ratio_ok = metrics["cpp_vs_reference_ratio"] >= ratio_floor
    print(f"cpp_vs_reference_ratio: {metrics['cpp_vs_reference_ratio']:.1f} >= {ratio_floor:.1f} {'OK' if ratio_ok else 'FAIL'}")
    if not ratio_ok:
        failures.append("cpp_vs_reference_ratio")
    if failures:
        print(json.dumps({"ok": False, "failed": failures, "metrics": metrics}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "metrics": metrics}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
