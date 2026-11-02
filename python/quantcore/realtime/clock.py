"""A-share market clock (Asia/Shanghai) used by the live quote service.

The clock is intentionally simple and honest: trading days are inferred from weekdays
(plus optional exchange-holiday overrides) and session phases follow the mainland
schedule.  It is a display/refresh hint for the UI, not an exchange calendar; real
backtests still use the calendar embedded in an immutable snapshot.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

SHANGHAI_TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")

PRE_OPEN = dt.time(9, 15)
OPEN_AM = dt.time(9, 30)
LUNCH = dt.time(11, 30)
OPEN_PM = dt.time(13, 0)
CLOSE = dt.time(15, 0)

PHASE_LABELS = {
    "pre_open": "集合竞价",
    "open": "交易中",
    "lunch": "午间休市",
    "closed": "已收盘",
    "holiday": "休市",
}


def now_shanghai() -> dt.datetime:
    """Current time in Asia/Shanghai (timezone-aware)."""
    return dt.datetime.now(tz=SHANGHAI_TZ)


def is_trading_day(moment: dt.datetime, holidays: set[int] | None = None) -> bool:
    """Weekday heuristic; holidays may carry explicit YYYYMMDD exchange holidays."""
    if moment.weekday() >= 5:  # Saturday/Sunday
        return False
    return not (holidays and int(moment.strftime("%Y%m%d")) in holidays)


def market_phase(moment: dt.datetime | None = None, holidays: set[int] | None = None) -> str:
    """One of pre_open / open / lunch / closed / holiday."""
    moment = moment or now_shanghai()
    if not is_trading_day(moment, holidays):
        return "holiday"
    clock = moment.timetz().replace(tzinfo=None)
    if clock < PRE_OPEN:
        return "closed"
    if clock < OPEN_AM:
        return "pre_open"
    if clock < LUNCH:
        return "open"
    if clock < OPEN_PM:
        return "lunch"
    if clock < CLOSE:
        return "open"
    return "closed"


def _next_weekday(moment: dt.datetime, days: int = 0) -> dt.date:
    candidate = moment.date() + dt.timedelta(days=days)
    step = 1 if days >= 0 else -1
    while candidate.weekday() >= 5:
        candidate += dt.timedelta(days=step)
    return candidate


def next_open(moment: dt.datetime | None = None, holidays: set[int] | None = None) -> dt.datetime:
    """Next session open (09:30 Asia/Shanghai), skipping weekends/holidays."""
    moment = (moment or now_shanghai()).astimezone(SHANGHAI_TZ)
    phase = market_phase(moment, holidays)
    local = moment.timetz().replace(tzinfo=None)
    day = moment.date()
    if phase == "pre_open":
        return dt.datetime.combine(day, OPEN_AM, tzinfo=SHANGHAI_TZ)
    if phase == "lunch":
        return dt.datetime.combine(day, OPEN_PM, tzinfo=SHANGHAI_TZ)
    if phase == "open":
        if local < LUNCH:
            return dt.datetime.combine(day, OPEN_PM, tzinfo=SHANGHAI_TZ)
        return dt.datetime.combine(_next_weekday(moment, 1), OPEN_AM, tzinfo=SHANGHAI_TZ)
    if phase == "closed" and is_trading_day(moment, holidays) and local < OPEN_AM:
        return dt.datetime.combine(day, OPEN_AM, tzinfo=SHANGHAI_TZ)
    candidate = _next_weekday(moment, 1)
    while holidays and int(candidate.strftime("%Y%m%d")) in holidays:
        candidate = _next_weekday(dt.datetime.combine(candidate, dt.time(0, 0)), 1)
    return dt.datetime.combine(candidate, OPEN_AM, tzinfo=SHANGHAI_TZ)


def last_trade_date(
    moment: dt.datetime | None = None, holidays: set[int] | None = None
) -> int | None:
    """Most recent completed session date as YYYYMMDD (best effort)."""
    moment = (moment or now_shanghai()).astimezone(SHANGHAI_TZ)
    phase = market_phase(moment, holidays)
    local = moment.timetz().replace(tzinfo=None)
    if phase == "closed" and is_trading_day(moment, holidays) and local >= CLOSE:
        return int(moment.strftime("%Y%m%d"))
    if phase in {"pre_open", "open", "lunch"} and is_trading_day(moment, holidays):
        return int(_next_weekday(moment, -1).strftime("%Y%m%d"))
    return int(_next_weekday(moment, -1).strftime("%Y%m%d"))


def market_clock(
    moment: dt.datetime | None = None, holidays: set[int] | None = None
) -> dict[str, Any]:
    """Serialisable clock payload for GET /api/live/status."""
    moment = (moment or now_shanghai()).astimezone(SHANGHAI_TZ)
    phase = market_phase(moment, holidays)
    return {
        "phase": phase,
        "label": PHASE_LABELS.get(phase, phase),
        "is_trading_day": is_trading_day(moment, holidays),
        "server_time": moment.isoformat(timespec="seconds"),
        "next_open": next_open(moment, holidays).isoformat(timespec="seconds"),
        "last_trade_date": last_trade_date(moment, holidays),
    }


__all__ = [
    "CLOSE",
    "LUNCH",
    "OPEN_AM",
    "OPEN_PM",
    "PHASE_LABELS",
    "PRE_OPEN",
    "SHANGHAI_TZ",
    "is_trading_day",
    "last_trade_date",
    "market_clock",
    "market_phase",
    "next_open",
    "now_shanghai",
]
