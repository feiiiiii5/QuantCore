"""Trading-calendar tests: real XSHG sessions from exchange_calendars (offline)."""

from __future__ import annotations

import datetime as dt

import pytest

from quantcore.calendar import from_date_int
from quantcore.trading_calendar import (
    calendar_source,
    is_trading_day,
    last_trading_day_on_or_before,
    next_trading_day,
    previous_trading_day,
    sessions_count,
    trading_days,
)


def test_calendar_is_backed_by_exchange_calendars() -> None:
    assert calendar_source() == "XSHG"


def test_spring_festival_2024_is_a_holiday() -> None:
    # 2024 Spring Festival: the exchange closed 2024-02-09 and re-opened 2024-02-19.
    assert is_trading_day(20240208) is True
    assert is_trading_day(20240209) is False
    assert is_trading_day(20240210) is False
    assert is_trading_day(20240212) is False
    assert is_trading_day(20240219) is True
    assert is_trading_day("2024-02-19") is True
    assert is_trading_day(dt.date(2024, 2, 10)) is False


def test_national_day_2024_is_a_holiday() -> None:
    assert is_trading_day(20240930) is True
    assert is_trading_day(20241001) is False
    assert is_trading_day(20241007) is False
    assert is_trading_day(20241008) is True


def test_weekend_is_not_a_trading_day() -> None:
    assert is_trading_day(20240106) is False  # Saturday
    assert is_trading_day(20240107) is False  # Sunday
    assert is_trading_day(20240108) is True  # Monday


def test_next_and_previous_session_across_holidays() -> None:
    assert next_trading_day(20240208) == 20240219
    assert next_trading_day(20240209) == 20240219
    assert next_trading_day(20240210) == 20240219
    assert previous_trading_day(20240219) == 20240208
    assert previous_trading_day(20240210) == 20240208
    assert previous_trading_day(20240212) == 20240208
    assert next_trading_day(20240930) == 20241008
    assert previous_trading_day(20241008) == 20240930


def test_next_session_works_on_a_session_day() -> None:
    assert next_trading_day(20240105) == 20240108  # Friday -> Monday
    assert previous_trading_day(20240108) == 20240105


def test_february_2024_session_list() -> None:
    sessions = trading_days(20240201, 20240229)
    assert len(sessions) == 15
    assert sessions[0] == 20240201
    assert sessions[-1] == 20240229
    assert 20240212 not in sessions
    assert sessions_count(20240201, 20240229) == len(sessions)


def test_last_trading_day_on_or_before() -> None:
    assert last_trading_day_on_or_before(20240210) == 20240208
    assert last_trading_day_on_or_before(20240219) == 20240219
    assert last_trading_day_on_or_before(20240106) == 20240105


def test_invalid_ranges_and_unsupported_values() -> None:
    assert trading_days(20240210, 20240208) == []
    with pytest.raises(TypeError):
        is_trading_day(object())
    assert isinstance(from_date_int(20240219), dt.date)
