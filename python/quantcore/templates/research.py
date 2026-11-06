"""Causal, long-only research candidates; not replications or return promises.

Signals use each bar's close * positive finite adjustment factor. Raw prices
remain the source of trading eligibility. Complete trailing histories are
required, and unsuccessful selection produces a cash target at rebalance dates.
Execution remains the C++ engine's next-bar responsibility.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ..data.panel import PanelData
from ..strategy.base import PanelView, Strategy, UniverseFilter, universe_mask
from .base import cs_quantile, daily_return, rolling_return, select_targets
from .builtin import TemplateParams


class TrendMomentumParams(TemplateParams):
    lookback: int = Field(default=252, ge=2, le=1000)
    skip: int = Field(default=21, ge=0, le=250)
    trend_window: int = Field(default=200, ge=2, le=1000)
    top_n: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _skip_within_lookback(self) -> TrendMomentumParams:
        if self.skip >= self.lookback:
            raise ValueError("skip must be less than lookback")
        return self


class LiquidReversalParams(TemplateParams):
    rebalance: str | int = "weekly"
    lookback: int = Field(default=5, ge=1, le=250)
    amount_lookback: int = Field(default=20, ge=1, le=250)
    liquidity_quantile: float = Field(default=0.5, ge=0.0, le=1.0)
    min_average_amount: float = Field(default=0.0, ge=0.0)
    trend_lookback: int = Field(default=60, ge=2, le=1000)
    top_n: int = Field(default=10, ge=1)


class DefensiveLowVolParams(TemplateParams):
    lookback: int = Field(default=60, ge=2, le=1000)
    trend_lookback: int = Field(default=120, ge=2, le=1000)
    top_n: int = Field(default=10, ge=1)


def _adjusted_close(view: PanelView) -> np.ndarray:
    close, factor = view.field("close"), view.field("adj_factor")
    valid = np.isfinite(close) & (close > 0) & np.isfinite(factor) & (factor > 0)
    with np.errstate(over="ignore", invalid="ignore"):
        adjusted = np.where(valid, close * factor, np.nan)
    return np.where(np.isfinite(adjusted) & (adjusted > 0), adjusted, np.nan)


def _complete(values: np.ndarray, window: int) -> np.ndarray:
    return pd.DataFrame(values).rolling(window, min_periods=window).count().to_numpy() == window


class _ResearchStrategy[P: TemplateParams](Strategy):
    template_id: ClassVar[str]

    def __init__(self, params: P, universe: UniverseFilter | None, name: str) -> None:
        self.params = params
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = f"long-only research candidate: {self.template_id}"

    def metadata(self) -> dict[str, Any]:
        return {
            **super().metadata(),
            "template": self.template_id,
            "params": self.params.model_dump(),
            "signal_price": "close * adj_factor",
            "research_candidate": True,
        }


class TrendMomentumStrategy(_ResearchStrategy[TrendMomentumParams]):
    """Positive 12-1 style momentum with a trailing moving-average trend gate."""

    template_id = "trend_momentum"

    def __init__(
        self,
        params: TrendMomentumParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "trend_momentum",
    ) -> None:
        super().__init__(params or TrendMomentumParams(), universe, name)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        price = _adjusted_close(view)
        p = self.params
        # lookback is measured from today: P[t-skip] / P[t-lookback] - 1.
        score = rolling_return(price, p.lookback - p.skip, skip=p.skip)
        average = (
            pd.DataFrame(price)
            .rolling(p.trend_window, min_periods=p.trend_window)
            .mean()
            .to_numpy()
        )
        mask = universe_mask(view, self.universe) & _complete(price, p.lookback + 1)
        mask &= np.isfinite(score) & (score > 0) & (price > average)
        return select_targets(view, view.rebalance_flags(p.rebalance), mask, score, p.top_n)


class LiquidReversalStrategy(_ResearchStrategy[LiquidReversalParams]):
    """Short-horizon laggards among liquid securities with a positive longer trend."""

    template_id = "liquid_reversal"

    def __init__(
        self,
        params: LiquidReversalParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "liquid_reversal",
    ) -> None:
        super().__init__(params or LiquidReversalParams(), universe, name)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        price = _adjusted_close(view)
        p = self.params
        score = -rolling_return(price, p.lookback)
        trend = rolling_return(price, p.trend_lookback)
        eligible = universe_mask(view, self.universe)
        amount = view.field("amount")
        amount = np.where(np.isfinite(amount) & (amount >= 0), amount, np.nan)
        average = (
            pd.DataFrame(amount)
            .rolling(p.amount_lookback, min_periods=p.amount_lookback)
            .mean()
            .to_numpy()
        )
        threshold = cs_quantile(np.where(eligible, average, np.nan), p.liquidity_quantile)
        mask = eligible & _complete(price, max(p.lookback, p.trend_lookback) + 1)
        mask &= np.isfinite(score) & np.isfinite(trend) & (trend > 0)
        mask &= (average > 0) & (average >= p.min_average_amount) & (average >= threshold[:, None])
        return select_targets(view, view.rebalance_flags(p.rebalance), mask, score, p.top_n)


class DefensiveLowVolStrategy(_ResearchStrategy[DefensiveLowVolParams]):
    """Positive-trend low volatility, allocated by inverse daily-return volatility."""

    template_id = "defensive_low_vol"

    def __init__(
        self,
        params: DefensiveLowVolParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "defensive_low_vol",
    ) -> None:
        super().__init__(params or DefensiveLowVolParams(), universe, name)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        price = _adjusted_close(view)
        p = self.params
        volatility = (
            pd.DataFrame(daily_return(price))
            .rolling(p.lookback, min_periods=p.lookback)
            .std(ddof=1)
            .to_numpy()
        )
        trend = rolling_return(price, p.trend_lookback)
        mask = universe_mask(view, self.universe) & _complete(price, p.trend_lookback + 1)
        mask &= np.isfinite(volatility) & (volatility > 0) & np.isfinite(trend) & (trend > 0)
        score = np.full_like(volatility, np.nan)
        np.divide(1.0, volatility, out=score, where=mask)
        return select_targets(
            view, view.rebalance_flags(p.rebalance), mask, score, p.top_n, weighting="score"
        )
