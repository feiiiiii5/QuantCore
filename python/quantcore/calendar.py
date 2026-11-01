"""Trading calendar helpers for the Python control plane.

All calendars generated here are **SYNTHETIC**: weekday trading days minus a fixed
set of fabricated holidays.  Synthetic calendars are only for development, tests and
demo runs; real research must load an official exchange calendar via a provider.

Dates are integers in ``YYYYMMDD`` form, matching ``qc::Date`` on the C++ side.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


def to_date_int(value: str | int | dt.date) -> int:
    """Normalise ``date``-like input to an ``YYYYMMDD`` integer."""
    if isinstance(value, int):
        _validate_date_int(value)
        return value
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        return value.year * 10000 + value.month * 100 + value.day
    text = value.strip().replace("-", "").replace("/", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value!r}")
    result = int(text)
    _validate_date_int(result)
    return result


def _validate_date_int(value: int) -> None:
    if value < 19000101 or value > 29991231:
        raise ValueError(f"date out of range: {value}")
    try:
        dt.date(value // 10000, (value // 100) % 100, value % 100)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"invalid calendar date: {value}") from exc


def from_date_int(value: int) -> dt.date:
    """Convert an ``YYYYMMDD`` integer to :class:`datetime.date`."""
    return dt.date(value // 10000, (value // 100) % 100, value % 100)


def date_str(value: int) -> str:
    """Format an ``YYYYMMDD`` integer as ``YYYY-MM-DD``."""
    return f"{value // 10000:04d}-{(value // 100) % 100:02d}-{value % 100:02d}"


# Fabricated holiday set (SYNTHETIC): month-day pairs applied to every year.
SYNTHETIC_HOLIDAY_MONTH_DAYS: tuple[tuple[int, int], ...] = (
    (1, 1),
    (2, 10),
    (2, 11),
    (2, 12),
    (2, 13),
    (2, 14),
    (2, 15),
    (2, 16),
    (4, 4),
    (4, 5),
    (4, 6),
    (5, 1),
    (5, 2),
    (5, 3),
    (5, 4),
    (5, 5),
    (6, 10),
    (9, 15),
    (9, 16),
    (9, 17),
    (10, 1),
    (10, 2),
    (10, 3),
    (10, 4),
    (10, 5),
    (10, 6),
    (10, 7),
)

SYNTHETIC_NOTE = "SYNTHETIC calendar (weekdays minus fabricated holidays); not an exchange calendar"


def synthetic_holidays(start_year: int, end_year: int) -> list[int]:
    """Return the fabricated SYNTHETIC holiday dates in ``[start_year, end_year]``."""
    holidays: list[int] = []
    for year in range(start_year, end_year + 1):
        for month, day in SYNTHETIC_HOLIDAY_MONTH_DAYS:
            try:
                dt.date(year, month, day)
            except ValueError:  # pragma: no cover - 2/30 style impossible pairs
                continue
            holidays.append(year * 10000 + month * 100 + day)
    return sorted(holidays)


@dataclass(frozen=True)
class TradingCalendar:
    """Ordered list of trading dates with fast lookup helpers."""

    dates: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.dates != tuple(sorted(set(self.dates))):
            raise ValueError("calendar dates must be strictly increasing and unique")

    @classmethod
    def from_dates(cls, dates: Iterable[int | str | dt.date]) -> TradingCalendar:
        return cls(tuple(sorted({to_date_int(d) for d in dates})))

    @classmethod
    def weekdays(
        cls,
        start: str | int | dt.date,
        end: str | int | dt.date,
        holidays: Iterable[int] | None = None,
    ) -> TradingCalendar:
        """Weekdays in ``[start, end]`` minus holidays (SYNTHETIC by default)."""
        start_d = from_date_int(to_date_int(start))
        end_d = from_date_int(to_date_int(end))
        if end_d < start_d:
            raise ValueError("end date precedes start date")
        if holidays is None:
            holiday_set = set(synthetic_holidays(start_d.year, end_d.year))
        else:
            holiday_set = {to_date_int(h) for h in holidays}
        out: list[int] = []
        cursor = start_d
        one_day = dt.timedelta(days=1)
        while cursor <= end_d:
            if cursor.weekday() < 5:
                value = cursor.year * 10000 + cursor.month * 100 + cursor.day
                if value not in holiday_set:
                    out.append(value)
            cursor += one_day
        return cls(tuple(out))

    @classmethod
    def load(cls, path: str | Path) -> TradingCalendar:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload["dates"]
        return cls.from_dates(payload)

    def save(self, path: str | Path) -> None:
        payload = {"kind": "SYNTHETIC", "note": SYNTHETIC_NOTE, "dates": list(self.dates)}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def __len__(self) -> int:
        return len(self.dates)

    def __iter__(self) -> Iterator[int]:
        return iter(self.dates)

    def __contains__(self, value: object) -> bool:
        return isinstance(value, int) and value in self._index()

    def at(self, index: int) -> int:
        return self.dates[index]

    def index_of(self, date: int, default: int = -1) -> int:
        return self._index().get(date, default)

    def is_trading_day(self, date: int) -> bool:
        return date in self._index()

    def next(self, date: int) -> int | None:
        idx = self._index().get(date)
        if idx is not None and idx + 1 < len(self.dates):
            return self.dates[idx + 1]
        for candidate in self.dates:
            if candidate > date:
                return candidate
        return None

    def prev(self, date: int) -> int | None:
        idx = self._index().get(date)
        if idx is not None and idx - 1 >= 0:
            return self.dates[idx - 1]
        for candidate in reversed(self.dates):
            if candidate < date:
                return candidate
        return None

    def between(self, start: int, end: int) -> list[int]:
        """Trading dates in ``[start, end]``."""
        return [d for d in self.dates if start <= d <= end]

    def slice(self, start: int | None = None, end: int | None = None) -> TradingCalendar:
        return TradingCalendar(tuple(self.between(start or self.dates[0], end or self.dates[-1])))

    def month_start_flags(self) -> list[bool]:
        """True on the first trading day of each calendar month."""
        flags: list[bool] = []
        previous: tuple[int, int] | None = None
        for date in self.dates:
            key = (date // 10000, (date // 100) % 100)
            flags.append(previous is None or key != previous)
            previous = key
        return flags

    def week_start_flags(self) -> list[bool]:
        """True on the first trading day of each ISO week."""

        flags: list[bool] = []
        previous: tuple[int, int] | None = None
        for date in self.dates:
            iso = from_date_int(date).isocalendar()
            key = (iso.year, iso.week)
            flags.append(previous is None or key != previous)
            previous = key
        return flags

    def rebalance_flags(self, frequency: str | int) -> list[bool]:
        """Return per-date rebalance flags for ``monthly``/``weekly``/``daily`` or every N days."""
        if isinstance(frequency, int) or (isinstance(frequency, str) and frequency.isdigit()):
            n = max(1, int(frequency))
            return [i % n == 0 for i in range(len(self.dates))]
        key = str(frequency).strip().lower()
        if key in {"daily", "1d", "every_day"}:
            return [True] * len(self.dates)
        if key in {"weekly", "w", "1w"}:
            return self.week_start_flags()
        if key in {"monthly", "m", "1m"}:
            return self.month_start_flags()
        if key in {"quarterly", "q", "1q"}:
            flags: list[bool] = []
            previous_quarter: int | None = None
            for date in self.dates:
                quarter = (date // 10000) * 4 + (date // 100 % 100 - 1) // 3
                flags.append(previous_quarter is None or quarter != previous_quarter)
                previous_quarter = quarter
            return flags
        raise ValueError(f"unsupported rebalance frequency: {frequency!r}")

    def _index(self) -> dict[int, int]:
        cached = getattr(self, "_index_cache", None)
        if cached is None:
            cached = {d: i for i, d in enumerate(self.dates)}
            object.__setattr__(self, "_index_cache", cached)
        return cached
