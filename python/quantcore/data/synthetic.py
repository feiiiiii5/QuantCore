"""Deterministic SYNTHETIC A-share market panel.

The generator produces a full cross-section of securities with daily bars, PIT
financials and corporate actions **for development and tests only**.  Every price,
limit, ST flag and accounting number is fabricated; datasets are labelled
``SYNTHETIC`` in the ``source`` columns, the panel metadata and the snapshot
manifest.  Never present these as real market results.

Supported scenarios (so tests can exercise engine edge cases):

- limit-up / limit-down days (including one-line ``一字板`` days with no liquidity)
- long and short suspensions
- ex-rights / ex-dividend days with adjusted limit references
- ST status switches (5% price limit)
- IPO (late listing) and delisting (early end of series)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, date_str, to_date_int
from .panel import BOARD_CODES, CORPORATE_ACTION_COLUMNS, PanelData, normalize_securities
from .synthetic_path import _board_price_path, _SecurityPlan
from .synthetic_rules import (
    INDUSTRIES,
    SYNTHETIC_DISCLAIMER,
    SYNTHETIC_SOURCE,
)


@dataclass(frozen=True)
class SyntheticConfig:
    """Configuration for :func:`generate_synthetic_panel`."""

    n_sec: int = 200
    start: str | int = "2020-01-02"
    end: str | int = "2024-12-31"
    seed: int = 42
    board_mix: tuple[float, float, float, float] = (0.60, 0.20, 0.12, 0.08)
    st_fraction: float = 0.05
    n_delist: int | None = None
    n_ex_rights: int | None = None
    n_suspensions: int | None = None
    n_one_line: int | None = None
    n_limit_touch: int | None = None
    n_ipo: int | None = None
    include_financials: bool = True
    include_corporate_actions: bool = True
    n_etf: int = 0
    n_cb: int = 0

    def __post_init__(self) -> None:
        if self.n_sec < 1:
            raise ValueError("n_sec must be >= 1")
        if to_date_int(self.start) >= to_date_int(self.end):
            raise ValueError("start must be before end")
        if abs(sum(self.board_mix) - 1.0) > 1e-9:
            raise ValueError("board_mix must sum to 1")
        if not 0.0 <= self.st_fraction < 1.0:
            raise ValueError("st_fraction must be in [0, 1)")
        if self.n_etf < 0 or self.n_cb < 0:
            raise ValueError("n_etf/n_cb must be non-negative")

    def scaled(self, fraction: float, minimum: int, maximum: int | None = None) -> int:
        """Scenario count scaled by ``fraction`` of ``n_sec`` (clamped)."""
        value = max(minimum, round(self.n_sec * fraction))
        if maximum is not None:
            value = min(value, maximum)
        return min(value, self.n_sec)


def _assign_scenarios(
    plans: list[_SecurityPlan], rng: np.random.Generator, n_time: int, cfg: SyntheticConfig
) -> None:
    """Attach ST/suspension/limit/ex-rights scenarios to disjoint security groups."""
    order = rng.permutation(len(plans))
    cursor = 0

    def take(count: int) -> list[_SecurityPlan]:
        nonlocal cursor
        chosen = [plans[int(i)] for i in order[cursor : cursor + count]]
        cursor = min(cursor + count, len(order))
        return chosen

    n_st = max(1, round(len(plans) * cfg.st_fraction))
    for plan in take(min(n_st, len(plans))):
        st_start = int(rng.integers(max(10, n_time // 10), max(11, int(n_time * 0.6))))
        st_len = int(rng.integers(min(60, n_time // 4 + 1), min(400, n_time - st_start - 5) + 1))
        plan.st_start = st_start
        plan.st_end = min(n_time - 1, st_start + st_len)

    n_delist = cfg.n_delist if cfg.n_delist is not None else cfg.scaled(0.01, 1, 3)
    for plan in take(n_delist):
        plan.end_idx = max(plan.list_idx + 60, n_time - int(rng.integers(3, 20)))

    n_susp = cfg.n_suspensions if cfg.n_suspensions is not None else cfg.scaled(0.015, 2, 5)
    for position, plan in enumerate(take(n_susp)):
        span = plan.end_idx - plan.list_idx
        length = int(rng.integers(60, 150)) if position < 2 else int(rng.integers(1, 4))
        length = min(length, max(1, span // 3))
        start = int(
            rng.integers(plan.list_idx + 10, max(plan.list_idx + 11, plan.end_idx - length))
        )
        plan.suspension.append((start, start + length))

    n_one_line = cfg.n_one_line if cfg.n_one_line is not None else cfg.scaled(0.02, 2, 8)
    for position, plan in enumerate(take(n_one_line)):
        start = int(rng.integers(plan.list_idx + 40, max(plan.list_idx + 41, plan.end_idx - 10)))
        length = int(rng.integers(1, 4))
        target = plan.one_line_down if position % 3 == 0 else plan.one_line_up
        target.extend(range(start, min(start + length, plan.end_idx)))

    n_touch = cfg.n_limit_touch if cfg.n_limit_touch is not None else cfg.scaled(0.08, 4, 20)
    for plan in take(n_touch):
        for _ in range(2):
            day = int(rng.integers(plan.list_idx + 30, max(plan.list_idx + 31, plan.end_idx - 1)))
            if day in plan.one_line_up or day in plan.one_line_down:
                continue
            (plan.limit_touch_up if rng.random() < 0.5 else plan.limit_touch_down).append(day)

    n_ex = cfg.n_ex_rights if cfg.n_ex_rights is not None else cfg.scaled(0.03, 2, 10)
    for plan in take(n_ex):
        excluded = {day for start, end in plan.suspension for day in range(start, end)}
        day = int(rng.integers(plan.list_idx + 20, max(plan.list_idx + 21, plan.end_idx - 2)))
        if day in excluded or day == plan.list_idx:
            continue
        cash = float(np.round(rng.uniform(0.03, 0.6), 2))
        split = float(rng.choice([1.0, 1.0, 1.5, 2.0]))
        plan.ex_actions[day] = (cash, split)

    n_ipo = cfg.n_ipo if cfg.n_ipo is not None else cfg.scaled(0.02, 1, 4)
    for plan in take(n_ipo):
        plan.list_idx = int(rng.integers(n_time // 8, max(n_time // 8 + 1, n_time // 3)))


def generate_synthetic_panel(config: SyntheticConfig | None = None) -> PanelData:
    """Generate a deterministic synthetic A-share panel."""
    cfg = config or SyntheticConfig()
    start, end = to_date_int(cfg.start), to_date_int(cfg.end)
    calendar = TradingCalendar.weekdays(start, end)
    n_time = len(calendar)
    if n_time < 120:
        raise ValueError("synthetic panel needs at least 120 trading days")
    rng = np.random.default_rng(cfg.seed)

    plans: list[_SecurityPlan] = []
    board_values = list(BOARD_CODES)
    board_p = np.asarray(cfg.board_mix, dtype=np.float64)
    industries = rng.choice(INDUSTRIES, size=cfg.n_sec)
    for i in range(cfg.n_sec):
        board = str(rng.choice(board_values, p=board_p))
        exchange = {
            "MAIN": "SH" if i % 2 == 0 else "SZ",
            "GEM": "SZ",
            "STAR": "SH",
            "BSE": "BJ",
        }[board]
        code_prefix = {"SH": "600", "SZ": "000", "BJ": "830"}[exchange]
        if board == "GEM":
            code_prefix = "300"
        elif board == "STAR":
            code_prefix = "688"
        code = f"{code_prefix}{i:03d}"[:6]
        total_shares = round(rng.uniform(1.0e8, 4.0e9) / 100.0) * 100
        float_shares = round(total_shares * rng.uniform(0.35, 1.0) / 100.0) * 100
        plans.append(
            _SecurityPlan(
                index=i,
                sec_id=f"S{i:05d}",
                code=code,
                exchange=exchange,
                board=board,
                name=f"SYN{industries[i]}{i:03d}",
                industry=str(industries[i]),
                list_idx=0,
                end_idx=n_time,
                total_shares=max(total_shares, 1_000_000),
                float_shares=max(float_shares, 1_000_000),
                drift=float(rng.normal(0.00025, 0.00045)),
                vol=float(rng.uniform(0.012, 0.032)),
                base_price=float(np.round(rng.uniform(4.0, 60.0), 2)),
            )
        )

    # V2 assets: ETFs and convertible bonds share the canonical bars schema; board stays
    # MAIN (the C++ engine currently uses board lot rules; paper trading applies sec_type
    # lots below).  They deliberately receive no stock-specific scenarios.
    asset_type: dict[str, str] = {}
    for plan in plans:
        asset_type[plan.sec_id] = "STOCK"
    next_index = len(plans)
    for offset in range(cfg.n_etf):
        plan = _SecurityPlan(
            index=next_index + offset,
            sec_id=f"E{offset:05d}",
            code=f"510{offset:03d}"[:6],
            exchange="SH",
            board="MAIN",
            name=f"SYN_ETF{offset:03d}",
            industry="ETF",
            list_idx=0,
            end_idx=n_time,
            total_shares=1_000_000_000,
            float_shares=1_000_000_000,
            drift=float(rng.normal(0.0001, 0.0002)),
            vol=float(rng.uniform(0.004, 0.015)),
            base_price=float(np.round(rng.uniform(2.0, 6.0), 2)),
        )
        plans.append(plan)
        asset_type[plan.sec_id] = "ETF"
    for offset in range(cfg.n_cb):
        plan = _SecurityPlan(
            index=next_index + cfg.n_etf + offset,
            sec_id=f"C{offset:05d}",
            code=f"110{offset:03d}"[:6],
            exchange="SH",
            board="MAIN",
            name=f"SYN_CB{offset:03d}",
            industry="可转债",
            list_idx=0,
            end_idx=n_time,
            total_shares=100_000_000,
            float_shares=100_000_000,
            drift=float(rng.normal(0.00005, 0.0003)),
            vol=float(rng.uniform(0.005, 0.02)),
            base_price=100.0,
        )
        plans.append(plan)
        asset_type[plan.sec_id] = "CONVERTIBLE"
    _assign_scenarios(plans, rng, n_time, cfg)

    security_rows: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    st_periods: dict[str, list[list[int]]] = {}
    for plan in plans:
        plan.list_idx = min(plan.list_idx, n_time - 60)
        plan.end_idx = max(plan.end_idx, plan.list_idx + 60)
        plan.end_idx = min(plan.end_idx, n_time)
        frames.append(_board_price_path(plan, np.asarray(calendar.dates, dtype=np.int64), rng))
        list_date = int(calendar.dates[plan.list_idx])
        end_date = int(calendar.dates[plan.end_idx - 1])
        delist_date = end_date if plan.end_idx < n_time else 0
        security_rows.append(
            {
                "sec_id": plan.sec_id,
                "code": plan.code,
                "exchange": plan.exchange,
                "name": plan.name,
                "board": plan.board,
                "list_date": list_date,
                "delist_date": delist_date,
                "sec_type": asset_type.get(plan.sec_id, "STOCK"),
                "industry": plan.industry,
                "source": SYNTHETIC_SOURCE,
            }
        )
        if plan.st_start >= 0:
            st_periods[plan.sec_id] = [
                [int(calendar.dates[plan.st_start]), int(calendar.dates[plan.st_end])]
            ]

    bars = pd.concat(frames, ignore_index=True)
    securities = normalize_securities(pd.DataFrame.from_records(security_rows))

    financials = (
        _build_financials(plans, calendar, rng) if cfg.include_financials else pd.DataFrame()
    )
    actions = (
        _build_corporate_actions(plans, calendar)
        if cfg.include_corporate_actions
        else pd.DataFrame()
    )

    scenarios = {
        "limit_up_days": int((bars["close"] >= bars["limit_up"]).sum()),
        "limit_down_days": int((bars["close"] <= bars["limit_down"]).sum()),
        "one_line_days": int(
            ((bars["high"] == bars["low"]) & (bars["volume"] <= 600) & ~bars["suspended"]).sum()
        ),
        "suspended_rows": int(bars["suspended"].sum()),
        "st_rows": int(bars["st"].sum()),
        "st_secs": sorted(st_periods),
        "delisted_secs": [p.sec_id for p in plans if p.end_idx < n_time],
        "ipo_secs": [p.sec_id for p in plans if p.list_idx > 0],
        "ex_rights_secs": [p.sec_id for p in plans if p.ex_actions],
        "suspended_secs": [p.sec_id for p in plans if p.suspension],
    }
    meta: dict[str, Any] = {
        "synthetic": True,
        "source": SYNTHETIC_SOURCE,
        "provider": "synthetic",
        "disclaimer": SYNTHETIC_DISCLAIMER,
        "seed": cfg.seed,
        "config": asdict(cfg),
        "st_periods": st_periods,
        "scenarios": scenarios,
        "calendar_note": "SYNTHETIC calendar: weekdays minus fabricated holidays",
        "start": date_str(start),
        "end": date_str(end),
    }
    return PanelData(
        calendar=calendar,
        securities=securities,
        bars=bars,
        financials=financials,
        corporate_actions=actions,
        meta=meta,
    )


def _build_financials(
    plans: list[_SecurityPlan], calendar: TradingCalendar, rng: np.random.Generator
) -> pd.DataFrame:
    """Build PIT quarterly financial rows (synthetic)."""
    rows: list[dict[str, Any]] = []
    first, last = calendar.dates[0], calendar.dates[-1]
    years = range(first // 10000, last // 10000 + 1)
    quarters = [year * 10000 + md for year in years for md in (331, 630, 930, 1231)]
    for plan in plans:
        list_date = int(calendar.dates[plan.list_idx])
        base_revenue = float(rng.uniform(5.0e8, 8.0e10))
        margin = float(rng.uniform(0.03, 0.32))
        growth = float(rng.uniform(0.0, 0.06))
        equity_ratio = float(rng.uniform(0.25, 0.65))
        for q_index, end_date in enumerate(quarters):
            end_dt = dt.date(end_date // 10000, (end_date // 100) % 100, end_date % 100)
            announce = to_date_int(end_dt + dt.timedelta(days=40))
            available = calendar.next(announce)
            if available is None or available > last or announce < list_date:
                continue
            if end_date < list_date:
                continue
            revenue = base_revenue * (1.0 + growth) ** q_index
            net_profit = revenue * margin
            total_assets = revenue * 3.5
            total_equity = total_assets * equity_ratio
            shares = plan.total_shares
            rows.append(
                {
                    "sec_id": plan.sec_id,
                    "end_date": end_date,
                    "ann_date": announce,
                    "f_ann_date": announce,
                    "report_type": "1",
                    "update_flag": "1",
                    "revenue": float(np.round(revenue, 2)),
                    "net_profit": float(np.round(net_profit, 2)),
                    "total_assets": float(np.round(total_assets, 2)),
                    "total_equity": float(np.round(total_equity, 2)),
                    "roe": float(np.round(net_profit / max(total_equity, 1.0) * 4.0, 6)),
                    "eps": float(np.round(net_profit / max(shares, 1), 6)),
                    "bps": float(np.round(total_equity / max(shares, 1), 6)),
                    "dividend_per_share": (
                        float(np.round(net_profit / max(shares, 1) * rng.uniform(0.2, 0.6), 4))
                        if end_date % 10000 == 1231
                        else 0.0
                    ),
                    "source": SYNTHETIC_SOURCE,
                }
            )
    return pd.DataFrame.from_records(rows)


def _build_corporate_actions(plans: list[_SecurityPlan], calendar: TradingCalendar) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for plan in plans:
        for day_local, (cash, split) in sorted(plan.ex_actions.items()):
            if day_local <= 0 or day_local >= len(calendar):
                continue
            ex_date = int(calendar.dates[day_local])
            prev_date = int(calendar.dates[day_local - 1])
            pay_date = calendar.next(ex_date) or ex_date
            rows.append(
                {
                    "sec_id": plan.sec_id,
                    "ann_date": int(
                        to_date_int(
                            dt.date(ex_date // 10000, (ex_date // 100) % 100, ex_date % 100)
                            - dt.timedelta(days=30)
                        )
                    ),
                    "record_date": prev_date,
                    "ex_date": ex_date,
                    "pay_date": int(pay_date),
                    "cash_per_share": cash,
                    "split_ratio": split,
                    "rights_ratio": 0.0,
                    "rights_price": 0.0,
                    "source": SYNTHETIC_SOURCE,
                }
            )
    return pd.DataFrame.from_records(rows, columns=list(CORPORATE_ACTION_COLUMNS))


def generate_quick_panel(
    n_sec: int = 30, start: str = "2023-01-03", end: str = "2023-12-29", seed: int = 7
) -> PanelData:
    """Small synthetic panel used by tests and smoke commands."""
    return generate_synthetic_panel(SyntheticConfig(n_sec=n_sec, start=start, end=end, seed=seed))
