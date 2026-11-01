"""Local CSV/Parquet provider with explicit column mapping.

The provider reads a directory of canonical datasets.  Raw files may use any column
names; a ``column_mapping`` maps canonical names to the source file's names
(``{"date": "trade_date"}``) and the provider renames them on read.  Datasets:

- ``calendar``: ``date``
- ``securities``: canonical security master columns
- ``bars``: canonical daily-bar columns
- ``financials`` / ``corporate_actions``: optional PIT datasets

File names default to ``<dataset>.csv`` or ``<dataset>.parquet`` and can be overridden.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import (
    BARS_COLUMNS,
    CORPORATE_ACTION_COLUMNS,
    FINANCIAL_COLUMNS,
    SECURITY_COLUMNS,
    normalize_bars,
    normalize_corporate_actions,
    normalize_financials,
    normalize_securities,
)
from ..errors import ProviderUnavailableError
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    subset_frame,
)

DATASET_COLUMNS: dict[str, dict[str, str]] = {
    "calendar": {"date": "int32"},
    "securities": SECURITY_COLUMNS,
    "bars": BARS_COLUMNS,
    "financials": FINANCIAL_COLUMNS,
    "corporate_actions": CORPORATE_ACTION_COLUMNS,
}
REQUIRED_DATASETS: tuple[str, ...] = ("calendar", "securities", "bars")


class LocalFileProvider(DataProvider):
    """Offline provider backed by user-supplied CSV/Parquet files."""

    name: ClassVar[str] = "local"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        financials=True, corporate_actions=True
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=100_000, window_seconds=1.0, tier="offline"
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission()

    def __init__(
        self,
        data_dir: str | Path,
        column_mapping: dict[str, dict[str, str]] | None = None,
        file_names: dict[str, str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.data_dir = Path(data_dir)
        self.column_mapping = copy.deepcopy(column_mapping or {})
        self.file_names = dict(file_names or {})
        self._cache: dict[str, pd.DataFrame] = {}
        for dataset, mapping in self.column_mapping.items():
            if dataset not in DATASET_COLUMNS:
                raise ValueError(f"unknown dataset in column_mapping: {dataset}")
            canonical = set(DATASET_COLUMNS[dataset])
            unknown = set(mapping) - canonical
            if unknown:
                raise ValueError(
                    f"column_mapping[{dataset!r}] has non-canonical keys: {sorted(unknown)}"
                )

    # -- file plumbing ----------------------------------------------------
    def _dataset_path(self, dataset: str) -> Path:
        if dataset in self.file_names:
            path = self.data_dir / self.file_names[dataset]
            if not path.exists():
                raise ProviderUnavailableError(f"local provider file not found: {path}")
            return path
        matches = sorted(
            list(self.data_dir.glob(f"{dataset}.*"))
            + list(self.data_dir.glob(f"*{dataset}*.parquet"))
        )
        matches = [path for path in matches if path.suffix.lower() in {".csv", ".parquet", ".json"}]
        if not matches:
            raise ProviderUnavailableError(
                f"local provider dataset {dataset!r} not found in {self.data_dir}; "
                f"expected {dataset}.csv or {dataset}.parquet"
            )
        return matches[0]

    def _read(self, dataset: str) -> pd.DataFrame:
        if dataset in self._cache:
            return self._cache[dataset]
        path = self._dataset_path(dataset)
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            frame = pd.read_parquet(path)
        elif suffix == ".csv":
            frame = pd.read_csv(path)
        elif suffix == ".json":
            frame = pd.read_json(path)
        else:  # pragma: no cover - guarded by _dataset_path
            raise ProviderUnavailableError(f"unsupported local file format: {path.suffix}")
        mapping = self.column_mapping.get(dataset, {})
        if mapping:
            missing_sources = [source for source in mapping.values() if source not in frame.columns]
            if missing_sources:
                raise ProviderUnavailableError(
                    f"column_mapping[{dataset!r}] refers to missing source columns: {missing_sources}"
                )
            rename = {source: canonical for canonical, source in mapping.items()}
            frame = frame.rename(columns=rename)
        self._cache[dataset] = frame
        return frame

    def _has_dataset(self, dataset: str) -> bool:
        try:
            self._dataset_path(dataset)
        except ProviderUnavailableError:
            return False
        return True

    # -- contract ---------------------------------------------------------
    def ensure_available(self) -> None:
        if not self.data_dir.exists():
            raise ProviderUnavailableError(
                f"local provider data_dir does not exist: {self.data_dir}"
            )
        missing = [name for name in REQUIRED_DATASETS if not self._has_dataset(name)]
        if missing:
            raise ProviderUnavailableError(
                f"local provider is missing datasets {missing} in {self.data_dir}"
            )

    def describe_local(self) -> dict[str, object]:
        return {
            "data_dir": str(self.data_dir),
            "datasets": {
                name: str(self._dataset_path(name))
                for name in DATASET_COLUMNS
                if self._has_dataset(name)
            },
            "column_mapping": self.column_mapping,
        }

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        self.limiter.acquire()
        frame = self._read("calendar")
        if "date" not in frame.columns:
            raise ProviderUnavailableError("local calendar dataset needs a 'date' column")
        dates = sorted({to_date_int(value) for value in frame["date"].tolist()})
        return TradingCalendar.from_dates(dates).slice(to_date_int(start), to_date_int(end))

    def fetch_security_master(self) -> pd.DataFrame:
        self.limiter.acquire()
        return normalize_securities(self._read("securities"))

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.limiter.acquire()
        frame = normalize_bars(self._read("bars"))
        return subset_frame(frame, to_date_int(start), to_date_int(end), codes=codes)

    def fetch_financials(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("financials")
        self.limiter.acquire()
        frame = normalize_financials(self._read("financials"))
        return subset_frame(
            frame, to_date_int(start), to_date_int(end), date_column="ann_date", codes=codes
        )

    def fetch_corporate_actions(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.require("corporate_actions")
        self.limiter.acquire()
        frame = normalize_corporate_actions(self._read("corporate_actions"))
        return subset_frame(
            frame, to_date_int(start), to_date_int(end), date_column="ex_date", codes=codes
        )
