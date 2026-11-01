"""QuantCore — local A-share quantitative research and backtesting workbench.

Python control plane for the ``qcore`` C++ core.  Everything here is research and
simulation tooling: no real order routing, and synthetic datasets are always labelled
``SYNTHETIC``.  Historical performance does not guarantee future results; nothing in
this package constitutes investment advice.
"""

from __future__ import annotations

from typing import Any

from .errors import (
    BacktestError,
    CppUnavailableError,
    DataValidationError,
    ExperimentError,
    LookaheadError,
    ProviderError,
    ProviderPermissionError,
    ProviderUnavailableError,
    QuantCoreError,
    SnapshotError,
    StrategyError,
    StrategyValidationError,
)

__version__ = "0.1.0"

_EXTENSION: Any = None
_EXTENSION_LOADED = False


def extension() -> Any:
    """Return the compiled ``quantcore._qcore`` module, or ``None`` if unavailable."""
    global _EXTENSION, _EXTENSION_LOADED
    if not _EXTENSION_LOADED:
        _EXTENSION_LOADED = True
        try:
            from . import _qcore  # type: ignore[attr-defined]

            _EXTENSION = _qcore
        except Exception:  # pragma: no cover - extension is required in production
            _EXTENSION = None
    return _EXTENSION


def _ready(flag: str, required: tuple[str, ...]) -> bool:
    module = extension()
    if module is None:
        return False
    if not all(hasattr(module, name) for name in required):
        return False
    probe = getattr(module, flag, None)
    if callable(probe):
        try:
            return bool(probe())
        except Exception:  # pragma: no cover - a broken build must not crash the CLI
            return False
    return True


def panel_available() -> bool:
    """True when the C++ ``.qpanel`` writer/reader is bound and self-checks."""
    return _ready("panel_ready", ("PanelWriter", "Panel"))


def kernels_available() -> bool:
    """True when C++ kernels are bound and pass their self-check."""
    return _ready("kernels_ready", ("rolling_mean", "cross_rank"))


def engine_available() -> bool:
    """True when the C++ backtest engine is bound and ready."""
    return _ready("engine_ready", ("Engine", "BacktestConfig"))


def expr_available() -> bool:
    """True when the C++ factor-expression DSL is bound."""
    return _ready("expr_ready", ("Expression",))


def engine_backend() -> str:
    """Return the active backtest backend; must be ``'cpp'`` for verification."""
    module = extension()
    if module is None:
        return "missing"
    return str(getattr(module, "engine_backend", "cpp"))


def cpp_version() -> str | None:
    module = extension()
    return None if module is None else str(getattr(module, "__version__", "unknown"))


def require_cpp() -> Any:
    module = extension()
    if module is None:
        raise CppUnavailableError("QuantCore C++ extension is not available; run `make build`")
    return module


def require_engine() -> Any:
    module = require_cpp()
    if not engine_available():
        raise CppUnavailableError(
            "QuantCore C++ backtest engine is not bound yet; rebuild the extension"
        )
    return module


def require_panel() -> Any:
    module = require_cpp()
    if not panel_available():
        raise CppUnavailableError(
            "QuantCore C++ .qpanel writer/reader is not bound yet; rebuild the extension"
        )
    return module


SYNTHETIC_DISCLAIMER = (
    "SYNTHETIC data: fabricated prices, rules and fundamentals. Not real market results."
)
INVESTMENT_DISCLAIMER = (
    "Historical performance does not guarantee future results and is not investment advice."
)

__all__ = [
    "INVESTMENT_DISCLAIMER",
    "SYNTHETIC_DISCLAIMER",
    "BacktestError",
    "CppUnavailableError",
    "DataValidationError",
    "ExperimentError",
    "LookaheadError",
    "ProviderError",
    "ProviderPermissionError",
    "ProviderUnavailableError",
    "QuantCoreError",
    "SnapshotError",
    "StrategyError",
    "StrategyValidationError",
    "__version__",
    "cpp_version",
    "engine_available",
    "engine_backend",
    "expr_available",
    "extension",
    "kernels_available",
    "panel_available",
    "require_cpp",
    "require_engine",
    "require_panel",
]
