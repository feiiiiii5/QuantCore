"""Market-data providers (synthetic / local files / Tushare / AKShare / mootdx)."""

from __future__ import annotations

from ..errors import ProviderError, ProviderPermissionError, ProviderUnavailableError
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    RateLimiter,
    RetryPolicy,
    retry_call,
    subset_frame,
)
from .localfile import LocalFileProvider
from .mootdx import MootdxProvider
from .registry import create_provider, describe_providers, list_providers, register_provider
from .synthetic import SyntheticProvider
from .tushare import TushareProvider

__all__ = [
    "DataProvider",
    "LocalFileProvider",
    "MootdxProvider",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderPermission",
    "ProviderPermissionError",
    "ProviderQuota",
    "ProviderUnavailableError",
    "RateLimiter",
    "RetryPolicy",
    "SyntheticProvider",
    "TushareProvider",
    "create_provider",
    "describe_providers",
    "list_providers",
    "register_provider",
    "retry_call",
    "subset_frame",
]
