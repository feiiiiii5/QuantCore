"""Trading rules reused by the paper simulator: board lots, tick sizes and A-share fees.

Fees follow ``qcore::sim::costs`` semantics (per-component rounding in 1e-4 CNY and a
minimum commission), using :class:`quantcore.backtest.config.CostModelConfig` defaults so
paper sessions behave like backtests.  This module never places a real order.
"""

from __future__ import annotations

import math
from typing import Any

from ..backtest.config import CostModelConfig, RuleSetConfig
from .errors import PaperValidationError

FIXED_SCALE = 10_000  # 1e-4 CNY, matching the C++ engine's fixed point
DEFAULT_PARTICIPATION = 0.1  # fraction of one day's volume fillable per order per day


def _llround(value: float) -> int:
    """Round half away from zero (same as C++ ``std::llround`` for our inputs)."""
    if value >= 0:
        return math.floor(value + 0.5)
    return -math.floor(-value + 0.5)


def to_fixed(value: float) -> int:
    return _llround(float(value) * FIXED_SCALE)


def from_fixed(value: int) -> float:
    return float(value) / FIXED_SCALE


def round_to_tick(price: float, tick: float = 0.01) -> float:
    """Round a CNY price to the configured tick (nearest, half up)."""
    if tick <= 0:
        return round(float(price), 4)
    raw = _llround(float(price) * FIXED_SCALE)
    tick_fixed = max(1, _llround(float(tick) * FIXED_SCALE))
    return from_fixed(((raw + tick_fixed // 2) // tick_fixed) * tick_fixed)


def is_shanghai(code: str) -> bool:
    """Shanghai-listed A-share (main board / STAR) code prefixes."""
    text = str(code)
    return text.startswith("6")


def fee_breakdown(
    costs: CostModelConfig,
    side: int,
    amount_cny: float,
    *,
    is_shanghai_stock: bool,
) -> dict[str, float]:
    """Return CNY fees for one fill; ``side`` is 0=buy, 1=sell."""
    amount = max(0, to_fixed(amount_cny))

    def rate_fee(rate: float) -> int:
        if amount <= 0 or rate <= 0.0:
            return 0
        return _llround(amount * rate)

    commission = rate_fee(costs.commission_rate)
    min_commission = _llround(costs.min_commission * FIXED_SCALE)
    if commission < min_commission:
        commission = min_commission
    stamp_duty = rate_fee(costs.stamp_duty_rate) if side == 1 else 0
    transfer_fee = 0
    if not costs.transfer_fee_shanghai_only or is_shanghai_stock:
        transfer_fee = rate_fee(costs.transfer_fee_rate)
    other_fee = rate_fee(costs.exchange_fee_rate) + rate_fee(costs.reg_fee_rate)
    return {
        "commission": from_fixed(commission),
        "stamp_duty": from_fixed(stamp_duty),
        "transfer_fee": from_fixed(transfer_fee),
        "other_fee": from_fixed(other_fee),
        "fee_total": from_fixed(commission + stamp_duty + transfer_fee + other_fee),
    }


def canonical_buy_qty(board: str, qty: int, rules: RuleSetConfig, sec_type: str = "STOCK") -> int:
    """Validate/return a buy quantity that satisfies the asset/board lot rules."""
    if qty <= 0:
        raise PaperValidationError("qty must be positive")
    asset = str(sec_type or "STOCK").upper()
    if asset == "ETF":
        if qty % rules.etf_lot != 0:
            raise PaperValidationError(f"ETF qty must be a multiple of {rules.etf_lot}")
        return qty
    if asset in {"CONVERTIBLE", "CB", "BOND"}:
        if qty % rules.cb_lot != 0:
            raise PaperValidationError(f"convertible-bond qty must be a multiple of {rules.cb_lot}")
        return qty
    board_code = str(board or "MAIN").upper()
    if board_code == "STAR":
        if qty < rules.star_lot:
            raise PaperValidationError(f"STAR board requires at least {rules.star_lot} shares")
        return qty
    if board_code == "BSE":
        if qty < rules.bse_lot:
            raise PaperValidationError(f"BSE board requires at least {rules.bse_lot} shares")
        return qty
    if qty % rules.main_lot != 0:
        raise PaperValidationError(f"qty must be a multiple of {rules.main_lot} shares")
    return qty


def participation_cap(volume: float, participation: float) -> int:
    """Max shares fillable in one day: floor(daily volume shares * participation)."""
    if participation <= 0 or not math.isfinite(float(volume)) or volume <= 0:
        return 0
    return max(0, math.floor(float(volume) * float(participation)))


def participation_rate(value: Any = None) -> float:
    """Validate session execution.participation (default 10% of daily volume)."""
    if value is None:
        return DEFAULT_PARTICIPATION
    try:
        rate = float(value)
    except (TypeError, ValueError) as exc:
        raise PaperValidationError("execution.participation must be a number") from exc
    if not math.isfinite(rate) or not 0.0 < rate <= 1.0:
        raise PaperValidationError("execution.participation must be within (0, 1]")
    return rate


def round_buy_qty(board: str, qty: int, rules: RuleSetConfig, sec_type: str = "STOCK") -> int:
    """Largest board/asset-lot-valid buy quantity <= qty (0 when below the minimum)."""
    if qty <= 0:
        return 0
    asset = str(sec_type or "STOCK").upper()
    if asset == "ETF":
        lot, minimum = rules.etf_lot, rules.etf_lot
    elif asset in {"CONVERTIBLE", "CB", "BOND"}:
        lot, minimum = rules.cb_lot, rules.cb_lot
    else:
        board_code = str(board or "MAIN").upper()
        if board_code == "STAR":
            lot, minimum = 1, rules.star_lot
        elif board_code == "BSE":
            lot, minimum = 1, rules.bse_lot
        else:
            lot, minimum = rules.main_lot, rules.main_lot
    rounded = (int(qty) // lot) * lot
    if rounded < minimum:
        return 0
    return canonical_buy_qty(board, rounded, rules, sec_type)


def price_limit_pct(board: str, is_st: bool, date: int, rules: RuleSetConfig) -> float:
    """Daily price-limit fraction for a board/ST status on a given date."""
    board_code = str(board or "MAIN").upper()
    if is_st:
        return (
            rules.st_limit_pct
            if int(date) < rules.st_limit_change_date
            else rules.st_limit_pct_after
        )
    if board_code == "GEM":
        return rules.gem_limit_pct
    if board_code == "STAR":
        return rules.star_limit_pct
    if board_code == "BSE":
        return rules.bse_limit_pct
    return rules.main_limit_pct


__all__ = [
    "DEFAULT_PARTICIPATION",
    "FIXED_SCALE",
    "canonical_buy_qty",
    "fee_breakdown",
    "from_fixed",
    "is_shanghai",
    "participation_cap",
    "participation_rate",
    "price_limit_pct",
    "round_buy_qty",
    "round_to_tick",
    "to_fixed",
]
