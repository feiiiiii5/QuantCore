"""Live A-share quotes for the local UI (read-only, network opt-in)."""

from __future__ import annotations

from .clock import market_clock, market_phase, now_shanghai
from .quotes import INDEX_SPECS, Quote, QuoteSourceError
from .service import LiveQuoteService, LiveStatusSnapshot

__all__ = [
    "INDEX_SPECS",
    "LiveQuoteService",
    "LiveStatusSnapshot",
    "Quote",
    "QuoteSourceError",
    "market_clock",
    "market_phase",
    "now_shanghai",
]
