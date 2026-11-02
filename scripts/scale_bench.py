#!/usr/bin/env python3
"""Scale benchmark for the panel data path, .qpanel mmap and the C++ engine.

Measures the reproducible "full-market scale" numbers that docs/PERFORMANCE.md marks
as nightly-only: synthetic panel construction, Parquet warehouse write/read, .qpanel
write/open (mmap), one C++ engine backtest and the process peak RSS.

Everything is SYNTHETIC and written under a temporary directory: no network access
and no permanent artifacts.  Run make bench-scale (small default) or::

    uv run python scripts/scale_bench.py --n-sec 5500 --json

The default 800 securities x 2020-2024 (about 1210 trading days, 17 panel fields)
finishes in well under a minute and stays within a few hundred MiB.  --n-sec 5500 is
the full A-share scale; it needs enough RAM (roughly several GiB peak) and takes
minutes, so it is documented as an opt-in run rather than a CI gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

MIB = 1024.0 * 1024.0
DEFAULT_TOP_N = 50
ENGINE_RUNS = 3
MIN_SYNTHETIC_DAYS = 120


def _timed(function: Any, repeats: int = 1) -> tuple[float, Any]:
    """Return (best_seconds, last_value) over repeats calls."""
    best = float("inf")
    value: Any = None
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        value = function()
        best = min(best, time.perf_counter() - started)
    return best, value


def _peak_rss() -> dict[str, Any]:
    """Process-wide peak RSS, normalised to MiB (macOS reports bytes, Linux KiB)."""
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows has no resource module
        return {"mib": None, "raw": None, "unit": "unavailable"}
    raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return {"mib": round(raw / MIB, 1), "raw": raw, "unit": "bytes"}
    return {"mib": round(raw / 1024.0, 1), "raw": raw, "unit": "kib"}


def _machine_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "python": platform.python_version(),
    }
    if sys.platform == "darwin":
        for key, command in (
            ("cpu", ["sysctl", "-n", "machdep.cpu.brand_string"]),
            ("memory_bytes", ["sysctl", "-n", "hw.memsize"]),
        ):
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=5, check=False
                )
            except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
                continue
            text = completed.stdout.strip()
            if completed.returncode == 0 and text:
                info[key] = text
        memory = info.get("memory_bytes")
        if isinstance(memory, str) and memory.isdigit():
            info["memory_gib"] = round(int(memory) / (1024.0**3), 1)
    return info


def _monthly_weights(panel: Any, top_n: int) -> Any:
    """Equal-weight the first top_n securities on month-start rebalances."""
    import numpy as np

    count = max(1, min(int(top_n), panel.n_sec))
    weights = np.full((panel.n_time, panel.n_sec), np.nan, dtype=np.float64)
    for day, flag in enumerate(panel.calendar.month_start_flags()):
        if flag:
            weights[day] = 0.0
            weights[day, :count] = 1.0 / count
    return weights


def _scale_summary(panel: Any, fields: int) -> dict[str, Any]:
    from quantcore.calendar import date_str

    points = panel.n_sec * panel.n_time
    return {
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
        "start": date_str(int(panel.calendar.dates[0])),
        "end": date_str(int(panel.calendar.dates[-1])),
        "bars_rows": len(panel.bars),
        "financials_rows": len(panel.financials),
        "corporate_actions_rows": len(panel.corporate_actions),
        "fields": fields,
        "matrix_points": points,
        "raw_matrix_mib": round(points * fields * 8 / MIB, 1),
    }


def _run(args: argparse.Namespace, started: float) -> dict[str, Any]:
    import numpy as np

    import quantcore
    from quantcore.calendar import TradingCalendar, date_str, from_date_int, to_date_int
    from quantcore.data.panel import PANEL_FIELDS
    from quantcore.data.store import ParquetStore
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.snapshot.qpanel import write_qpanel

    if args.n_sec < 1:
        raise ValueError("--n-sec must be >= 1")
    start, end = to_date_int(args.start), to_date_int(args.end)
    if start >= end:
        raise ValueError("--start must be earlier than --end")
    calendar = TradingCalendar.weekdays(start, end)
    # The synthetic generator needs at least MIN_SYNTHETIC_DAYS trading days; short
    # smoke windows are padded backwards and then truncated to the requested range.
    generation_start = start
    while len(calendar) < MIN_SYNTHETIC_DAYS:
        generation_start = to_date_int(from_date_int(generation_start) - dt.timedelta(days=7))
        calendar = TradingCalendar.weekdays(generation_start, end)
    if generation_start != start:
        print(
            f"[scale-bench] note: {date_str(start)}..{date_str(end)} has fewer than "
            f"{MIN_SYNTHETIC_DAYS} synthetic trading days; generating from "
            f"{date_str(generation_start)} and truncating to the requested window",
            file=sys.stderr,
        )
    requested_days = len(TradingCalendar.weekdays(start, end))
    # Measured on an M2 Pro: 800 x 1208 peaks at ~1.6 GiB, dominated by pandas panel
    # generation; scale the warning linearly so a full-market run is never a surprise.
    estimated_peak_mib = 1600.0 * (requested_days * args.n_sec) / (1208.0 * 800.0)
    if estimated_peak_mib > 4096.0:
        print(
            f"[scale-bench] warning: estimated peak RSS ~{estimated_peak_mib / 1024.0:.1f} GiB; "
            "full-market runs need plenty of free RAM (>=16 GiB recommended) and may take minutes",
            file=sys.stderr,
        )

    backend = quantcore.engine_backend()
    if not (quantcore.panel_available() and quantcore.engine_available()):
        raise RuntimeError(
            f"C++ bindings unavailable (engine_backend={backend!r}); "
            "run make build before the scale benchmark"
        )

    print(
        f"[scale-bench] generating SYNTHETIC panel n_sec={args.n_sec} "
        f"{args.start}..{args.end} (seed={args.seed})",
        file=sys.stderr,
    )
    config = SyntheticConfig(n_sec=args.n_sec, start=generation_start, end=end, seed=args.seed)

    def _build_panel() -> Any:
        generated = generate_synthetic_panel(config)
        return generated.select(start, end) if generation_start != start else generated

    generate_s, panel = _timed(_build_panel)
    scale = _scale_summary(panel, len(PANEL_FIELDS))

    with tempfile.TemporaryDirectory(prefix="qc-scale-bench-") as directory:
        workspace = Path(directory)

        print("[scale-bench] writing/reading Parquet warehouse", file=sys.stderr)
        store = ParquetStore(workspace / "warehouse")
        parquet_write_s, _ = _timed(lambda: store.write_panel(panel))
        parquet_mib = (
            sum(path.stat().st_size for path in (workspace / "warehouse").rglob("*.parquet")) / MIB
        )
        parquet_read_s, bars_read = _timed(lambda: store.read_dataset("bars"))
        if len(bars_read) != len(panel.bars):
            raise RuntimeError(
                f"Parquet round-trip row mismatch: {len(bars_read)} != {len(panel.bars)}"
            )

        print("[scale-bench] writing/opening .qpanel", file=sys.stderr)
        qpanel_path = workspace / "panel.qpanel"
        qpanel_write_s, qpanel_info = _timed(lambda: write_qpanel(panel, qpanel_path))
        qpanel_mib = float(qpanel_info["bytes"]) / MIB
        module = quantcore.require_panel()
        qpanel_open_s, panel_object = _timed(lambda: module.Panel.open(str(qpanel_path)), 3)

        print(f"[scale-bench] running the C++ engine ({ENGINE_RUNS} timed runs)", file=sys.stderr)
        weights = np.ascontiguousarray(_monthly_weights(panel, DEFAULT_TOP_N))
        engine_config = module.BacktestConfig(
            start=int(panel.calendar.dates[0]),
            end=int(panel.calendar.dates[-1]),
            initial_cash=1_000_000.0,
            trace_level=1,
            seed=args.seed,
        )
        engine = module.Engine(panel_object, engine_config)
        engine_s, first_result = _timed(lambda: engine.run(weights), ENGINE_RUNS)
        again = engine.run(weights)
        deterministic = bool(
            np.array_equal(np.asarray(first_result.equity), np.asarray(again.equity))
        )

    return {
        "ok": True,
        "synthetic": True,
        "disclaimer": "SYNTHETIC data: fabricated prices and rules, not real market results.",
        "backend": backend,
        "machine": _machine_info(),
        "panel": scale,
        "timings_s": {
            "synthetic_generate": round(generate_s, 3),
            "parquet_write": round(parquet_write_s, 3),
            "parquet_read": round(parquet_read_s, 3),
            "qpanel_write": round(qpanel_write_s, 3),
            "qpanel_open": round(qpanel_open_s, 4),
            "engine_backtest": round(engine_s, 4),
        },
        "sizes": {
            "parquet_mib": round(parquet_mib, 1),
            "qpanel_mib": round(qpanel_mib, 1),
        },
        "engine": {
            "timed_runs": ENGINE_RUNS,
            "top_n": min(DEFAULT_TOP_N, scale["n_sec"]),
            "trades": len(first_result.trades),
            "deterministic": deterministic,
        },
        "rss": _peak_rss(),
        "elapsed_s": round(time.perf_counter() - started, 2),
    }


def _print_human(result: dict[str, Any]) -> None:
    machine = result["machine"]
    panel = result["panel"]
    timings = result["timings_s"]
    rss = result["rss"]
    cpu = machine.get("cpu") or machine.get("processor", "unknown")
    memory = f"{machine['memory_gib']} GiB" if "memory_gib" in machine else "unknown RAM"
    print("QuantCore scale benchmark — SYNTHETIC data, offline, temporary directory")
    print(f"  machine    : {cpu} / {machine['platform']} / {memory}")
    print(f"  python     : {machine['python']}  backend={result['backend']}")
    print(
        f"  panel      : {panel['n_sec']} sec x {panel['n_time']} days "
        f"({panel['start']}..{panel['end']}) = {panel['matrix_points']:,} points "
        f"x {panel['fields']} fields"
    )
    print(
        f"  data       : bars={panel['bars_rows']:,} rows, "
        f"raw matrices ~{panel['raw_matrix_mib']:.1f} MiB, "
        f"parquet={result['sizes']['parquet_mib']:.1f} MiB, "
        f"qpanel={result['sizes']['qpanel_mib']:.1f} MiB"
    )
    print("  timings    :")
    for label, key in (
        ("synthetic panel build", "synthetic_generate"),
        ("Parquet write", "parquet_write"),
        ("Parquet read (bars)", "parquet_read"),
        (".qpanel write (mmap file)", "qpanel_write"),
        (".qpanel open (mmap)", "qpanel_open"),
        ("C++ engine backtest", "engine_backtest"),
    ):
        value = timings[key]
        shown = f"{value * 1000.0:.1f} ms" if value < 1.0 else f"{value:.3f} s"
        print(f"    {label:<26} {shown}")
    print(
        f"  engine     : {result['engine']['trades']} trades, "
        f"deterministic={result['engine']['deterministic']}"
    )
    if rss["mib"] is None:
        print("  peak RSS   : unavailable on this platform")
    else:
        print(f"  peak RSS   : {rss['mib']:.1f} MiB (process peak, {rss['unit']})")
    print(f"  wall time  : {result['elapsed_s']:.2f} s")
    print("  note       : historical performance does not guarantee future results.")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QuantCore scale benchmark (synthetic panel -> Parquet/.qpanel -> C++ engine).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-sec", type=int, default=800, help="number of synthetic securities")
    parser.add_argument("--start", default="2020-01-02", help="first calendar date")
    parser.add_argument("--end", default="2024-12-31", help="last calendar date")
    parser.add_argument("--seed", type=int, default=42, help="synthetic data seed")
    parser.add_argument(
        "--json", action="store_true", help="print a JSON summary instead of the text report"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    started = time.perf_counter()
    try:
        result = _run(args, started)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("[scale-bench] interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[scale-bench] ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
