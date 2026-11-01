"""Pydantic request/response models for the local research API (contract v2)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BacktestRequest(BaseModel):
    """Request a research backtest (never a real order)."""

    model_config = ConfigDict(extra="forbid")
    template: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] | None = None
    snapshot: str | None = Field(default=None, description="snapshot id/prefix; omit for synthetic")
    snapshots_root: str | None = None
    experiments_root: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    synthetic: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_strategy_source(self) -> BacktestRequest:
        if (self.template is None) == (self.strategy is None):
            raise ValueError("provide exactly one of 'template' or 'strategy'")
        return self


class JobView(BaseModel):
    id: str
    kind: str
    status: str
    progress: float = 0.0
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class HealthView(BaseModel):
    status: str = "ok"
    version: str
    engine_backend: str
    engine_available: bool
    panel_available: bool
    synthetic_only: bool = True
    cors: bool = False


class JobAcceptedView(BaseModel):
    job_id: str
    status: str = "pending"


class DataUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "synthetic"
    start: str | int = "2020-01-02"
    end: str | int = "2024-12-31"
    n_sec: int = Field(default=40, ge=1, le=5500)
    seed: int = 42
    local_dir: str | None = None
    fixture_dir: str | None = None
    column_mapping: dict[str, Any] | None = None
    incremental: bool = True
    reset: bool = False


class SnapshotBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_root: str | None = None
    snapshots_root: str | None = None
    require_qpanel: bool = True


class ScreenerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: str | None = None
    expression: str = Field(min_length=1, max_length=4000)
    universe: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=2000)


class SavedScreenerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    expression: str = Field(min_length=1, max_length=4000)


class FactorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: str | None = None
    expression: str = Field(min_length=1, max_length=4000)
    forward_days: int = Field(default=5, ge=1, le=60)
    quantiles: int = Field(default=5, ge=2, le=20)
    name: str | None = Field(default=None, max_length=120)


class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str
    param_grid: dict[str, list[Any]] = Field(min_length=1)
    snapshot: str | None = None
    start: str | None = None
    end: str | None = None
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    workers: int = Field(default=1, ge=1, le=8)


class WalkForwardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str
    params: dict[str, Any] = Field(default_factory=dict)
    snapshot: str | None = None
    folds: int = Field(default=3, ge=2, le=10)
    initial_cash: float = Field(default=1_000_000.0, gt=0)


class TemplateValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=200_000)


class AttributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=120)


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=120)


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_sec: int = Field(default=40, ge=10, le=500)
    start: str = "2022-01-04"
    end: str = "2024-12-31"
    seed: int = 42


JOB_STATUSES = ("pending", "running", "done", "failed", "cancelled")
TERMINAL_JOB_STATUSES = ("done", "failed", "cancelled")


# ---------------------------------------------------------------- paper trading (M9)
class PaperSessionCreateRequest(BaseModel):
    """Create a simulated session over one immutable snapshot (never a real account)."""

    model_config = ConfigDict(extra="forbid")
    snapshot: str | None = Field(default=None, max_length=200)
    initial_cash: float = Field(default=1_000_000.0, gt=0, le=1e12, description="CNY")
    start: int | str | None = None
    end: int | str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)


class PaperStepRequest(BaseModel):
    """Advance the simulated clock (default one trading day)."""

    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=1, ge=1, le=1000)
    to_date: int | str | None = None


class PaperOrderRequest(BaseModel):
    """Submit a simulated order; fills happen on a later ``step``."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    qty: int = Field(gt=0, le=100_000_000)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, gt=0, le=1_000_000)

    @model_validator(mode="after")
    def _limit_price_matches_type(self) -> PaperOrderRequest:
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price is only valid for limit orders")
        return self


# ---------------------------------------------------------------- research robustness (M7)
class OverfittingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=160)
    n_trials: int = Field(default=1, ge=1, le=1000)


class PBORequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_ids: list[str] = Field(min_length=1, max_length=20)
    n_splits: int = Field(default=8, ge=2, le=20)

    @model_validator(mode="after")
    def _even_splits(self) -> PBORequest:
        if self.n_splits % 2 != 0:
            raise ValueError("n_splits must be even (CSCV splits into equal halves)")
        return self


class CostSensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=160)
    multipliers: list[Annotated[float, Field(ge=0, le=100)]] = Field(
        default_factory=lambda: [0.0, 0.5, 1.0, 2.0, 3.0], min_length=1, max_length=10
    )


class MonteCarloRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=160)
    n_paths: int = Field(default=500, ge=1, le=5000)
    horizon: int = Field(default=250, ge=1, le=5000)


class CapacityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=160)
    adv_participation: float = Field(default=0.1, gt=0, le=1)
