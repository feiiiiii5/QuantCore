"""Local A-share paper accounts over historical snapshots or fresh public quotes.

Sessions mutate only their JSON account state. Quote fetching belongs to the server's
read-only live service; this package never connects to a broker or routes real orders.
"""

from __future__ import annotations

from .engine import PaperSessionEngine
from .errors import (
    PaperConflictError,
    PaperError,
    PaperNotFoundError,
    PaperValidationError,
)
from .live import LivePaperSessionEngine
from .market import PaperMarketData
from .models import PaperOrder, PaperPosition, PaperSession, PaperTrade
from .rules import canonical_buy_qty, fee_breakdown, price_limit_pct, round_to_tick
from .store import PaperStore

__all__ = [
    "LivePaperSessionEngine",
    "PaperConflictError",
    "PaperError",
    "PaperMarketData",
    "PaperNotFoundError",
    "PaperOrder",
    "PaperPosition",
    "PaperSession",
    "PaperSessionEngine",
    "PaperStore",
    "PaperTrade",
    "PaperValidationError",
    "canonical_buy_qty",
    "fee_breakdown",
    "price_limit_pct",
    "round_to_tick",
]
