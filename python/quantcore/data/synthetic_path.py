"""Synthetic daily-bar price path generation (internal to quantcore.data.synthetic).

The generator deliberately fabricates limit moves, one-line boards, suspensions and
ex-rights events so the C++ engine and Python control plane can be tested against
edge cases.  All output is labelled ``SYNTHETIC``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .synthetic_rules import (
    BOARD_LIMIT,
    ST_LIMIT,
    ST_LIMIT_AFTER,
    ST_LIMIT_CHANGE_DATE,
    SYNTHETIC_SOURCE,
)


@dataclass
class _SecurityPlan:
    index: int
    sec_id: str
    code: str
    exchange: str
    board: str
    name: str
    industry: str
    list_idx: int
    end_idx: int
    total_shares: int
    float_shares: int
    drift: float
    vol: float
    base_price: float
    st_start: int = -1
    st_end: int = -1
    one_line_up: list[int] = field(default_factory=list)
    one_line_down: list[int] = field(default_factory=list)
    forced_limit_up: list[int] = field(default_factory=list)
    forced_limit_down: list[int] = field(default_factory=list)
    suspension: list[tuple[int, int]] = field(default_factory=list)
    limit_touch_up: list[int] = field(default_factory=list)
    limit_touch_down: list[int] = field(default_factory=list)
    ex_actions: dict[int, tuple[float, float]] = field(default_factory=dict)


def _round2(values: np.ndarray | float) -> np.ndarray | float:
    return np.round(values, 2)


def _board_price_path(
    plan: _SecurityPlan,
    dates: np.ndarray,
    rng: np.random.Generator,
) -> pd.DataFrame:
    start, end = plan.list_idx, plan.end_idx
    n = end - start
    local = np.arange(n, dtype=np.int64)
    absolute = start + local  # calendar indices (scenario windows are index based)
    st_flags = (absolute >= plan.st_start) & (absolute <= plan.st_end) & (plan.st_start >= 0)
    pct = np.full(n, BOARD_LIMIT[plan.board], dtype=np.float64)
    if plan.board == "MAIN":
        # TODO(verify): the ST 5% -> 10% switch applies to the main board; ChiNext/STAR
        # ST stocks keep their board limit in this synthetic rule set.
        pct = np.where(st_flags, ST_LIMIT, pct)
        if np.any(absolute >= ST_LIMIT_CHANGE_DATE):
            st_after = st_flags & (absolute >= ST_LIMIT_CHANGE_DATE)
            pct = np.where(st_after, ST_LIMIT_AFTER, pct)

    sig = plan.vol * (1.35 if plan.board in {"GEM", "STAR", "BSE"} else 1.0)
    returns = rng.normal(plan.drift, sig, size=n)
    returns = np.clip(returns, -pct * 0.999, pct * 0.999)
    returns[0] = 0.0
    close_raw = plan.base_price * np.cumprod(1.0 + returns)

    # Apply ex-rights scaling: prices after the ex-date continue from the adjusted reference.
    ex_ref: dict[int, float] = {}
    for day_local, (cash, split) in sorted(plan.ex_actions.items()):
        offset = day_local - start
        if offset <= 0 or offset >= n:
            continue
        prev_close = float(np.round(close_raw[offset - 1], 2))
        reference = float(np.round(max(0.01, (prev_close - cash) / split), 2))
        close_raw[offset:] *= reference / prev_close
        ex_ref[offset] = reference

    close = np.round(close_raw, 2)
    pre_close = np.empty(n, dtype=np.float64)
    pre_close[0] = float(np.round(plan.base_price, 2))
    limit_up = np.empty(n, dtype=np.float64)
    limit_down = np.empty(n, dtype=np.float64)

    def recompute_chain() -> None:
        pre_close[1:] = close[:-1]
        for offset, reference in ex_ref.items():
            pre_close[offset] = reference
        limit_up[:] = np.round(pre_close * (1.0 + pct), 2)
        limit_down[:] = np.round(pre_close * (1.0 - pct), 2)

    def force(day_abs: int, up: bool) -> None:
        offset = day_abs - start
        if not 0 <= offset < n:
            return
        if offset > 0:
            pre_close[offset] = close[offset - 1]
        limit_up[offset] = float(np.round(pre_close[offset] * (1.0 + pct[offset]), 2))
        limit_down[offset] = float(np.round(pre_close[offset] * (1.0 - pct[offset]), 2))
        close[offset] = limit_up[offset] if up else limit_down[offset]

    forced_up = list(plan.one_line_up) + list(plan.forced_limit_up)
    forced_down = list(plan.one_line_down) + list(plan.forced_limit_down)
    # Fixed-point iteration: clip to the limit band, re-derive the reference chain and
    # re-apply the forced limit days until the cent-rounded chain is self-consistent.
    for _ in range(8):
        recompute_chain()
        close = np.clip(close, limit_down, limit_up)
        for day in sorted(forced_up):
            force(day, True)
        for day in sorted(forced_down):
            force(day, False)
    recompute_chain()
    close = np.clip(close, limit_down, limit_up)

    suspension = np.zeros(n, dtype=bool)
    for win_start, win_end in plan.suspension:
        lo = max(0, win_start - start)
        hi = min(n, win_end - start)
        suspension[lo:hi] = True

    open_px = np.clip(
        np.round(pre_close * (1.0 + rng.normal(0.0, 0.004, size=n)), 2), limit_down, limit_up
    )
    high = np.maximum(open_px, close)
    low = np.minimum(open_px, close)
    high = np.clip(
        np.round(high * (1.0 + np.abs(rng.normal(0.0, 0.004, size=n))), 2), low, limit_up
    )
    low = np.clip(
        np.round(low * (1.0 - np.abs(rng.normal(0.0, 0.004, size=n))), 2), limit_down, high
    )

    one_line_mask = np.zeros(n, dtype=bool)
    for day, up in [(d, True) for d in plan.one_line_up] + [
        (d, False) for d in plan.one_line_down
    ]:
        offset = day - start
        if 0 <= offset < n:
            one_line_mask[offset] = True
            close[offset] = limit_up[offset] if up else limit_down[offset]
            open_px[offset] = high[offset] = low[offset] = close[offset]

    for day in plan.limit_touch_up:
        offset = day - start
        if 0 <= offset < n and not one_line_mask[offset] and close[offset] < limit_up[offset]:
            high[offset] = limit_up[offset]
    for day in plan.limit_touch_down:
        offset = day - start
        if 0 <= offset < n and not one_line_mask[offset] and close[offset] > limit_down[offset]:
            low[offset] = limit_down[offset]

    # A suspended bar carries the previous close and no trading activity.
    close[suspension] = pre_close[suspension]
    open_px[suspension] = pre_close[suspension]
    high[suspension] = pre_close[suspension]
    low[suspension] = pre_close[suspension]
    limit_up[suspension] = np.round(pre_close[suspension] * (1.0 + pct[suspension]), 2)
    limit_down[suspension] = np.round(pre_close[suspension] * (1.0 - pct[suspension]), 2)

    high = np.maximum.reduce([high, open_px, close])
    low = np.minimum.reduce([low, open_px, close])

    target_turnover = np.clip(rng.lognormal(np.log(0.012), 0.55, size=n), 0.0004, 0.35)
    volume = np.floor(target_turnover * plan.float_shares / 100.0) * 100.0
    volume[suspension] = 0.0
    tiny = rng.integers(0, 6, size=n) * 100.0
    one_line = one_line_mask & ~suspension
    volume[one_line] = tiny[one_line]
    volume = volume.astype(np.int64)
    vwap = np.round((open_px + high + low + close) / 4.0, 2)
    amount = np.round(volume * vwap, 2)
    amount[suspension] = 0.0

    adj = np.ones(n, dtype=np.float64)
    for offset, reference in ex_ref.items():
        adj[offset:] *= float(np.round(close[offset - 1] / reference, 6))
    turnover = np.where(plan.float_shares > 0, volume / float(plan.float_shares), 0.0).astype(
        np.float64
    )

    total_shares = np.full(n, plan.total_shares, dtype=np.int64)
    float_shares = np.full(n, plan.float_shares, dtype=np.int64)
    frame = pd.DataFrame(
        {
            "date": np.asarray(dates[start:end], dtype=np.int32),
            "sec_id": plan.sec_id,
            "code": plan.code,
            "open": np.round(open_px, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "pre_close": np.round(pre_close, 2),
            "volume": volume,
            "amount": amount,
            "adj_factor": np.round(adj, 8),
            "limit_up": np.round(limit_up, 2),
            "limit_down": np.round(limit_down, 2),
            "suspended": suspension,
            "st": st_flags,
            "turnover": np.round(turnover, 8),
            "total_shares": total_shares,
            "float_shares": float_shares,
            "mktcap": np.round(close * total_shares, 2),
            "float_mktcap": np.round(close * float_shares, 2),
            "source": SYNTHETIC_SOURCE,
        }
    )
    return frame
