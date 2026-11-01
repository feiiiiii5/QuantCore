"""Ingestion: provider fetch -> quality gate -> snapshot-ready warehouse."""

from __future__ import annotations

from .pipeline import IngestResult, ProviderIngestor

__all__ = ["IngestResult", "ProviderIngestor"]
