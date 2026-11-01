"""Local paper trading (M9): simulated A-share execution only.

There is no real order routing, broker gateway or network access anywhere in this
package: sessions read one immutable local snapshot and mutate a JSON account state.
"""

from __future__ import annotations

from .engine import PaperSessionEngine
from .errors import (
    PaperConflictError,
    PaperError,
    PaperNotFoundError,
    PaperValidationError,
)
from .market import PaperMarketData
from .models import PaperOrder, PaperPosition, PaperSession, PaperTrade
from .rules import canonical_buy_qty, fee_breakdown, price_limit_pct, round_to_tick
from .store import PaperStore

__all__ = [
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
