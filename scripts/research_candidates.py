#!/usr/bin/env python3
"""Run a fixed offline candidate study on an existing local warehouse or synthetic data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))


def main() -> None:
    from quantcore.data.store import ParquetStore
    from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
    from quantcore.research.candidates import run_candidate_study

    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data-root", type=Path, help="existing data root or warehouse directory")
    source.add_argument(
        "--synthetic", action="store_true", help="fabricated software-check data only"
    )
    parser.add_argument("--output", required=True, type=Path, help="new or empty study directory")
    parser.add_argument("--annual-holdout", action="store_true")
    parser.add_argument(
        "--development-start", default="20210101", help="fixed development start date"
    )
    parser.add_argument("--holdout-start", default="20230101", help="fixed holdout split date")
    args = parser.parse_args()
    if args.synthetic:
        data = generate_synthetic_panel(
            SyntheticConfig(n_sec=6, start="2019-01-02", end="2024-12-31", seed=42)
        )
    else:
        root = args.data_root
        warehouse = root if (root / "warehouse_manifest.json").is_file() else root / "warehouse"
        if not (warehouse / "warehouse_manifest.json").is_file():
            parser.error(f"no existing warehouse manifest under {root}")
        data = ParquetStore(warehouse)
    study = run_candidate_study(
        data,
        args.output,
        annual_holdout=args.annual_holdout,
        development_start=args.development_start,
        holdout_start=args.holdout_start,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "synthetic": study["data"]["synthetic"],
                "runs": len(study["results"]),
                "report": str(args.output / "report.md"),
            }
        )
    )


if __name__ == "__main__":
    main()
