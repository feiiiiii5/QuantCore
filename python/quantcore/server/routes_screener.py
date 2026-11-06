"""Screener routes: expression DSL over the latest visible cross-section."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException

from ..errors import StrategyValidationError
from ..strategy.base import PanelView, UniverseFilter
from ..strategy.expr import evaluate_expression
from .schemas import SavedScreenerRequest, ScreenerRequest
from .workspace import Workspace, json_safe

SAVED_FILE = "screener_saved.json"


def _saved_path(ctx: Workspace) -> Path:
    return ctx.settings.data_root / SAVED_FILE


def _load_saved(ctx: Workspace) -> list[dict[str, Any]]:
    path = _saved_path(ctx)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return payload if isinstance(payload, list) else []


def _write_saved(ctx: Workspace, items: list[dict[str, Any]]) -> None:
    path = _saved_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


PRESETS = [
    {
        "id": "momentum",
        "name": "动量 20 日",
        "description": "20 日收益横截面前 20%",
        "expression": "rank(ret(close,20)) > 0.8",
    },
    {
        "id": "low_vol",
        "name": "低波动 60 日",
        "description": "60 日波动率最低 20%",
        "expression": "rank(std(ret(close,1),60)) < 0.2",
    },
    {
        "id": "trend",
        "name": "双均线趋势",
        "description": "5 日均线高于 20 日均线",
        "expression": "ma(close,5) > ma(close,20)",
    },
    {
        "id": "liquid",
        "name": "高流动性",
        "description": "成交额前 30%",
        "expression": "rank(amount) > 0.7",
    },
    {
        "id": "quality_momentum",
        "name": "质量动量",
        "description": "动量前 30% 且低波动",
        "expression": "rank(ret(close,60)) > 0.7 and rank(std(ret(close,1),60)) < 0.5",
    },
]


def _universe(payload: dict[str, Any]) -> UniverseFilter:
    boards = payload.get("boards")
    return UniverseFilter(
        exclude_st=bool(payload.get("exclude_st", True)),
        exclude_suspended=bool(payload.get("exclude_suspended", True)),
        min_price=float(payload.get("min_price", 1.0)),
        min_list_days=int(payload.get("min_list_days", 0)),
        boards=tuple(str(item) for item in boards) if boards else None,
        min_amount=float(payload.get("min_amount", 0.0)),
    )


def register_screener_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.get("/api/screener/presets")
    def presets() -> list[dict[str, Any]]:
        return PRESETS

    @app.get("/api/screener/saved")
    def list_saved() -> Any:
        return json_safe(_load_saved(ctx))

    @app.post("/api/screener/saved", status_code=201)
    def save_screener(payload: SavedScreenerRequest) -> Any:
        try:
            evaluate_expression(payload.expression, PanelView(ctx.synthetic_panel()))
        except (StrategyValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        items = _load_saved(ctx)
        item = {
            "id": f"scr_{secrets.token_hex(6)}",
            "name": payload.name,
            "expression": payload.expression,
            "created_at": datetime.now(UTC).isoformat(),
        }
        items.insert(0, item)
        _write_saved(ctx, items)
        return item

    @app.delete("/api/screener/saved/{item_id}")
    def delete_saved(item_id: str) -> dict[str, Any]:
        items = _load_saved(ctx)
        kept = [item for item in items if item.get("id") != item_id]
        if len(kept) == len(items):
            raise HTTPException(status_code=404, detail=f"unknown saved screener: {item_id}")
        _write_saved(ctx, kept)
        return {"id": item_id, "deleted": True}

    @app.post("/api/screener/run")
    def run(payload: ScreenerRequest) -> Any:
        panel, meta = ctx.panel(payload.snapshot, allow_synthetic=True)
        view = PanelView(panel)
        try:
            scores = np.asarray(evaluate_expression(payload.expression, view), dtype=np.float64)
        except (StrategyValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        universe = _universe(payload.universe)
        eligible = universe.eligible_mask(view)[-1]
        latest = scores[-1] if scores.ndim == 2 else np.full(panel.n_sec, float(scores))
        finite = np.isfinite(latest)
        boolean_like = np.all((~finite) | (latest == 0.0) | (latest == 1.0))
        matched = eligible & finite & (latest > 0.5) if boolean_like else eligible & finite
        indices = np.flatnonzero(matched)
        matched_count = len(indices)
        if not boolean_like:
            indices = indices[np.argsort(-latest[indices], kind="stable")]
        indices = indices[: payload.limit]
        rows: list[dict[str, Any]] = []
        meta_frame = panel.securities.reset_index(drop=True)
        close = view.field("close")[-1]
        pre_close = view.field("pre_close")[-1] if "pre_close" in panel.bars.columns else close
        turnover = view.field("turnover")[-1]
        mktcap = view.field("mktcap")[-1]
        for idx in indices:
            record = meta_frame.iloc[int(idx)].to_dict() if int(idx) < len(meta_frame) else {}
            score = float(latest[int(idx)])
            rows.append(
                {
                    "sec_id": str(record.get("sec_id", idx)),
                    "code": str(record.get("code", "")),
                    "name": str(record.get("name", "")),
                    "board": str(record.get("board", "MAIN")),
                    "industry": str(record.get("industry", "")),
                    "close": float(close[int(idx)]),
                    "change_pct": round(
                        (float(close[int(idx)]) / float(pre_close[int(idx)]) - 1.0) * 100, 2
                    )
                    if np.isfinite(pre_close[int(idx)]) and pre_close[int(idx)]
                    else 0.0,
                    "turnover": round(float(turnover[int(idx)]) * 100.0, 4),
                    "mktcap": float(mktcap[int(idx)]),
                    "score": score,
                }
            )
        return json_safe(
            {
                "as_of": int(panel.calendar.dates[-1]),
                "snapshot": meta.get("snapshot_id"),
                "synthetic": bool(meta.get("synthetic", False)),
                "universe_count": int(eligible.sum()),
                "matched_count": matched_count,
                "rows": rows,
            }
        )
