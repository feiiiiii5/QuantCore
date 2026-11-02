"""Typed exceptions shared across the QuantCore Python control plane."""

from __future__ import annotations


class QuantCoreError(Exception):
    """Base class for all QuantCore control-plane errors."""


class CppUnavailableError(QuantCoreError):
    """Raised when a capability requires the compiled ``quantcore._qcore`` extension."""


class DataValidationError(QuantCoreError):
    """Raised when a dataset does not conform to the canonical schema."""


class ProviderError(QuantCoreError):
    """Base class for data-provider failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when an optional provider dependency cannot be imported or configured."""


class ProviderPermissionError(ProviderError):
    """Raised when a provider requires credentials/permission that are not available."""


class SnapshotError(QuantCoreError):
    """Raised when a snapshot cannot be built, verified or loaded."""


class StrategyError(QuantCoreError):
    """Base class for strategy loading/validation failures."""


class StrategyValidationError(StrategyError):
    """Raised when a strategy spec or template parameters are invalid."""


class LookaheadError(StrategyError):
    """Raised when a strategy accesses data after the decision date."""


class BacktestError(QuantCoreError):
    """Raised when a backtest cannot be executed."""


class ExperimentError(QuantCoreError):
    """Raised when an experiment record is missing or inconsistent."""


class DemoError(QuantCoreError):
    """Raised when the one-command ``qc demo`` pipeline cannot run (e.g. engine missing)."""
