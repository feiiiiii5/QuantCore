"""Provider registry: look up providers by name with lazy imports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..errors import ProviderUnavailableError
from .base import DataProvider

ProviderFactory = Callable[..., DataProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register (or replace) a provider factory under ``name``."""
    _REGISTRY[name.strip().lower()] = factory


def _synthetic(**kwargs: Any) -> DataProvider:
    from .synthetic import SyntheticProvider

    return SyntheticProvider(**kwargs)


def _local(**kwargs: Any) -> DataProvider:
    from .localfile import LocalFileProvider

    return LocalFileProvider(**kwargs)


def _tushare(**kwargs: Any) -> DataProvider:
    from .tushare import TushareProvider

    return TushareProvider(**kwargs)


def _akshare(**kwargs: Any) -> DataProvider:
    from .akshare import AKShareProvider

    return AKShareProvider(**kwargs)


def _mootdx(**kwargs: Any) -> DataProvider:
    from .mootdx import MootdxProvider

    return MootdxProvider(**kwargs)


for _name, _factory in (
    ("synthetic", _synthetic),
    ("local", _local),
    ("tushare", _tushare),
    ("akshare", _akshare),
    ("mootdx", _mootdx),
):
    register_provider(_name, _factory)


def list_providers() -> list[str]:
    """Names of all registered providers, sorted for deterministic CLI output."""
    return sorted(_REGISTRY)


def create_provider(name: str, **kwargs: Any) -> DataProvider:
    """Instantiate the provider registered under ``name``."""
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise ProviderUnavailableError(
            f"unknown provider {name!r}; available: {', '.join(list_providers())}"
        )
    return _REGISTRY[key](**kwargs)


def describe_providers() -> list[dict[str, Any]]:
    """Static capability/quota/permission descriptors (no instantiation)."""
    rows: list[dict[str, Any]] = []
    for name in list_providers():
        try:
            instance = _REGISTRY[name]()
        except Exception as exc:  # pragma: no cover - descriptors are best effort
            rows.append({"name": name, "error": str(exc)})
            continue
        rows.append(
            {
                "name": name,
                "class": type(instance).__name__,
                "capabilities": instance.capabilities.to_dict(),
                "quota": instance.quota.to_dict(),
                "permission": instance.permission.describe(),
            }
        )
    return rows
