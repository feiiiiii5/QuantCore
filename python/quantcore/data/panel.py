"""Canonical panel data model shared by providers, store, snapshots and strategies.

Conventions (mirroring ``cpp/include/qcore``):

- ``date`` is an ``int`` in ``YYYYMMDD`` form (``qc::Date``).
- ``sec_id`` is the stable internal security identifier, ``code`` the current 6-digit code.
- prices/amounts are ``float64`` CNY in memory; the C++ engine converts to fixed point.
- quantities are ``int64`` shares.

The in-memory tables are the *canonical long format*: one row per ``(date, sec_id)``.
Providers are responsible for normalising their raw schemas into these column names;
:func:`normalize_bars` performs the common renaming/coercion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
import pandas as pd

from ..calendar import TradingCalendar, date_str, to_date_int

# ---------------------------------------------------------------------------
# Canonical schema
# ---------------------------------------------------------------------------

BARS_COLUMNS: dict[str, str] = {
    "date": "int32",
    "sec_id": "object",
    "code": "object",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "pre_close": "float64",
    "volume": "int64",
    "amount": "float64",
    "adj_factor": "float64",
    "limit_up": "float64",
    "limit_down": "float64",
    "suspended": "bool",
    "st": "bool",
    "turnover": "float64",
    "total_shares": "int64",
    "float_shares": "int64",
    "mktcap": "float64",
    "float_mktcap": "float64",
    "source": "object",
}

BARS_REQUIRED: tuple[str, ...] = (
    "date",
    "sec_id",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "adj_factor",
    "limit_up",
    "limit_down",
    "suspended",
    "st",
)

SECURITY_COLUMNS: dict[str, str] = {
    "sec_id": "object",
    "code": "object",
    "exchange": "object",
    "name": "object",
    "board": "object",
    "list_date": "int32",
    "delist_date": "int32",
    "sec_type": "object",
    "industry": "object",
    "source": "object",
}

FINANCIAL_COLUMNS: dict[str, str] = {
    "sec_id": "object",
    "end_date": "int32",
    "ann_date": "int32",
    "f_ann_date": "int32",
    "report_type": "object",
    "update_flag": "object",
    "revenue": "float64",
    "net_profit": "float64",
    "total_assets": "float64",
    "total_equity": "float64",
    "roe": "float64",
    "eps": "float64",
    "bps": "float64",
    "dividend_per_share": "float64",
    "source": "object",
}

CORPORATE_ACTION_COLUMNS: dict[str, str] = {
    "sec_id": "object",
    "ann_date": "int32",
    "record_date": "int32",
    "ex_date": "int32",
    "pay_date": "int32",
    "cash_per_share": "float64",
    "split_ratio": "float64",
    "rights_ratio": "float64",
    "rights_price": "float64",
    "source": "object",
}

BOARD_CODES: dict[str, int] = {"MAIN": 0, "GEM": 1, "STAR": 2, "BSE": 3}
BOARD_NAMES: dict[int, str] = {value: key for key, value in BOARD_CODES.items()}

#: Fields exported into ``.qpanel`` for the C++ engine.
PANEL_FIELDS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "adj_factor",
    "limit_up",
    "limit_down",
    "suspended",
    "st",
    "turnover",
    "total_shares",
    "float_shares",
    "mktcap",
    "float_mktcap",
)

SCHEMA_VERSION = "1"


def _coerce_frame(frame: pd.DataFrame, schema: dict[str, str]) -> pd.DataFrame:
    """Return *frame* with canonical columns/order and best-effort dtypes."""
    out = frame.copy()
    identity = [
        column
        for column in ("date", "sec_id", "open", "high", "low", "close", "volume")
        if column in schema
    ]
    for column, dtype in schema.items():
        if column not in out.columns:
            if schema is BARS_COLUMNS and column in identity:
                raise ValueError(f"missing required column: {column}")
            if dtype == "bool":
                out[column] = False
            elif dtype in {"float64", "int64", "int32"}:
                out[column] = np.nan
            else:
                out[column] = ""
    out = out[list(schema)]
    for column, dtype in schema.items():
        if dtype == "float64":
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
        elif dtype in {"int64", "int32"}:
            numeric = pd.to_numeric(out[column], errors="coerce")
            if column == "date" or column.endswith("_date"):
                numeric = numeric.fillna(0)
                out[column] = numeric.round().astype(cast(Any, dtype))
            elif column in {"volume", "total_shares", "float_shares"}:
                out[column] = numeric.fillna(0).round().astype(cast(Any, dtype))
            else:
                out[column] = numeric.round().astype(cast(Any, dtype))
        elif dtype == "bool":
            out[column] = out[column].fillna(False).astype(bool)
        else:
            out[column] = out[column].fillna("").astype(object)
    return out


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce a raw bars frame into the canonical schema."""
    out = _coerce_frame(frame, BARS_COLUMNS)
    if "pre_close" in frame.columns and frame["pre_close"].isna().any():
        out["pre_close"] = out["pre_close"].where(
            out["pre_close"].notna(), out.groupby("sec_id")["close"].shift(1)
        )
    if out["turnover"].isna().any():
        volume = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0).astype(float)
        shares = pd.to_numeric(out["float_shares"], errors="coerce").fillna(0.0).astype(float)
        derived = np.divide(volume, shares, out=np.zeros_like(volume), where=shares > 0)
        out["turnover"] = out["turnover"].where(out["turnover"].notna(), derived)
    for column in ("mktcap", "float_mktcap"):
        if out[column].isna().any():
            scale = pd.to_numeric(
                out["total_shares" if column == "mktcap" else "float_shares"], errors="coerce"
            ).fillna(0.0)
            out[column] = out[column].where(out[column].notna(), out["close"] * scale)
    out["suspended"] = out["suspended"].fillna(False).astype(bool)
    out["st"] = out["st"].fillna(False).astype(bool)
    out = out.sort_values(["date", "sec_id"], kind="stable").reset_index(drop=True)
    return out


def normalize_securities(frame: pd.DataFrame) -> pd.DataFrame:
    out = _coerce_frame(frame, SECURITY_COLUMNS)
    out["board"] = out["board"].replace({"": "MAIN"}).astype(str).str.upper()
    out["sec_type"] = out["sec_type"].replace({"": "STOCK"}).astype(str).str.upper()
    out = out.sort_values("sec_id", kind="stable").reset_index(drop=True)
    return out


def normalize_financials(frame: pd.DataFrame) -> pd.DataFrame:
    out = _coerce_frame(frame, FINANCIAL_COLUMNS)
    out = out.sort_values(["ann_date", "sec_id", "end_date"], kind="stable").reset_index(drop=True)
    return out


def normalize_corporate_actions(frame: pd.DataFrame) -> pd.DataFrame:
    out = _coerce_frame(frame, CORPORATE_ACTION_COLUMNS)
    out = out.sort_values(["ex_date", "sec_id"], kind="stable").reset_index(drop=True)
    return out


def _digest_frame(frame: pd.DataFrame) -> str:
    hasher = hashlib.sha256()
    hasher.update("|".join(map(str, frame.columns)).encode())
    hasher.update(str(list(frame.dtypes.astype(str))).encode())
    hashes = pd.util.hash_pandas_object(frame, index=False)
    hasher.update(np.asarray(hashes, dtype=np.uint64).tobytes())
    return hasher.hexdigest()


@dataclass
class PanelData:
    """A complete in-memory panel: calendar, securities, bars and optional PIT data."""

    calendar: TradingCalendar
    securities: pd.DataFrame
    bars: pd.DataFrame
    financials: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=list(FINANCIAL_COLUMNS))
    )
    corporate_actions: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=list(CORPORATE_ACTION_COLUMNS))
    )
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.securities = normalize_securities(self.securities)
        self.bars = normalize_bars(self.bars)
        if not self.financials.empty:
            self.financials = normalize_financials(self.financials)
        if not self.corporate_actions.empty:
            self.corporate_actions = normalize_corporate_actions(self.corporate_actions)
        if (
            self.meta.get("synthetic")
            and "source" in self.bars.columns
            and not (self.bars["source"] == "SYNTHETIC").all()
        ):
            raise ValueError("synthetic panel bars must be labelled SYNTHETIC")

    # -- basic views ------------------------------------------------------
    @property
    def sec_ids(self) -> np.ndarray:
        return self.securities["sec_id"].to_numpy(dtype=object)

    @property
    def sec_id_list(self) -> list[str]:
        return [str(value) for value in self.sec_ids]

    @property
    def dates(self) -> np.ndarray:
        return np.asarray(self.calendar.dates, dtype=np.int64)

    @property
    def n_time(self) -> int:
        return len(self.calendar)

    @property
    def n_sec(self) -> int:
        return len(self.securities)

    def sec_index(self) -> dict[str, int]:
        return {str(sec): i for i, sec in enumerate(self.sec_ids)}

    def date_index(self) -> dict[int, int]:
        return dict(self.calendar._index())

    # -- matrix export ----------------------------------------------------
    def matrix(self, field_name: str, fill: float = np.nan) -> np.ndarray:
        """Return a ``(n_time, n_sec)`` matrix of *field_name* (engine layout)."""
        from .matrices import MatrixLayout

        # PanelData is mutable: coordinates must reflect its current tables.
        return MatrixLayout(self.bars, self.dates, self.sec_ids).matrix(field_name, fill)

    def security_meta(self) -> dict[str, Any]:
        """Metadata embedded into ``.qpanel`` (all values JSON-serialisable)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "synthetic": bool(self.meta.get("synthetic", False)),
            "source": self.meta.get("source", self.meta.get("provider", "unknown")),
            "disclaimer": self.meta.get("disclaimer", ""),
            "sec_ids": self.sec_id_list,
            "codes": [str(value) for value in self.securities["code"].tolist()],
            "industries": [str(value) for value in self.securities["industry"].tolist()],
        }

    # -- slicing ----------------------------------------------------------
    def truncate(self, cut: int) -> PanelData:
        """Return a copy containing only information available on trading date ``cut``.

        Bars are cut by ``date <= cut``; PIT financials and corporate actions are cut
        by their announcement date ``<= cut`` so a strategy cannot peek at disclosures
        that were not public yet.
        """
        idx = self.calendar.index_of(cut)
        if idx < 0:
            raise ValueError(f"cut date {cut} is not in the calendar")
        dates = self.calendar.dates[: idx + 1]
        frame = self.bars[self.bars["date"] <= cut].reset_index(drop=True)
        financials = self.financials
        if not financials.empty:
            financials = financials[financials["ann_date"] <= cut].reset_index(drop=True)
        actions = self.corporate_actions
        if not actions.empty:
            actions = actions[actions["ann_date"] <= cut].reset_index(drop=True)
        return PanelData(
            calendar=TradingCalendar(dates),
            securities=self.securities.copy(),
            bars=frame,
            financials=financials.copy(),
            corporate_actions=actions.copy(),
            meta=dict(self.meta),
        )

    def select(self, start: int | None = None, end: int | None = None) -> PanelData:
        """Return a copy restricted to ``[start, end]``."""
        lo = to_date_int(start) if start is not None else self.calendar.dates[0]
        hi = to_date_int(end) if end is not None else self.calendar.dates[-1]
        dates = self.calendar.between(lo, hi)
        if not dates:
            raise ValueError("empty date selection")
        frame = self.bars[(self.bars["date"] >= lo) & (self.bars["date"] <= hi)]
        return PanelData(
            calendar=TradingCalendar(tuple(dates)),
            securities=self.securities.copy(),
            bars=frame.reset_index(drop=True),
            financials=self.financials.copy(),
            corporate_actions=self.corporate_actions.copy(),
            meta=dict(self.meta),
        )

    # -- integrity --------------------------------------------------------
    def content_hash(self) -> str:
        """Stable hash of the data payload (excludes volatile metadata timestamps)."""
        hasher = hashlib.sha256()
        hasher.update(SCHEMA_VERSION.encode())
        for name, frame in (
            ("securities", self.securities),
            ("bars", self.bars),
            ("financials", self.financials),
            ("corporate_actions", self.corporate_actions),
        ):
            hasher.update(name.encode())
            hasher.update(_digest_frame(frame).encode())
        stable_meta = {
            key: value
            for key, value in self.meta.items()
            if key not in {"created_at", "generated_at", "ingested_at", "quality"}
        }
        hasher.update(json.dumps(stable_meta, sort_keys=True, ensure_ascii=False).encode())
        return hasher.hexdigest()

    def schema_problems(self) -> list[str]:
        """Return a list of canonical-schema violations (empty means valid)."""
        problems: list[str] = []
        for name, frame, schema in (
            ("bars", self.bars, BARS_COLUMNS),
            ("securities", self.securities, SECURITY_COLUMNS),
        ):
            missing = [column for column in schema if column not in frame.columns]
            if missing:
                problems.append(f"{name}: missing columns {missing}")
        if self.bars.empty:
            problems.append("bars: empty")
        if self.securities.empty:
            problems.append("securities: empty")
        if not self.bars.empty:
            if not pd.api.types.is_integer_dtype(self.bars["date"]):
                problems.append("bars: date column is not integer")
            if self.bars.duplicated(subset=["date", "sec_id"]).any():
                problems.append("bars: duplicated (date, sec_id) rows")
            unknown = set(self.bars["sec_id"].unique()) - set(self.securities["sec_id"])
            if unknown:
                problems.append(f"bars: unknown sec_ids {sorted(unknown)[:5]}")
            outside = (self.bars["date"] < self.calendar.dates[0]) | (
                self.bars["date"] > self.calendar.dates[-1]
            )
            if outside.any():
                problems.append("bars: dates outside calendar")
        if not self.securities.empty and self.securities["sec_id"].duplicated().any():
            problems.append("securities: duplicated sec_id")
        return problems

    def describe(self) -> dict[str, Any]:
        """Small JSON-friendly summary used by CLI/experiments/reports."""
        return {
            "kind": "PanelData",
            "synthetic": bool(self.meta.get("synthetic", False)),
            "n_sec": self.n_sec,
            "n_time": self.n_time,
            "start": date_str(int(self.calendar.dates[0])),
            "end": date_str(int(self.calendar.dates[-1])),
            "bars_rows": len(self.bars),
            "financials_rows": len(self.financials),
            "corporate_actions_rows": len(self.corporate_actions),
            "source": self.meta.get("source", "unknown"),
            "content_hash": self.content_hash(),
            "schema_version": SCHEMA_VERSION,
        }


def frame_to_dates(frame: pd.DataFrame, column: str = "date") -> list[int]:
    """Normalise a date column to ``YYYYMMDD`` integers."""
    return [to_date_int(value) for value in frame[column].tolist()]


def lower_bound_index(dates: Iterable[int], target: int) -> int:
    """Index of the first date ``>= target`` in a sorted iterable."""
    ordered = dates if isinstance(dates, np.ndarray) else np.asarray(list(dates))
    return int(np.searchsorted(ordered, target, side="left"))
