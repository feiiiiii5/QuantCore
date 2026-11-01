"""qc CLI entry point (M0 stub; expanded in M4)."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print("qc: QuantCore CLI (data/snapshot/backtest/sweep/check/serve/bench)")
        return 0
    print(f"qc: unknown or not-yet-implemented command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
