"""Small shared helpers for the paper simulator (dates and UTC timestamps)."""

from __future__ import annotations

import bisect
from datetime import UTC, datetime

from ..calendar import to_date_int


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _date_text(value: int) -> str:
    text = str(int(value))
    return f"{text[:4]}-{text[4:6]}-{text[6:]}" if len(text) == 8 else text


def _clip_index(dates: list[int], value: int | str | None, default: int, *, rounding: str) -> int:
    if value is None:
        return default
    target = to_date_int(value)
    if rounding == "up":
        index = bisect.bisect_left(dates, target)
        return min(index, len(dates) - 1)
    index = bisect.bisect_right(dates, target) - 1
    return max(index, 0)


__all__ = ["_clip_index", "_date_text", "_now"]
