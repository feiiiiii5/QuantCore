"""API request/response schemas (M5 minimal research API)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BacktestRequest(BaseModel):
    """Request a research backtest (never a real order)."""

    model_config = ConfigDict(extra="forbid")
    template: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] | None = None
    snapshot: str | None = Field(
        default=None,
        description="snapshot id/prefix under snapshots_root; omit to use a quick synthetic panel",
    )
    snapshots_root: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    experiments_root: str | None = None

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
