"""Snapshot-backed market data access for the paper simulator (read-only)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..data.panel import PanelData


class PaperMarketData:
    """Lazy ``(n_time, n_sec)`` matrices from a snapshot panel for day-by-day access."""

    def __init__(self, panel: PanelData) -> None:
        self.panel = panel
        self.dates: list[int] = [int(value) for value in panel.calendar.dates]
        self.date_index: dict[int, int] = panel.date_index()
        self.sec_ids: list[str] = panel.sec_id_list
        self.sec_index: dict[str, int] = panel.sec_index()
        securities = panel.securities.reset_index(drop=True)
        self.meta: list[dict[str, Any]] = [
            {str(key): value for key, value in record.items()}
            for record in securities.to_dict(orient="records")
        ]
        self._matrices: dict[str, np.ndarray] = {}

    @property
    def n_time(self) -> int:
        return len(self.dates)

    @property
    def n_sec(self) -> int:
        return len(self.sec_ids)

    def matrix(self, field_name: str) -> np.ndarray:
        cached = self._matrices.get(field_name)
        if cached is not None:
            return cached
        if field_name not in self.panel.bars.columns:
            values = np.full((self.n_time, self.n_sec), np.nan, dtype=np.float64)
        else:
            values = self.panel.matrix(field_name)
        self._matrices[field_name] = values
        return values

    def value(self, field_name: str, day: int, sec: int) -> float:
        if day < 0 or day >= self.n_time or sec < 0 or sec >= self.n_sec:
            return float("nan")
        return float(self.matrix(field_name)[day, sec])

    def board(self, sec: int) -> str:
        return str(self.meta[sec].get("board") or "MAIN").upper()

    def code(self, sec: int) -> str:
        return str(self.meta[sec].get("code", ""))

    def name(self, sec: int) -> str:
        return str(self.meta[sec].get("name", ""))
