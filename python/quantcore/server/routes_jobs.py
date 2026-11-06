"""Backtest submission, job inspection/cancel, full results and WebSocket progress."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..errors import ExperimentError, StrategyValidationError
from ..experiments import ExperimentStore
from ..templates.registry import template_param_model
from .schemas import BacktestRequest, JobAcceptedView, JobView, ReplayRequest
from .security import ServerSecurity
from .workspace import Workspace, json_safe

TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


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


def _full_result_payload(job: dict[str, Any], workspace: Workspace) -> dict[str, Any] | None:
    """Expand a finished backtest job with the full result stored in its experiment."""
    stored = job.get("result") or {}
    if not isinstance(stored, dict) or not stored.get("run_id"):
        return None
    experiments_root = stored.get("experiments_root") or workspace.settings.experiments_root
    store = ExperimentStore(Path(str(experiments_root)))
    try:
        result = store.load_result(str(stored["run_id"]))
    except Exception:  # missing/removed experiment must not break job polling
        return None
    trades = result.trades.where(result.trades.notna(), None)
    return json_safe(
        {
            "run_id": stored.get("run_id"),
            "engine_backend": result.engine_backend,
            "engine_version": result.engine_version,
            "seed": result.seed,
            "metrics": result.metrics,
            "reasons": result.reasons,
            "trade_count": len(result.trades),
            "final_equity": float(result.equity_yuan[-1]) if len(result.equity) else 0.0,
            "dates": result.dates.astype(int).tolist(),
            "equity": result.equity_yuan.tolist(),
            "cash": (result.cash.astype("float64") / 10000.0).tolist(),
            "market_value": (result.market_value.astype("float64") / 10000.0).tolist(),
            "trades": trades.to_dict(orient="records") if not result.trades.empty else [],
            "snapshot": stored.get("snapshot", {}),
            "synthetic": bool(stored.get("synthetic", False)),
            "report": stored.get("report"),
            "experiment_dir": stored.get("experiment_dir"),
            "benchmark": result.benchmark,
        }
    )


def _validate_backtest(payload: BacktestRequest) -> None:
    """Fail fast for unknown templates / invalid params (422 at submit time)."""
    if payload.template is not None:
        try:
            model = template_param_model(payload.template)
        except StrategyValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            model.model_validate(payload.params)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=json_safe(exc.errors())) from exc


def register_job_routes(app: FastAPI, ctx: Workspace, security: ServerSecurity) -> None:
    @app.post("/api/backtest", status_code=202, response_model=JobAcceptedView)
    def submit_backtest(payload: BacktestRequest) -> JobAcceptedView:
        _validate_backtest(payload)
        if payload.source_run_id:
            try:
                ExperimentStore(payload.experiments_root or ctx.settings.experiments_root).get(
                    payload.source_run_id
                )
            except ExperimentError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        job_payload = payload.model_dump()
        job_payload["kind"] = "backtest"
        job_payload["snapshots_root"] = str(payload.snapshots_root or ctx.settings.snapshots_root)
        job_payload["experiments_root"] = str(
            payload.experiments_root or ctx.settings.experiments_root
        )
        job_id = ctx.queue.submit("backtest", job_payload)
        return JobAcceptedView(job_id=job_id)

    @app.post("/api/backtest/replay")
    def replay_backtest(payload: ReplayRequest) -> Any:
        """Convenience alias for `POST /api/experiments/{run_id}/replay`."""
        store = ExperimentStore(Path(str(ctx.settings.experiments_root)))
        try:
            store.get(payload.run_id)
        except Exception as exc:  # unknown run is a 404
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        from ..experiments import replay_experiment

        try:
            outcome = replay_experiment(store, payload.run_id)
        except Exception as exc:  # replayability conflicts are 409
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return json_safe(
            {
                "run_id": outcome.run_id,
                "matched": outcome.matched,
                "equity_matched": outcome.equity_match,
                "trades_matched": outcome.trades_match,
                "metrics_matched": outcome.metrics_match,
                "diffs": list(outcome.differences),
                "differences": list(outcome.differences),
                "metadata": outcome.metadata,
            }
        )

    @app.get("/api/jobs", response_model=list[JobView])
    def list_jobs(
        status: str | None = Query(
            default=None, pattern="^(pending|running|done|failed|cancelled)$"
        ),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[JobView]:
        return [_job_view(job) for job in ctx.queue.list(status=status, limit=limit)]

    @app.get("/api/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str) -> JobView:
        job = ctx.queue.status(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_view(job)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> Any:
        job = ctx.queue.status(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if str(job["status"]) in TERMINAL_STATUSES:
            return {
                "job_id": job_id,
                "cancelled": str(job["status"]) == "cancelled",
                "status": job["status"],
            }
        updated = ctx.queue.cancel(job_id)
        current = updated or ctx.queue.status(job_id) or job
        cancelled = bool(current.get("cancel_requested")) or current["status"] == "cancelled"
        return {"job_id": job_id, "cancelled": cancelled, "status": current["status"]}

    @app.get("/api/jobs/{job_id}/result")
    def get_job_result(job_id: str) -> Any:
        job = ctx.queue.status(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        status = str(job["status"])
        if status in {"pending", "running"}:
            return JSONResponse({"job_id": job_id, "status": status}, status_code=202)
        if status in {"failed", "cancelled"}:
            return JSONResponse(
                {"job_id": job_id, "status": status, "error": job.get("error")},
                status_code=409,
            )
        full = _full_result_payload(job, ctx)
        return {"job_id": job_id, "status": "done", "result": full or job.get("result")}

    @app.websocket("/ws/jobs/{job_id}")
    async def job_socket(websocket: WebSocket, job_id: str) -> None:
        token = websocket.query_params.get("token", "")
        host = websocket.headers.get("host", "")
        origin = websocket.headers.get("origin")
        if not security.allowed_host(host) or not security.authorized(f"Bearer {token}"):
            await websocket.close(code=1008, reason="unauthorized")
            return
        if origin is not None and not security.allowed_origin(origin):
            await websocket.close(code=1008, reason="origin not allowed")
            return
        await websocket.accept()
        try:
            last_serialized: str | None = None
            while True:
                job = await asyncio.to_thread(ctx.queue.status, job_id)
                if job is None:
                    await websocket.send_json({"type": "error", "error": "job not found"})
                    await websocket.close(code=1008)
                    return
                view = json_safe(_job_view(job).model_dump())
                serialized = json.dumps(view, sort_keys=True, default=str)
                if serialized != last_serialized:
                    last_serialized = serialized
                    await websocket.send_json({"type": "job", "job": view})
                status = str(job["status"])
                if status in TERMINAL_STATUSES:
                    event = "error" if status == "failed" else "done"
                    message: dict[str, Any] = {
                        "type": event,
                        "job": view,
                        "status": status,
                    }
                    if event == "error":
                        message["error"] = job.get("error")
                    await websocket.send_json(message)
                    await websocket.close()
                    return
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return
