"""A-share market clock (Asia/Shanghai) used by the live quote service.

Trading days and sessions come from quantcore.trading_calendar (the real XSHG calendar
from exchange-calendars, including Chinese public holidays and one-off closures), so the
live service no longer guesses with weekdays. The clock is a display/refresh hint for the
UI; backtests still use the calendar frozen in a snapshot.

holidays is kept for backwards compatibility: an optional set of extra YYYYMMDD closures
(tests / one-off announcements) layered on top of the exchange calendar.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .. import trading_calendar
from ..calendar import from_date_int

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

# The XSHG calendar shipped by exchange-calendars currently ends 2026-12-31. Beyond the
# bounds (or if the optional dependency is missing) the clock degrades to a weekday
# fallback so the live status endpoint keeps answering instead of raising; refresh the
# dependency rather than relying on the fallback (see docs/AUDIT-R3.md).


def now_shanghai() -> dt.datetime:
    """Current time in Asia/Shanghai (timezone-aware)."""
    return dt.datetime.now(tz=SHANGHAI_TZ)


def _local(moment: dt.datetime) -> dt.datetime:
    """Treat naive datetimes as Shanghai wall time; convert aware ones."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(SHANGHAI_TZ)


def _day_int(moment: dt.datetime) -> int:
    day = _local(moment).date()
    return day.year * 10000 + day.month * 100 + day.day


def _weekday(day: int) -> int:
    return from_date_int(day).weekday()


def _session(day: int) -> bool:
    try:
        return bool(trading_calendar.is_trading_day(day))
    except Exception:  # pragma: no cover - calendar out of bounds / dependency missing
        return _weekday(day) < 5


def _next_session(day: int) -> int:
    try:
        return int(trading_calendar.next_trading_day(day))
    except Exception:  # pragma: no cover - calendar out of bounds / dependency missing
        candidate = from_date_int(day) + dt.timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += dt.timedelta(days=1)
        return candidate.year * 10000 + candidate.month * 100 + candidate.day


def _previous_session(day: int) -> int:
    try:
        return int(trading_calendar.previous_trading_day(day))
    except Exception:  # pragma: no cover - calendar out of bounds / dependency missing
        candidate = from_date_int(day) - dt.timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= dt.timedelta(days=1)
        return candidate.year * 10000 + candidate.month * 100 + candidate.day


def _is_trading_day(day: int, holidays: set[int] | None = None) -> bool:
    if holidays and day in holidays:
        return False
    return _session(day)


def _next_session_skipping(day: int, holidays: set[int] | None = None) -> int:
    candidate = _next_session(day)
    guard = 0
    while holidays and candidate in holidays and guard < 400:
        candidate = _next_session(candidate)
        guard += 1
    return candidate


def _previous_session_skipping(day: int, holidays: set[int] | None = None) -> int:
    candidate = _previous_session(day)
    guard = 0
    while holidays and candidate in holidays and guard < 400:
        candidate = _previous_session(candidate)
        guard += 1
    return candidate


def is_trading_day(moment: dt.datetime, holidays: set[int] | None = None) -> bool:
    """True when the moment's Shanghai calendar day is a real XSHG session."""
    return _is_trading_day(_day_int(moment), holidays)


def market_phase(moment: dt.datetime | None = None, holidays: set[int] | None = None) -> str:
    """One of pre_open / open / lunch / closed / holiday (XSHG sessions)."""
    moment = _local(moment or now_shanghai())
    if not _is_trading_day(_day_int(moment), holidays):
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


def _open_at(day: int, clock: dt.time) -> dt.datetime:
    return dt.datetime.combine(from_date_int(day), clock, tzinfo=SHANGHAI_TZ)


def next_open(moment: dt.datetime | None = None, holidays: set[int] | None = None) -> dt.datetime:
    """Next session open (09:30 Asia/Shanghai), skipping holidays and the lunch break."""
    moment = _local(moment or now_shanghai())
    day = _day_int(moment)
    local = moment.timetz().replace(tzinfo=None)
    trading = _is_trading_day(day, holidays)
    if trading and local < OPEN_AM:
        return _open_at(day, OPEN_AM)
    if trading and local < LUNCH:
        return _open_at(day, OPEN_PM)  # morning session: next open is the afternoon one
    if trading and local < OPEN_PM:
        return _open_at(day, OPEN_PM)
    return _open_at(_next_session_skipping(day, holidays), OPEN_AM)


def last_trade_date(
    moment: dt.datetime | None = None, holidays: set[int] | None = None
) -> int | None:
    """Most recent completed (or current, after close) session date as YYYYMMDD."""
    moment = _local(moment or now_shanghai())
    day = _day_int(moment)
    local = moment.timetz().replace(tzinfo=None)
    if _is_trading_day(day, holidays) and local >= CLOSE:
        return day
    return _previous_session_skipping(day, holidays)


def calendar_source() -> str:
    """Where trading days come from (XSHG when exchange-calendars is available)."""
    return trading_calendar.calendar_source()


def market_clock(
    moment: dt.datetime | None = None, holidays: set[int] | None = None
) -> dict[str, Any]:
    """Serialisable clock payload for GET /api/live/status."""
    moment = _local(moment or now_shanghai())
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
    "calendar_source",
    "is_trading_day",
    "last_trade_date",
    "market_clock",
    "market_phase",
    "next_open",
    "now_shanghai",
]
