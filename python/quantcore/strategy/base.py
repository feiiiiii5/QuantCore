"""Strategy interface tiers and shared panel-view helpers.

Three tiers are supported (M4):

A. :class:`DeclarativeStrategy` — declarative entry/exit conditions (see
   :mod:`quantcore.strategy.expr`);
B. :class:`PanelWeightStrategy` — a user-supplied ``(n_time, n_sec)`` target-weight
   matrix (or callable producing one);
C. :class:`EventStrategy` — event-driven ``on_bar`` callback producing targets.

All tiers produce the same contract: a float64 matrix of shape ``(n_time, n_sec)`` where
a row of ``NaN`` means "no rebalance" and a row of zeros means "target all cash".  The
C++ engine performs execution; strategies only generate targets from data available at
the decision date.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data.matrices import MatrixLayout
from ..data.panel import PanelData

MAX_ABS_WEIGHT_SUM = 1.0 + 1e-9


@dataclass
class UniverseFilter:
    """Universe eligibility rules shared by all strategy tiers."""

    exclude_st: bool = True
    exclude_suspended: bool = True
    min_price: float = 1.0
    min_list_days: int = 0
    boards: tuple[str, ...] | None = None
    min_amount: float = 0.0

    def eligible_mask(self, view: PanelView) -> np.ndarray:
        return universe_mask(view, self)


def _listed_mask(view: PanelView, min_list_days: int) -> np.ndarray:
    n_time, n_sec = view.n_time, view.n_sec
    dates = view.dates
    list_dates = []
    for record in view.securities.to_dict(orient="records"):
        list_dates.append(int(record.get("list_date") or 0))
    if min_list_days <= 0:
        return np.ones((n_time, n_sec), dtype=bool)
    first_index = np.searchsorted(dates, np.asarray(list_dates, dtype=np.int64), side="left")
    time_index = np.arange(n_time)[:, None]
    return (time_index - first_index[None, :]) >= min_list_days


def universe_mask(view: PanelView, universe: UniverseFilter | None = None) -> np.ndarray:
    """Return a ``(n_time, n_sec)`` boolean eligibility mask (causal: uses only rows ≤ t)."""
    rules = universe or UniverseFilter()
    close = view.field("close")
    mask = np.isfinite(close) & (close > 0)
    mask &= ~np.isnan(view.field("open"))
    mask &= ~np.isnan(view.field("high"))
    mask &= ~np.isnan(view.field("low"))
    if rules.exclude_suspended:
        mask &= view.field("suspended") < 0.5
    if rules.exclude_st:
        mask &= view.field("st") < 0.5
    if rules.min_price > 0:
        mask &= close >= rules.min_price
    if rules.min_amount > 0:
        mask &= view.field("amount") >= rules.min_amount
    if rules.boards is not None:
        board_by_sec = {
            str(sec): str(board)
            for sec, board in zip(view.securities["sec_id"], view.securities["board"], strict=False)
        }
        allowed = np.array(
            [board_by_sec.get(str(sec), "MAIN") in rules.boards for sec in view.sec_ids],
            dtype=bool,
        )
        mask &= allowed[None, :]
    if rules.min_list_days > 0:
        mask &= _listed_mask(view, rules.min_list_days)
    return mask


def validate_weights(weights: np.ndarray, n_time: int, n_sec: int) -> list[str]:
    """Return a list of contract violations for a target-weight matrix."""
    problems: list[str] = []
    array = np.asarray(weights)
    if array.shape != (n_time, n_sec):
        problems.append(f"shape {array.shape} != {(n_time, n_sec)}")
        return problems
    if array.dtype.kind not in "fiub":
        problems.append(f"dtype must be numeric, got {array.dtype}")
    values = array.astype(np.float64, copy=False)
    if np.isinf(values).any():
        problems.append("weights contain infinite values")
        return problems
    rebalance = ~np.isnan(values).all(axis=1)
    rows = values[rebalance]
    if rows.size:
        # A NaN element in a rebalance row means "keep the current position" (engine contract).
        if np.any((rows < -1e-12) & np.isfinite(rows)):
            problems.append("weights must be non-negative (long-only)")
        row_sums = np.nansum(rows, axis=1)
        if (row_sums > MAX_ABS_WEIGHT_SUM + 1e-9).any():
            problems.append("rebalance rows must sum to <= 1.0")
    return problems


def assert_valid_weights(weights: np.ndarray, n_time: int, n_sec: int) -> np.ndarray:
    from ..errors import StrategyValidationError

    problems = validate_weights(weights, n_time, n_sec)
    if problems:
        raise StrategyValidationError("; ".join(problems))
    return np.asarray(weights, dtype=np.float64)


@dataclass
class PanelView:
    """Read-only accessor over a panel, optionally truncated at a bar index."""

    panel: PanelData
    cut: int | None = None
    _cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)
    _layout: MatrixLayout | None = field(default=None, init=False, repr=False)

    @property
    def n_time(self) -> int:
        return self.panel.n_time if self.cut is None else self.cut + 1

    @property
    def n_sec(self) -> int:
        return self.panel.n_sec

    @property
    def dates(self) -> np.ndarray:
        return self.panel.dates[: self.n_time]

    @property
    def sec_ids(self) -> list[str]:
        return self.panel.sec_id_list

    @property
    def securities(self) -> pd.DataFrame:
        return self.panel.securities

    @property
    def last_date(self) -> int:
        return int(self.dates[-1])

    def field(self, name: str) -> np.ndarray:
        """Return the ``(visible_time, n_sec)`` matrix for a bar field."""
        if name not in self._cache:
            if self._layout is None:
                self._layout = MatrixLayout(self.panel.bars, self.panel.dates, self.panel.sec_ids)
            matrix = self._layout.matrix(name)
            self._cache[name] = matrix[: self.n_time]
        return self._cache[name]

    def matrix(self, name: str) -> np.ndarray:
        return self.field(name)

    def financials(self) -> pd.DataFrame:
        """PIT financial rows announced on or before the last visible date."""
        frame = self.panel.financials
        if frame.empty:
            return frame
        available = frame[frame["ann_date"] <= self.last_date]
        return available.reset_index(drop=True)

    def corporate_actions(self) -> pd.DataFrame:
        frame = self.panel.corporate_actions
        if frame.empty:
            return frame
        return frame[frame["ann_date"] <= self.last_date].reset_index(drop=True)

    def rebalance_flags(self, frequency: str | int = "monthly") -> np.ndarray:
        from ..calendar import TradingCalendar

        calendar = TradingCalendar(tuple(int(d) for d in self.dates))
        return np.asarray(calendar.rebalance_flags(frequency), dtype=bool)

    def truncate(self, cut: int) -> PanelView:
        """Return a new view whose last visible bar is index ``cut``."""
        if cut < 0 or cut >= self.n_time:
            raise ValueError(f"cut index out of range: {cut}")
        return PanelView(self.panel.truncate(int(self.dates[cut])))

    def panel_data(self) -> PanelData:
        return self.panel.select(end=self.last_date)

    def describe(self) -> dict[str, Any]:
        return {
            "n_time": self.n_time,
            "n_sec": self.n_sec,
            "last_date": self.last_date,
            "synthetic": bool(self.panel.meta.get("synthetic", False)),
        }


class Strategy(ABC):
    """Common strategy interface."""

    name: str = "strategy"
    version: str = "1"
    description: str = ""

    @abstractmethod
    def generate_weights(self, panel: PanelData) -> np.ndarray:
        """Return target weights ``(n_time, n_sec)``; NaN rows mean no rebalance."""

    def generate_targets(self, panel: PanelData) -> np.ndarray:
        weights = np.asarray(self.generate_weights(panel), dtype=np.float64)
        return assert_valid_weights(weights, panel.n_time, panel.n_sec)

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "class": f"{type(self).__module__}.{type(self).__name__}",
            "description": self.description,
        }

    def content_hash(self) -> str:
        """Content hash over the strategy class, parameters and source file bytes."""
        import inspect

        payload = json.dumps(self.metadata(), sort_keys=True, ensure_ascii=False)
        hasher = hashlib.sha256(payload.encode())
        source_file = inspect.getsourcefile(type(self))
        if source_file:
            hasher.update(str(source_file).encode())
            source = Path(source_file)
            if source.exists():
                hasher.update(source.read_bytes())
        return hasher.hexdigest()

    def specification(self) -> dict[str, Any]:
        return {"metadata": self.metadata(), "content_hash": self.content_hash()}


class PanelWeightStrategy(Strategy):
    """Tier B: targets supplied directly as a matrix or a callable."""

    def __init__(
        self,
        weights: np.ndarray | Callable[[PanelData], np.ndarray],
        name: str = "panel_weights",
        version: str = "1",
        description: str = "user supplied target-weight matrix",
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self._weights = weights

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        if callable(self._weights):
            matrix = np.asarray(self._weights(panel), dtype=np.float64)
        else:
            matrix = np.asarray(self._weights, dtype=np.float64).copy()
        assert matrix.shape == (panel.n_time, panel.n_sec), (
            f"weight matrix shape {matrix.shape} != {(panel.n_time, panel.n_sec)}"
        )
        return matrix


class DeclarativeStrategy(Strategy):
    """Tier A: entry/exit conditions evaluated by :mod:`quantcore.strategy.expr`."""

    def __init__(
        self,
        entry: str,
        exit: str | None = None,
        *,
        score: str | None = None,
        top_n: int | None = None,
        weighting: str = "equal",
        rebalance: str | int = "monthly",
        universe: UniverseFilter | None = None,
        name: str = "declarative",
        version: str = "1",
        description: str = "",
    ) -> None:
        from .expr import compile_expression

        self.entry = entry
        self.exit = exit
        self.score = score
        self.top_n = top_n
        self.weighting = weighting
        self.rebalance = rebalance
        self.universe = universe or UniverseFilter()
        self.name = name
        self.version = version
        self.description = description or f"declarative: {entry}"
        self._entry_expr = compile_expression(entry)
        self._exit_expr = compile_expression(exit) if exit else None
        self._score_expr = compile_expression(score) if score else None

    def metadata(self) -> dict[str, Any]:
        payload = super().metadata()
        payload.update(
            {
                "entry": self.entry,
                "exit": self.exit,
                "score": self.score,
                "top_n": self.top_n,
                "weighting": self.weighting,
                "rebalance": self.rebalance,
                "universe": self.universe.__dict__,
            }
        )
        return payload

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        from ..templates.base import select_targets
        from .expr import evaluate_expression

        view = PanelView(panel)
        flags = view.rebalance_flags(self.rebalance)
        eligible = self.universe.eligible_mask(view)
        entry = evaluate_expression(self.entry, view) > 0
        selected = entry & eligible
        if self._exit_expr is not None:
            selected &= ~(evaluate_expression(self._exit_expr, view) > 0)
        score = (
            evaluate_expression(self._score_expr, view)
            if self._score_expr is not None
            else np.ones((view.n_time, view.n_sec))
        )
        return select_targets(
            view,
            flags=flags,
            mask=selected,
            score=score,
            top_n=self.top_n,
            weighting=self.weighting,
        )


@dataclass
class EventState:
    """Minimal observable state passed to :meth:`EventStrategy.on_bar`."""

    day_index: int = 0
    date: int = 0
    positions: dict[str, float] = field(default_factory=dict)
    history: list[dict[str, float]] = field(default_factory=list)

    def update(self, targets: Mapping[str, float] | None) -> None:
        if targets is not None:
            self.positions = {str(key): float(value) for key, value in targets.items()}
            self.history.append(dict(self.positions))


class EventStrategy(Strategy):
    """Tier C: event-driven ``on_bar`` callback returning target weights."""

    rebalance: str | int = "daily"

    def __init__(
        self,
        name: str = "event",
        version: str = "1",
        description: str = "event-driven strategy",
        rebalance: str | int = "daily",
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.rebalance = rebalance

    @abstractmethod
    def on_bar(self, view: PanelView, state: EventState) -> Mapping[str, float] | None:
        """Return ``{sec_id: weight}`` targets for the decision at the visible bar."""

    def metadata(self) -> dict[str, Any]:
        payload = super().metadata()
        payload["rebalance"] = self.rebalance
        return payload

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        flags = view.rebalance_flags(self.rebalance)
        index_of = {str(sec): position for position, sec in enumerate(view.sec_ids)}
        weights = np.full((view.n_time, view.n_sec), np.nan, dtype=np.float64)
        state = EventState()
        for day in range(view.n_time):
            state.day_index = day
            state.date = int(view.dates[day])
            if not flags[day]:
                continue
            bar_view = view if day == view.n_time - 1 else view.truncate(day)
            targets = self.on_bar(bar_view, state)
            if targets is None:
                continue
            row = np.zeros(view.n_sec, dtype=np.float64)
            total = 0.0
            for key, weight in targets.items():
                position = index_of.get(str(key))
                if position is None:
                    continue
                value = float(weight)
                if value < 0:
                    raise ValueError(f"negative target weight for {key}: {value}")
                row[position] = value
                total += value
            if total > MAX_ABS_WEIGHT_SUM + 1e-9:
                raise ValueError(f"target weights sum to {total} > 1")
            weights[day] = row
            state.update(targets)
        return weights
