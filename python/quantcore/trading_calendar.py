"""Real A-share (XSHG) trading calendar backed by exchange_calendars.

exchange-calendars is a mature open-source project (gerrymanoim/exchange_calendars)
that ships the actual Shanghai Stock Exchange sessions, including Chinese public
holidays and one-off closures.  Using it removes the weekday heuristic from the live
market clock and keeps every date helper on the same authoritative calendar.

The helpers accept ``datetime.date`` / ``datetime.datetime`` / ``YYYY-MM-DD`` strings
/ integer ``YYYYMMDD`` values and always return integer ``YYYYMMDD`` days, mirroring
the rest of the data pipeline.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any

import pandas as pd

from .calendar import from_date_int, to_date_int

try:  # pragma: no cover - the dependency is declared, the guard keeps imports friendly
    import exchange_calendars as xcals
except Exception:  # pragma: no cover
    xcals = None

XSHG = "XSHG"
_LOOKAROUND_DAYS = 40


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, int):
        return from_date_int(value)
    if isinstance(value, str):
        text = value.strip().replace("/", "-")
        if len(text) == 8 and text.isdigit():
            return from_date_int(int(text))
        return dt.date.fromisoformat(text)
    raise TypeError(f"unsupported date value: {value!r}")


def _as_day(value: Any) -> int:
    return to_date_int(_as_date(value))


def _shift_days(day: int, offset: int) -> int:
    return to_date_int(from_date_int(day) + dt.timedelta(days=offset))


@lru_cache(maxsize=1)
def _calendar() -> Any:
    if xcals is None:
        return None
    return xcals.get_calendar(XSHG)


def calendar_source() -> str:
    """Where trading days come from: exchange_calendars or the weekday fallback."""
    return XSHG if _calendar() is not None else "weekday"


def is_trading_day(value: Any) -> bool:
    """True when ``value`` is an XSHG session (holidays and weekends are False)."""
    day = _as_date(value)
    calendar = _calendar()
    if calendar is None:  # pragma: no cover - fallback when the extra is unavailable
        return day.weekday() < 5
    return bool(calendar.is_session(pd.Timestamp(day)))


@lru_cache(maxsize=256)
def _sessions_cached(start: int, end: int) -> tuple[int, ...]:
    calendar = _calendar()
    if calendar is None:  # pragma: no cover - fallback when the extra is unavailable
        first, last = from_date_int(start), from_date_int(end)
        return tuple(
            int(candidate.strftime("%Y%m%d"))
            for candidate in (
                first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)
            )
            if candidate.weekday() < 5
        )
    sessions = calendar.sessions_in_range(
        pd.Timestamp(from_date_int(start)), pd.Timestamp(from_date_int(end))
    )
    return tuple(int(session.strftime("%Y%m%d")) for session in sessions)


def trading_days(start: Any, end: Any) -> list[int]:
    """All XSHG sessions in the inclusive interval [start, end] as YYYYMMDD ints."""
    start_i, end_i = _as_day(start), _as_day(end)
    if start_i > end_i:
        return []
    return list(_sessions_cached(start_i, end_i))


def sessions_count(start: Any, end: Any) -> int:
    return len(trading_days(start, end))


def next_trading_day(value: Any) -> int:
    """First session strictly after ``value`` (works on non-session days too)."""
    day = _as_day(value)
    sessions = _sessions_cached(_shift_days(day, 1), _shift_days(day, _LOOKAROUND_DAYS * 3))
    if not sessions:  # pragma: no cover - 120 days always contains a session
        raise ValueError(f"no trading day within {_LOOKAROUND_DAYS * 3} days after {day}")
    return sessions[0]


def previous_trading_day(value: Any) -> int:
    """Last session strictly before ``value`` (works on non-session days too)."""
    day = _as_day(value)
    sessions = _sessions_cached(_shift_days(day, -_LOOKAROUND_DAYS * 3), _shift_days(day, -1))
    if not sessions:  # pragma: no cover
        raise ValueError(f"no trading day within {_LOOKAROUND_DAYS * 3} days before {day}")
    return sessions[-1]


def last_trading_day_on_or_before(value: Any) -> int:
    """Most recent session at or before ``value``."""
    day = _as_day(value)
    if is_trading_day(day):
        return day
    return previous_trading_day(day)


def reset_calendar_cache() -> None:
    """Drop cached sessions (tests / long-running processes after a dependency swap)."""
    _sessions_cached.cache_clear()
    _calendar.cache_clear()


__all__ = [
    "XSHG",
    "calendar_source",
    "is_trading_day",
    "last_trading_day_on_or_before",
    "next_trading_day",
    "previous_trading_day",
    "reset_calendar_cache",
    "sessions_count",
    "trading_days",
]
