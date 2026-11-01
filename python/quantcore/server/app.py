"""Local FastAPI research server (M5 minimal): loopback-only, bearer-token protected.

Only research backtests are exposed.  There is no real order routing, no broker gateway
endpoint and no market-data network access from the server process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import quantcore

from ..backtest.config import BacktestConfig
from ..backtest.engine import run_backtest
from ..data.state import SQLiteState
from ..data.synthetic import SyntheticConfig, generate_synthetic_panel
from ..jobs.queue import JobQueue, JobRunner
from ..snapshot.reader import find_snapshot
from ..strategy.spec import StrategySpec
from .schemas import BacktestRequest, HealthView, JobAcceptedView, JobView
from .security import SecurityMiddleware, ServerSecurity, resolve_token

DEFAULT_STATE_PATH = "data/state.sqlite"
DEFAULT_SNAPSHOTS_ROOT = "data/snapshots"


def default_job_runner(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a research backtest payload; used by the default API worker."""
    config = BacktestConfig.model_validate(payload.get("config") or {})
    snapshot_ref = payload.get("snapshot")
    if snapshot_ref:
        root = str(payload.get("snapshots_root") or DEFAULT_SNAPSHOTS_ROOT)
        snapshot = find_snapshot(root, str(snapshot_ref))
        panel = snapshot.to_panel_data()
        target: Any = snapshot
        snapshot_meta = snapshot.describe()
    else:
        synthetic = payload.get("synthetic") or {}
        panel = generate_synthetic_panel(
            SyntheticConfig(
                n_sec=int(synthetic.get("n_sec", 40)),
                start=str(synthetic.get("start", "2023-01-03")),
                end=str(synthetic.get("end", "2024-12-29")),
                seed=int(synthetic.get("seed", 42)),
            )
        )
        target = panel
        snapshot_meta = {
            "synthetic": True,
            "source": "SYNTHETIC",
            "n_sec": panel.n_sec,
            "n_time": panel.n_time,
        }
    if payload.get("strategy") is not None:
        spec = StrategySpec.model_validate(payload["strategy"])
    else:
        spec = StrategySpec(
            name=str(payload.get("template")),
            template=str(payload["template"]),
            params=dict(payload.get("params") or {}),
        )
    strategy = spec.load()
    weights = strategy.generate_targets(panel)
    result = run_backtest(
        target,
        weights,
        config,
        strategy_metadata=strategy.metadata(),
        snapshot_metadata=snapshot_meta,
    )
    return {
        "engine_backend": result.engine_backend,
        "engine_version": result.engine_version,
        "seed": result.seed,
        "trade_count": len(result.trades),
        "metrics": result.metrics,
        "reasons": result.reasons,
        "final_equity": float(result.equity_yuan[-1]) if len(result.equity) else 0.0,
        "snapshot": snapshot_meta,
        "synthetic": bool(snapshot_meta.get("synthetic", False)),
        "disclaimer": quantcore.INVESTMENT_DISCLAIMER,
    }


def create_app(
    *,
    token: str | None = None,
    port: int = 8000,
    state_path: str | Path = DEFAULT_STATE_PATH,
    runner: JobRunner | None = None,
    start_worker: bool = True,
    security: ServerSecurity | None = None,
) -> FastAPI:
    """Build the FastAPI application (no CORS middleware, loopback security)."""
    if security is None:
        resolved_token, generated = resolve_token(token)
        security = ServerSecurity(token=resolved_token, port=port, token_generated=generated)
    state = SQLiteState(Path(state_path))
    queue = JobQueue(state, runner or default_job_runner)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if start_worker:
            queue.start()
        try:
            yield
        finally:
            queue.stop()

    app = FastAPI(
        title="QuantCore research API",
        version=quantcore.__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.security = security
    app.state.jobs = queue
    app.state.state = state
    app.add_middleware(SecurityMiddleware, security=security)

    @app.get("/health", response_model=HealthView)
    def health() -> HealthView:
        return HealthView(
            version=quantcore.__version__,
            engine_backend=quantcore.engine_backend(),
            engine_available=quantcore.engine_available(),
            panel_available=quantcore.panel_available(),
            synthetic_only=True,
            cors=False,
        )

    @app.post("/api/backtest", status_code=202, response_model=JobAcceptedView)
    def submit_backtest(payload: BacktestRequest, request: Request) -> JobAcceptedView:
        job_payload = payload.model_dump()
        if payload.snapshots_root is None:
            job_payload["snapshots_root"] = str(request.app.state.settings_snapshots_root)
        job_id = queue.submit("backtest", job_payload)
        return JobAcceptedView(job_id=job_id)

    @app.get("/api/jobs", response_model=list[JobView])
    def list_jobs(
        status: str | None = Query(default=None, pattern="^(pending|running|done|failed)$"),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[JobView]:
        return [_job_view(job) for job in queue.list(status=status, limit=limit)]

    @app.get("/api/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str) -> JobView:
        job = queue.status(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_view(job)

    @app.get("/api/jobs/{job_id}/result")
    def get_job_result(job_id: str) -> Any:
        job = queue.status(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] in {"pending", "running"}:
            return JSONResponse({"job_id": job_id, "status": job["status"]}, status_code=202)
        if job["status"] == "failed":
            return JSONResponse(
                {"job_id": job_id, "status": "failed", "error": job.get("error")},
                status_code=409,
            )
        return {"job_id": job_id, "status": "done", "result": job.get("result")}

    app.state.settings_snapshots_root = DEFAULT_SNAPSHOTS_ROOT
    return app


def _job_view(job: dict[str, Any]) -> JobView:
    return JobView(
        id=str(job["id"]),
        kind=str(job["kind"]),
        status=str(job["status"]),
        progress=float(job.get("progress") or 0.0),
        created_at=str(job.get("created_at") or ""),
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        error=job.get("error"),
        result=job.get("result"),
    )


__all__ = ["create_app", "default_job_runner"]
