"""The seven built-in strategy templates (M4).

Templates only generate target weights from information visible at each decision date;
the C++ engine owns execution semantics.  They are deliberately simple reference
implementations — not investment strategies.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..data.panel import PanelData
from ..strategy.base import PanelView, Strategy, UniverseFilter, universe_mask
from ..strategy.expr import rolling_mean, rolling_std
from .base import (
    combine_scores,
    cs_quantile,
    cs_zscore,
    daily_return,
    pit_value_matrix,
    rolling_return,
    select_targets,
)

FULL_NAN = np.nan


class TemplateParams(BaseModel):
    """Base class for template parameter models (strict: unknown keys rejected)."""

    model_config = ConfigDict(extra="forbid")
    rebalance: str | int = "monthly"

    @field_validator("rebalance")
    @classmethod
    def _validate_rebalance(cls, value: str | int) -> str | int:
        if isinstance(value, int):
            if value < 1:
                raise ValueError("rebalance interval must be >= 1 day")
            return value
        allowed = {"daily", "weekly", "monthly", "quarterly"}
        if value not in allowed:
            raise ValueError(f"rebalance must be one of {sorted(allowed)} or an integer")
        return value


class BuyAndHoldParams(TemplateParams):
    top_n: int | None = Field(default=None, ge=1, description="cap the number of holdings")


class DualMAParams(TemplateParams):
    short: int = Field(default=5, ge=1, le=500)
    long: int = Field(default=20, ge=2, le=1000)
    top_n: int | None = Field(default=None, ge=1)

    @field_validator("long")
    @classmethod
    def _long_after_short(cls, value: int, info: Any) -> int:
        short = info.data.get("short")
        if short is not None and value <= short:
            raise ValueError("long window must be greater than short window")
        return value


class MomentumParams(TemplateParams):
    lookback: int = Field(default=120, ge=2, le=1000)
    skip: int = Field(default=20, ge=0, le=250)
    top_n: int = Field(default=20, ge=1)


class LowVolParams(TemplateParams):
    lookback: int = Field(default=60, ge=2, le=1000)
    top_n: int = Field(default=20, ge=1)


class DividendQualityParams(TemplateParams):
    top_n: int = Field(default=20, ge=1)
    min_roe: float = Field(default=0.0)


class SmallCapLiquidityParams(TemplateParams):
    top_n: int = Field(default=20, ge=1)
    amount_lookback: int = Field(default=20, ge=1, le=250)
    liquidity_quantile: float = Field(default=0.3, ge=0.0, le=1.0)


class MultiFactorParams(TemplateParams):
    top_n: int = Field(default=20, ge=1)
    momentum_window: int = Field(default=120, ge=2, le=1000)
    vol_window: int = Field(default=60, ge=2, le=1000)


def _metadata(strategy: Strategy, template_id: str, params: BaseModel) -> dict[str, Any]:
    payload = Strategy.metadata(strategy)
    payload["template"] = template_id
    payload["params"] = params.model_dump()
    return payload


class BuyAndHoldStrategy(Strategy):
    """Equal-weight the eligible universe on the first tradable day and hold."""

    template_id: ClassVar[str] = "buy_and_hold"

    def __init__(
        self,
        params: BuyAndHoldParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "buy_and_hold",
    ) -> None:
        self.params = params or BuyAndHoldParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "buy and hold: equal weight the eligible universe once"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        weights = np.full((view.n_time, view.n_sec), np.nan)
        rows = np.flatnonzero(eligible.any(axis=1))
        if rows.size == 0:
            return weights
        flags = np.zeros(view.n_time, dtype=bool)
        flags[int(rows[0])] = True
        return select_targets(view, flags, eligible, top_n=self.params.top_n)


class DualMAStrategy(Strategy):
    """Hold securities whose short moving average is above the long average."""

    template_id: ClassVar[str] = "dual_ma"

    def __init__(
        self,
        params: DualMAParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "dual_ma",
    ) -> None:
        self.params = params or DualMAParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "dual moving average trend following"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        close = view.field("close")
        fast = rolling_mean(close, self.params.short)
        slow = rolling_mean(close, self.params.long)
        trend = fast - slow
        mask = eligible & np.isfinite(trend) & (trend > 0)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=trend, top_n=self.params.top_n)


class MomentumStrategy(Strategy):
    """Cross-sectional momentum: rank by lookback return, hold the leaders."""

    template_id: ClassVar[str] = "momentum"

    def __init__(
        self,
        params: MomentumParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "momentum",
    ) -> None:
        self.params = params or MomentumParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "cross-sectional momentum"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        score = rolling_return(view.field("close"), self.params.lookback, skip=self.params.skip)
        mask = eligible & np.isfinite(score)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=score, top_n=self.params.top_n)


class LowVolStrategy(Strategy):
    """Cross-sectional low-volatility: hold the least volatile securities."""

    template_id: ClassVar[str] = "low_vol"

    def __init__(
        self,
        params: LowVolParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "low_vol",
    ) -> None:
        self.params = params or LowVolParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "cross-sectional low volatility"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        volatility = rolling_std(daily_return(view.field("close")), self.params.lookback)
        score = -volatility
        mask = eligible & np.isfinite(score)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=score, top_n=self.params.top_n)


class DividendQualityStrategy(Strategy):
    """Dividend yield plus ROE quality using point-in-time fundamentals."""

    template_id: ClassVar[str] = "dividend_quality"

    def __init__(
        self,
        params: DividendQualityParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "dividend_quality",
    ) -> None:
        self.params = params or DividendQualityParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "dividend yield + ROE quality (PIT fundamentals)"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        close = view.field("close")
        dividend = pit_value_matrix(view, "dividend_per_share", annual_only=True)
        roe = pit_value_matrix(view, "roe", annual_only=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            dividend_yield = np.where(close > 0, dividend / close, np.nan)
        score = combine_scores(cs_zscore(dividend_yield), cs_zscore(roe), min_valid=1)
        roe_ok = np.isfinite(roe) & (roe >= self.params.min_roe)
        mask = eligible & np.isfinite(dividend_yield) & roe_ok & np.isfinite(score)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=score, top_n=self.params.top_n)


class SmallCapLiquidityStrategy(Strategy):
    """Small float-cap selection with a liquidity floor."""

    template_id: ClassVar[str] = "small_cap_liquidity"

    def __init__(
        self,
        params: SmallCapLiquidityParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "small_cap_liquidity",
    ) -> None:
        self.params = params or SmallCapLiquidityParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "small float market cap + liquidity filter"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        float_mktcap = view.field("float_mktcap")
        average_amount = rolling_mean(view.field("amount"), self.params.amount_lookback)
        threshold = cs_quantile(average_amount, self.params.liquidity_quantile)
        liquid = np.isfinite(average_amount) & (average_amount >= threshold[:, None])
        with np.errstate(divide="ignore", invalid="ignore"):
            score = -np.log(np.where(float_mktcap > 0, float_mktcap, np.nan))
        mask = eligible & liquid & np.isfinite(score)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=score, top_n=self.params.top_n)


class MultiFactorStrategy(Strategy):
    """Equal-weight composite of momentum, low volatility, value and quality."""

    template_id: ClassVar[str] = "multi_factor"

    def __init__(
        self,
        params: MultiFactorParams | None = None,
        universe: UniverseFilter | None = None,
        name: str = "multi_factor",
    ) -> None:
        self.params = params or MultiFactorParams()
        self.universe = universe or UniverseFilter()
        self.name = name
        self.description = "multi-factor score: momentum + low vol + value + quality"

    def metadata(self) -> dict[str, Any]:
        return _metadata(self, self.template_id, self.params)

    def generate_weights(self, panel: PanelData) -> np.ndarray:
        view = PanelView(panel)
        eligible = universe_mask(view, self.universe)
        close = view.field("close")
        momentum = rolling_return(close, self.params.momentum_window)
        volatility = rolling_std(daily_return(close), self.params.vol_window)
        low_vol = -volatility
        eps = pit_value_matrix(view, "eps", annual_only=True)
        roe = pit_value_matrix(view, "roe", annual_only=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            value = np.where(close > 0, eps / close, np.nan)
        score = combine_scores(
            cs_zscore(momentum),
            cs_zscore(low_vol),
            cs_zscore(value),
            cs_zscore(roe),
            min_valid=2,
        )
        mask = eligible & np.isfinite(score)
        flags = view.rebalance_flags(self.params.rebalance)
        return select_targets(view, flags, mask, score=score, top_n=self.params.top_n)


__all__ = [
    "BuyAndHoldParams",
    "BuyAndHoldStrategy",
    "DividendQualityParams",
    "DividendQualityStrategy",
    "DualMAParams",
    "DualMAStrategy",
    "LowVolParams",
    "LowVolStrategy",
    "MomentumParams",
    "MomentumStrategy",
    "MultiFactorParams",
    "MultiFactorStrategy",
    "SmallCapLiquidityParams",
    "SmallCapLiquidityStrategy",
    "TemplateParams",
]
