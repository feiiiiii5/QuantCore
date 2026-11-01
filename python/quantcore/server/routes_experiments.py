"""Experiment, replay, report and export routes."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from ..backtest.result import BacktestResult
from ..errors import ExperimentError
from ..experiments import ExperimentStore, replay_experiment
from ..report import render_html_report
from .workspace import json_safe


def _store(ctx: Any) -> ExperimentStore:
    return ExperimentStore(ctx.settings.experiments_root)


def _result_payload(result: BacktestResult) -> dict[str, Any]:
    trades = result.trades.copy()
    if "date" in trades.columns:
        trades["date"] = trades["date"].astype(int)
    records = (
        trades.where(trades.notna(), None).to_dict(orient="records") if not trades.empty else []
    )
    return json_safe(
        {
            "dates": result.dates.astype(int).tolist(),
            "equity": result.equity_yuan.tolist(),
            "cash": (result.cash.astype(np.float64) / 10000.0).tolist(),
            "market_value": (result.market_value.astype(np.float64) / 10000.0).tolist(),
            "trades": records,
            "metrics": result.metrics,
            "reasons": result.reasons,
            "engine_backend": result.engine_backend,
            "engine_version": result.engine_version,
            "seed": result.seed,
            "benchmark": result.benchmark,
        }
    )


def _metadata_view(record: Any) -> dict[str, Any]:
    metadata = record.metadata
    return {
        "run_id": record.run_id,
        "kind": record.kind,
        "created_at": record.created_at,
        "status": record.status,
        "strategy_name": metadata.get("strategy_name"),
        "template": (metadata.get("strategy") or {}).get("template"),
        "snapshot_id": (metadata.get("snapshot") or {}).get("snapshot_id"),
        "content_hash": (metadata.get("snapshot") or {}).get("content_hash"),
        "metrics": metadata.get("metrics", {}),
        "tags": metadata.get("tags", []),
        "note": metadata.get("note", ""),
        "synthetic": bool(metadata.get("synthetic", False)),
    }


def register_experiment_routes(app: FastAPI, ctx: Any) -> None:
    @app.get("/api/experiments")
    def list_experiments(limit: int = 100, kind: str | None = None) -> Any:
        store = _store(ctx)
        return json_safe([_metadata_view(record) for record in store.list(kind=kind, limit=limit)])

    @app.get("/api/experiments/compare")
    def compare(ids: str) -> Any:
        wanted = [part.strip() for part in ids.split(",") if part.strip()]
        if len(wanted) < 2:
            raise HTTPException(status_code=400, detail="provide at least two run ids")
        if len(wanted) > 6:
            raise HTTPException(status_code=400, detail="compare at most six runs")
        store = _store(ctx)
        metrics: dict[str, Any] = {}
        equity: list[dict[str, Any]] = []
        for run_id in wanted:
            try:
                record = store.get(run_id)
                result = store.load_result(run_id)
            except ExperimentError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            metrics[run_id] = record.metadata.get("metrics", {})
            equity.append(
                {
                    "run_id": run_id,
                    "dates": result.dates.astype(int).tolist(),
                    "equity": result.equity_yuan.tolist(),
                }
            )
        return json_safe({"ids": wanted, "metrics": metrics, "equity": equity})

    @app.get("/api/experiments/{run_id}")
    def get_experiment(run_id: str) -> Any:
        store = _store(ctx)
        try:
            record = store.get(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        summary_path = record.directory / "summary.json"
        summary = (
            json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        )
        report_path = record.directory / "report.html"
        if report_path.exists():
            summary["report"] = str(report_path)
        payload: dict[str, Any] = {
            "run_id": run_id,
            "metadata": record.metadata,
            "summary": summary,
            "metrics": record.metadata.get("metrics", summary.get("metrics", {})),
        }
        try:
            payload["result"] = _result_payload(store.load_result(run_id))
        except ExperimentError:
            payload["result"] = None
        return json_safe(payload)

    @app.get("/api/experiments/{run_id}/result")
    def get_result(run_id: str) -> Any:
        store = _store(ctx)
        try:
            result = store.load_result(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _result_payload(result)

    @app.get("/api/experiments/{run_id}/report.pdf")
    def report_pdf(run_id: str) -> Any:
        store = _store(ctx)
        try:
            record = store.get(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        html = record.directory / "report.html"
        if not html.exists():
            raise HTTPException(status_code=404, detail="HTML report not found for this experiment")
        from ..report_pdf import PdfReportError, render_pdf

        pdf = record.directory / "report.pdf"
        if not pdf.exists():
            try:
                render_pdf(html, pdf)
            except PdfReportError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        return FileResponse(
            pdf,
            media_type="application/pdf",
            filename=f"{run_id}.pdf",
        )

    @app.post("/api/experiments/{run_id}/replay")
    def replay(run_id: str) -> Any:
        store = _store(ctx)
        try:
            store.get(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            outcome = replay_experiment(store, run_id)
        except ExperimentError as exc:
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

    @app.get("/api/experiments/{run_id}/report")
    def report(run_id: str) -> FileResponse:
        store = _store(ctx)
        try:
            record = store.get(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        target = record.directory / "report.html"
        if not target.exists():
            try:
                result = store.load_result(run_id)
            except ExperimentError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            render_html_report(
                result,
                output_path=target,
                strategy_metadata=(record.metadata.get("strategy") or {}),
                snapshot_metadata=(record.metadata.get("snapshot") or {}),
            )
        return FileResponse(target, media_type="text/html")

    @app.get("/api/experiments/{run_id}/export")
    def export(run_id: str) -> Response:
        store = _store(ctx)
        try:
            record = store.get(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(record.directory.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(record.directory))
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'},
        )

    @app.delete("/api/experiments/{run_id}")
    def delete(run_id: str) -> dict[str, Any]:
        try:
            _store(ctx).delete(run_id)
        except ExperimentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"run_id": run_id, "deleted": True}
