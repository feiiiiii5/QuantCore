"""QuantCore — local A-share quantitative research and backtesting workbench."""
from __future__ import annotations

__version__ = "0.1.0"

try:
    from . import _qcore  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - extension is required in production
    _qcore = None


def engine_backend() -> str:
    """Return the active backtest backend; must be 'cpp' for verification."""
    if _qcore is None:
        return "missing"
    return getattr(_qcore, "engine_backend", "cpp")


def require_cpp() -> None:
    if engine_backend() != "cpp":
        raise RuntimeError("QuantCore C++ extension is not available; run `make build`")
