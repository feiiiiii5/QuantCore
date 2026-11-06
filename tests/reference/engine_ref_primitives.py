"""Reference-engine primitives shared by the differential tests."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

REASONS = {
    "none": 0,
    "suspended": 1,
    "limit_up": 2,
    "limit_down": 3,
    "lot_size": 4,
    "t_plus_one": 5,
    "insufficient_cash": 6,
    "no_quote": 7,
    "price_out_of_range": 8,
    "min_rebalance": 9,
    "canceled": 10,
    "corporate_action": 16,
}

BOARD_CODES = {"MAIN": 0, "GEM": 1, "STAR": 2, "BSE": 3}


def llround(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0 else -math.floor(-value + 0.5)


@dataclass
class RefConfig:
    initial_cash: int = 10_000_000_000  # 1,000,000 CNY in 1e-4
    commission_rate: float = 0.0003
    min_commission: int = 50_000  # 5 CNY
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    exchange_fee_rate: float = 0.00001
    reg_fee_rate: float = 0.000002
    transfer_fee_shanghai_only: bool = True
    slippage_bps: float = 0.0
    max_participation: float = 1.0
    min_rebalance_value: int = 0
    main_lot: int = 100
    star_lot: int = 200
    bse_lot: int = 100
    t_plus_one: bool = True
    annual_days: int = 244
    min_price_tick: int = 100
    use_panel_corporate_actions: bool = True
    corporate_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RefResult:
    dates: list[int]
    equity: list[int]
    cash: list[int]
    market_value: list[int]
    trades: list[dict[str, Any]]
    metrics: dict[str, float]
    reasons: dict[int, int]
    final_qty: dict[int, int] = field(default_factory=dict)


def canon_buy_qty(cfg: RefConfig, board: int, raw_qty: int) -> int:
    if raw_qty <= 0:
        return 0
    if board == 2:
        return raw_qty if raw_qty >= cfg.star_lot else 0
    if board == 3:
        return raw_qty if raw_qty >= cfg.bse_lot else 0
    lot = cfg.main_lot if cfg.main_lot > 0 else 100
    return (raw_qty // lot) * lot


def round_to_tick(raw: int, cfg: RefConfig) -> int:
    tick = cfg.min_price_tick
    if tick <= 1:
        return raw
    if raw >= 0:
        return ((raw + tick // 2) // tick) * tick
    return -(((-raw + tick // 2) // tick) * tick)


def compute_costs(cfg: RefConfig, side: int, amount: int, is_shanghai: bool) -> dict[str, int]:
    """Fees exactly as ``cpp/src/sim/costs.cpp`` (per-component rounding, min commission)."""
    if amount < 0:
        amount = 0

    def rate_fee(rate: float) -> int:
        if amount <= 0 or rate <= 0.0:
            return 0
        return llround(amount * rate)

    commission = rate_fee(cfg.commission_rate)
    if commission < cfg.min_commission:
        commission = cfg.min_commission
    stamp = rate_fee(cfg.stamp_duty_rate) if side == 1 else 0
    transfer = 0
    if not cfg.transfer_fee_shanghai_only or is_shanghai:
        transfer = rate_fee(cfg.transfer_fee_rate)
    other = rate_fee(cfg.exchange_fee_rate) + rate_fee(cfg.reg_fee_rate)
    return {
        "commission": commission,
        "stamp_duty": stamp,
        "transfer_fee": transfer,
        "other_fee": other,
        "fee_total": commission + stamp + transfer + other,
    }


def apply_slippage(ref: int, side: int, cfg: RefConfig) -> int:
    if ref <= 0 or cfg.slippage_bps <= 0:
        return ref
    factor = 1.0 + cfg.slippage_bps / 10000.0 if side == 0 else 1.0 - cfg.slippage_bps / 10000.0
    raw = ref * factor
    if raw <= 0:
        return 0
    return round_to_tick(llround(raw), cfg)


def _px(value: float) -> int:
    if not np.isfinite(value) or value <= 0:
        return 0
    return round(float(value) * 10000)
