"""Prevent incremental imports from silently mixing sources or security universes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.store import ParquetStore
from ..errors import ProviderError
from ..providers.base import DataProvider


def _canonical(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _codes(provider: str, codes: Iterable[str] | None) -> list[str] | None:
    values = list(codes) if codes is not None else []
    if not values:
        return None
    if provider in {"tushare", "sina", "eastmoney", "akshare", "mootdx"}:
        from ..providers.public_web import normalize_code

        return sorted({normalize_code(code) for code in values})
    return sorted({str(code).strip().upper() for code in values})


def source_identity(provider: DataProvider, codes: Iterable[str] | None) -> dict[str, Any]:
    """Persist only source-affecting settings; never tokens, transports or quotas."""
    name = provider.name
    options: dict[str, Any] = {}
    if name == "synthetic":
        options = asdict(provider.config)  # type: ignore[attr-defined]
        options.pop("start", None)
        options.pop("end", None)
    elif name == "local":
        local = {
            "directory": str(Path(provider.data_dir).resolve()),  # type: ignore[attr-defined]
            "column_mapping": provider.column_mapping,  # type: ignore[attr-defined]
            "file_names": provider.file_names,  # type: ignore[attr-defined]
        }
        options["source_id"] = hashlib.sha256(
            json.dumps(local, sort_keys=True).encode()
        ).hexdigest()
    elif name == "tushare":
        fixture = provider.fixture_dir  # type: ignore[attr-defined]
        options["mode"] = "fixture" if fixture is not None else "live"
        if fixture is not None:
            options["source_id"] = hashlib.sha256(str(Path(fixture).resolve()).encode()).hexdigest()
    elif name in {"sina", "eastmoney"}:
        options["limit"] = provider.limit  # type: ignore[attr-defined]
        if name == "sina":
            options["derive_actions"] = provider.derive_actions  # type: ignore[attr-defined]
            options["index_symbol"] = provider.index_symbol  # type: ignore[attr-defined]
    return _canonical(
        {
            "provider": name,
            "codes": _codes(name, codes or getattr(provider, "codes", None)),
            "options": options,
        }
    )


def check_incremental_identity(
    store: ParquetStore, identity: dict[str, Any], bars: pd.DataFrame
) -> None:
    prior = store.get_metadata("ingest_identity")
    if prior is None:
        metadata = store.get_metadata("panel_meta", {}) or {}
        provider = metadata.get("provider")
        if provider is None and set(bars["source"]) == {"SYNTHETIC"}:
            provider = "synthetic"
        options: dict[str, Any] = {}
        if provider == "synthetic" and metadata.get("config"):
            options = dict(metadata["config"])
            options.pop("start", None)
            options.pop("end", None)
        elif identity["options"]:
            raise ProviderError(
                "legacy warehouse has insufficient source identity; use reset or a non-incremental import"
            )
        requested_codes = identity["codes"]
        prior = _canonical(
            {
                "provider": provider,
                "codes": _codes(
                    str(provider), bars["sec_id" if provider == "synthetic" else "code"]
                )
                if requested_codes
                else None,
                "options": options,
            }
        )
    if prior != identity:
        raise ProviderError(
            "incremental source identity changed (provider, codes or settings); "
            "use reset or a non-incremental import to replace the warehouse"
        )
