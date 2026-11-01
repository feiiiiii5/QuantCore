"""Backtest configuration mirroring ``qcore::BacktestConfig``.

Python-side values are human units (CNY, fractions); :meth:`BacktestConfig.cpp_kwargs`
converts to the fixed-point integers the C++ engine expects (1e-4 CNY).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..calendar import to_date_int


class ExecType(StrEnum):
    next_open = "next_open"
    next_close = "next_close"
    next_vwap = "next_vwap"
    after_hours_fixed = "after_hours_fixed"

    @property
    def code(self) -> int:
        return {
            ExecType.next_open: 0,
            ExecType.next_close: 1,
            ExecType.next_vwap: 2,
            ExecType.after_hours_fixed: 3,
        }[self]


class TraceLevel(StrEnum):
    off = "off"
    summary = "summary"
    full = "full"

    @property
    def code(self) -> int:
        return {TraceLevel.off: 0, TraceLevel.summary: 1, TraceLevel.full: 2}[self]


class RuleSetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    main_limit_pct: float = Field(default=0.10, gt=0, le=0.5)
    gem_limit_pct: float = Field(default=0.20, gt=0, le=0.5)
    star_limit_pct: float = Field(default=0.20, gt=0, le=0.5)
    bse_limit_pct: float = Field(default=0.30, gt=0, le=0.5)
    st_limit_pct: float = Field(default=0.05, gt=0, le=0.5)
    st_limit_change_date: int = 20260706
    st_limit_pct_after: float = Field(default=0.10, gt=0, le=0.5)
    main_lot: int = Field(default=100, ge=1)
    star_lot: int = Field(default=200, ge=1)
    bse_lot: int = Field(default=100, ge=1)
    t_plus_one: bool = True
    after_hours: bool = True
    after_hours_extension_date: int = 20260706
    min_price_tick: float = Field(default=0.01, gt=0)


class CostModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commission_rate: float = Field(default=0.0003, ge=0, le=0.01)
    min_commission: float = Field(
        default=5.0, ge=0, description="minimum commission per order, CNY"
    )
    stamp_duty_rate: float = Field(default=0.0005, ge=0, le=0.01)
    transfer_fee_rate: float = Field(default=0.00001, ge=0, le=0.01)
    exchange_fee_rate: float = Field(default=0.00001, ge=0, le=0.01)
    reg_fee_rate: float = Field(default=0.000002, ge=0, le=0.01)
    transfer_fee_shanghai_only: bool = True
    enable_dividend_tax: bool = False


class ExecModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ExecType = ExecType.next_open
    slippage_bps: float = Field(default=0.0, ge=0, le=500)
    max_participation: float = Field(default=1.0, gt=0, le=1.0)
    min_rebalance_value: float = Field(default=0.0, ge=0, description="skip tiny rebalances, CNY")


class RiskLimitsConfig(BaseModel):
    """Optional portfolio risk limits applied to target weights before execution."""

    model_config = ConfigDict(extra="forbid")
    max_positions: int | None = Field(default=None, ge=1, le=5000)
    max_weight: float | None = Field(default=None, gt=0, le=1.0)
    long_only: bool = True


class BacktestConfig(BaseModel):
    """Complete backtest configuration (dates optional; default to the panel range)."""

    model_config = ConfigDict(extra="forbid")
    start: int | str | None = None
    end: int | str | None = None
    initial_cash: float = Field(default=1_000_000.0, gt=0, description="CNY")
    rules: RuleSetConfig = Field(default_factory=RuleSetConfig)
    costs: CostModelConfig = Field(default_factory=CostModelConfig)
    exec: ExecModelConfig = Field(default_factory=ExecModelConfig)
    risk: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)
    trace: TraceLevel = TraceLevel.summary
    seed: int = 42
    annual_days: int = Field(default=244, ge=1)
    benchmark_code: str | None = Field(
        default=None,
        max_length=32,
        description="optional local security code for buy-and-hold benchmark",
    )
    corporate_actions: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_dates(self) -> BacktestConfig:
        if (
            self.start is not None
            and self.end is not None
            and to_date_int(self.start) > to_date_int(self.end)
        ):
            raise ValueError("start date must not be after end date")
        return self

    def resolve_dates(self, calendar: Any) -> tuple[int, int]:
        """Return concrete ``(start_date, end_date)`` clipped to the provided calendar."""
        start = to_date_int(self.start) if self.start is not None else int(calendar.dates[0])
        end = to_date_int(self.end) if self.end is not None else int(calendar.dates[-1])
        start = max(start, int(calendar.dates[0]))
        end = min(end, int(calendar.dates[-1]))
        if start > end:
            raise ValueError(f"backtest window {start}..{end} is outside the data range")
        return start, end

    def cpp_kwargs(self, calendar: Any = None) -> dict[str, Any]:
        """Flat keyword arguments for the pybind ``_qcore.BacktestConfig`` constructor."""
        start, end = (
            self.resolve_dates(calendar)
            if calendar is not None
            else (
                to_date_int(self.start) if self.start is not None else 0,
                to_date_int(self.end) if self.end is not None else 0,
            )
        )
        kwargs: dict[str, Any] = {
            "start": int(start),
            "end": int(end),
            # Money kwargs are in CNY (the binding converts to the 1e-4 fixed-point unit).
            "initial_cash": float(self.initial_cash),
            "commission_rate": self.costs.commission_rate,
            "min_commission": float(self.costs.min_commission),
            "stamp_duty_rate": self.costs.stamp_duty_rate,
            "transfer_fee_rate": self.costs.transfer_fee_rate,
            "exchange_fee_rate": self.costs.exchange_fee_rate,
            "reg_fee_rate": self.costs.reg_fee_rate,
            "transfer_fee_shanghai_only": self.costs.transfer_fee_shanghai_only,
            "enable_dividend_tax": self.costs.enable_dividend_tax,
            "main_limit_pct": self.rules.main_limit_pct,
            "gem_limit_pct": self.rules.gem_limit_pct,
            "star_limit_pct": self.rules.star_limit_pct,
            "bse_limit_pct": self.rules.bse_limit_pct,
            "st_limit_pct": self.rules.st_limit_pct,
            "st_limit_change_date": self.rules.st_limit_change_date,
            "st_limit_pct_after": self.rules.st_limit_pct_after,
            "main_lot": self.rules.main_lot,
            "star_lot": self.rules.star_lot,
            "bse_lot": self.rules.bse_lot,
            "t_plus_one": self.rules.t_plus_one,
            "after_hours": self.rules.after_hours,
            "after_hours_extension_date": self.rules.after_hours_extension_date,
            "min_price_tick": self.rules.min_price_tick,
            "exec_type": self.exec.type.code,
            "slippage_bps": self.exec.slippage_bps,
            "max_participation": self.exec.max_participation,
            "min_rebalance_value": float(self.exec.min_rebalance_value),
            "trace_level": self.trace.code,
            "seed": self.seed,
            "annual_days": self.annual_days,
        }
        return kwargs

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BacktestConfig:
        return cls.model_validate(payload)


DEFAULT_CONFIG = BacktestConfig()
