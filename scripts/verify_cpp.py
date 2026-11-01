#!/usr/bin/env python3
"""Verify C++ backend identity, differential consistency and baseline benchmarks."""
from __future__ import annotations

import json
import sys


def main() -> int:
    import quantcore

    backend = quantcore.engine_backend()
    print(json.dumps({"engine_backend": backend, "version": quantcore.__version__}))
    if backend != "cpp":
        print("verify-cpp: C++ extension missing", file=sys.stderr)
        return 1
    print("verify-cpp: TODO(M1-M3) differential+bench gates will be enforced here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
