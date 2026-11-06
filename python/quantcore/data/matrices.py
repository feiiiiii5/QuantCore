"""Long-table matrix assembly with reusable coordinates for read-only views."""

from __future__ import annotations

import numpy as np
import pandas as pd


class MatrixLayout:
    """Map bar rows to panel cells; only reuse while the source is read-only."""

    def __init__(self, bars: pd.DataFrame, dates: np.ndarray, sec_ids: np.ndarray) -> None:
        self.bars = bars
        self.dates = dates
        self.sec_ids = sec_ids
        self.shape = (len(dates), len(sec_ids))
        date_axis, sec_axis = pd.Index(dates), pd.Index(sec_ids)
        self._rows: np.ndarray | None = None
        self._cells: np.ndarray | None = None
        self._duplicates = False
        # Reindexing permits repeated output labels. Keep pandas' exact behavior
        # for those unusual axes rather than requiring a unique-index mapping.
        if not date_axis.is_unique or not sec_axis.is_unique:
            return
        times = date_axis.get_indexer(bars["date"])
        securities = sec_axis.get_indexer(bars["sec_id"])
        self._rows = np.flatnonzero((times >= 0) & (securities >= 0))
        self._cells = times[self._rows] * self.shape[1] + securities[self._rows]
        counts = np.bincount(self._cells, minlength=self.shape[0] * self.shape[1])
        self._duplicates = bool((counts > 1).any())

    def matrix(self, field_name: str, fill: float = np.nan) -> np.ndarray:
        if field_name not in self.bars.columns:
            raise KeyError(f"unknown field: {field_name}")
        if self._cells is None or field_name in {"date", "sec_id"}:
            frame = self.bars[["date", "sec_id", field_name]]
            pivoted = frame.pivot_table(
                index="date", columns="sec_id", values=field_name, aggfunc="last"
            ).reindex(index=self.dates, columns=self.sec_ids)
            pivot_values = pivoted.to_numpy(dtype=np.float64)
            return (
                pivot_values
                if np.isnan(fill)
                else np.where(np.isnan(pivot_values), fill, pivot_values)
            )

        assert self._rows is not None
        selected = self.bars[field_name].iloc[self._rows]
        present = selected.notna().to_numpy()
        cells = self._cells[present]
        # Select before conversion: values outside the output axes were ignored
        # by pivot/reindex too, including nonnumeric values in those rows.
        values = selected.iloc[np.flatnonzero(present)].to_numpy(dtype=np.float64)
        if not np.isnan(fill):
            values = np.where(np.isnan(values), fill, values)
        result = np.full(self.shape, fill, dtype=np.float64)
        if self._duplicates:
            # groupby.last skips nulls per field and uses the last source row.
            # Explicit row reduction avoids relying on repeated-index assignment.
            last = np.full(result.size, -1, dtype=np.intp)
            np.maximum.at(last, cells, np.arange(len(cells), dtype=np.intp))
            occupied = np.flatnonzero(last >= 0)
            result.ravel()[occupied] = values[last[occupied]]
        else:
            result.ravel()[cells] = values
        return result
