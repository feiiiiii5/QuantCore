"""Market-data read routes (snapshot-backed, synthetic-safe)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from ..data.panel import PANEL_FIELDS
from .workspace import Workspace, json_safe

INDEX_DEFS: tuple[tuple[str, str | None], ...] = (
    ("全市场", None),
    ("主板", "MAIN"),
    ("创业板", "GEM"),
    ("科创板", "STAR"),
)


def _latest_panel(ctx: Workspace, snapshot: str | None) -> tuple[Any, dict[str, Any]]:
    panel, meta = ctx.panel(snapshot, allow_synthetic=True)
    meta.setdefault("fields", [field for field in PANEL_FIELDS if field in panel.bars.columns])
    return panel, meta


def _parse_date(value: str | int) -> int:
    text = str(value).replace("-", "").replace("/", "")
    if len(text) != 8 or not text.isdigit():
        raise HTTPException(status_code=400, detail=f"invalid date: {value!r}")
    return int(text)


def _date_label(value: int) -> str:
    text = str(int(value))
    return f"{text[:4]}-{text[4:6]}-{text[6:]}" if len(text) == 8 else text


def _date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return _date_label(int(value))


def _index_series(panel: Any, board: str | None, points: int = 60) -> list[float]:
    close = panel.matrix("close")
    if close.size == 0:
        return []
    if board is not None:
        codes = panel.securities["board"].astype(str).to_numpy()
        mask = codes == board
        if not mask.any():
            return []
        close = close[:, mask]
    with np.errstate(divide="ignore", invalid="ignore"):
        prev = np.vstack([np.full((1, close.shape[1]), np.nan), close[:-1]])
        returns = close / prev - 1.0
    valid = np.isfinite(returns)
    counts = valid.sum(axis=1)
    avg = np.where(counts > 0, np.nansum(returns, axis=1) / np.maximum(counts, 1), 0.0)
    level = 1000.0 * np.cumprod(1.0 + avg)
    return [float(v) for v in level[-points:]]


def _overview(panel: Any) -> dict[str, Any]:
    dates = panel.calendar.dates
    close = panel.matrix("close")
    latest = close[-1] if close.size else np.array([])
    prev = close[-2] if close.shape[0] > 1 else latest
    with np.errstate(divide="ignore", invalid="ignore"):
        change = latest / prev - 1.0
    columns = set(panel.bars.columns)
    suspended = panel.matrix("suspended")[-1] if "suspended" in columns else np.zeros_like(latest)
    limit_up = (
        panel.matrix("limit_up")[-1] if "limit_up" in columns else np.full_like(latest, np.nan)
    )
    limit_down = (
        panel.matrix("limit_down")[-1] if "limit_down" in columns else np.full_like(latest, np.nan)
    )
    valid = np.isfinite(change) & (suspended <= 0.5)
    up = int(np.sum(valid & (change > 0.0001)))
    down = int(np.sum(valid & (change < -0.0001)))
    flat = int(np.sum(valid & (np.abs(change) <= 0.0001)))
    lu = int(
        np.sum(
            np.isfinite(latest)
            & np.isfinite(limit_up)
            & (latest >= limit_up - 0.005)
            & (suspended <= 0.5)
        )
    )
    ld = int(
        np.sum(
            np.isfinite(latest)
            & np.isfinite(limit_down)
            & (latest <= limit_down + 0.005)
            & (suspended <= 0.5)
        )
    )
    indices = []
    for name, board in INDEX_DEFS:
        spark = _index_series(panel, board)
        if not spark:
            continue
        pct = (spark[-1] / spark[-2] - 1.0) * 100.0 if len(spark) > 1 else 0.0
        indices.append(
            {
                "name": name,
                "close": round(spark[-1], 2),
                "change_pct": round(pct, 2),
                "spark": spark,
            }
        )
    sectors: list[dict[str, Any]] = []
    meta = panel.securities.reset_index(drop=True)
    if "industry" in meta.columns and len(meta) == len(latest):
        frame = pd.DataFrame(
            {"industry": meta["industry"].astype(str).to_numpy(), "change": change, "valid": valid}
        )
        for industry, group in frame.groupby("industry", dropna=False):
            rows = group[group["valid"]]
            if rows.empty:
                continue
            sectors.append(
                {
                    "name": str(industry),
                    "count": len(rows),
                    "avg_change": round(float(rows["change"].mean()) * 100.0, 2),
                    "up": int((rows["change"] > 0).sum()),
                    "down": int((rows["change"] < 0).sum()),
                }
            )
        sectors.sort(key=lambda item: abs(item["avg_change"]), reverse=True)
    return {
        "indices": indices,
        "breadth": {
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": lu,
            "limit_down": ld,
            "suspended": int((suspended > 0.5).sum()),
        },
        "sectors": sectors[:12],
        "as_of": _date_label(int(dates[-1])) if len(dates) else None,
    }


def _snapshot_info(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("snapshot_id"),
        "content_hash": meta.get("content_hash"),
        "n_sec": meta.get("n_sec"),
        "n_time": meta.get("n_time"),
        "start": _date_text(meta.get("start")),
        "end": _date_text(meta.get("end")),
        "synthetic": bool(meta.get("synthetic", False)),
        "source": meta.get("source"),
        "fields": list(meta.get("fields", [])),
        "created_at": meta.get("created_at") or "",
    }


def register_market_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.get("/api/market/overview")
    def overview(snapshot: str | None = Query(default=None)) -> Any:
        panel, meta = _latest_panel(ctx, snapshot)
        payload = _overview(panel)
        payload["snapshot"] = _snapshot_info(meta)
        payload["updated_at"] = meta.get("created_at") or ""
        return json_safe(payload)

    @app.get("/api/market/bars")
    def bars(
        code: str = Query(..., min_length=1),
        snapshot: str | None = Query(default=None),
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        limit: int = Query(default=600, ge=10, le=5000),
    ) -> Any:
        panel, meta = _latest_panel(ctx, snapshot)
        securities = panel.securities
        match = securities[
            (securities["code"].astype(str) == code) | (securities["sec_id"].astype(str) == code)
        ]
        if match.empty:
            raise HTTPException(status_code=404, detail=f"security not found: {code}")
        sec_id = str(match.iloc[0]["sec_id"])
        full = panel.bars[panel.bars["sec_id"].astype(str) == sec_id].sort_values("date")
        if full.empty:
            raise HTTPException(status_code=404, detail=f"no bars for {code}")
        full_close = full["close"].astype(float)
        full_ma5 = full_close.rolling(5).mean()
        full_ma20 = full_close.rolling(20).mean()
        frame = full
        if start:
            frame = frame[frame["date"] >= _parse_date(start)]
        if end:
            frame = frame[frame["date"] <= _parse_date(end)]
        frame = frame.tail(limit)
        if frame.empty:
            raise HTTPException(status_code=404, detail=f"no bars for {code} in range")
        positions = full.index.get_indexer(frame.index)
        close = frame["close"].astype(float)
        return json_safe(
            {
                "code": str(match.iloc[0]["code"]),
                "name": str(match.iloc[0].get("name", code)),
                "board": str(match.iloc[0].get("board", "MAIN")),
                "dates": [_date_label(int(v)) for v in frame["date"]],
                "open": frame["open"].astype(float).tolist(),
                "high": frame["high"].astype(float).tolist(),
                "low": frame["low"].astype(float).tolist(),
                "close": close.tolist(),
                "volume": frame["volume"].astype(float).tolist(),
                "amount": frame["amount"].astype(float).tolist(),
                "turnover": (frame["turnover"].astype(float) * 100.0).tolist()
                if "turnover" in frame
                else [],
                "ma5": full_ma5.iloc[positions].tolist(),
                "ma20": full_ma20.iloc[positions].tolist(),
                "limit_up": frame["limit_up"].astype(float).tolist() if "limit_up" in frame else [],
                "limit_down": frame["limit_down"].astype(float).tolist()
                if "limit_down" in frame
                else [],
                "suspended": frame["suspended"].astype(float).tolist()
                if "suspended" in frame
                else [],
                "synthetic": bool(meta.get("synthetic", False)),
            }
        )

    @app.get("/api/market/securities")
    def securities(
        snapshot: str | None = Query(default=None),
        query: str = Query(default=""),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> Any:
        panel, _ = _latest_panel(ctx, snapshot)
        bars = panel.bars.sort_values("date")
        latest = bars.groupby("sec_id", as_index=False).tail(1)
        meta = panel.securities.rename(columns={"sec_id": "sec_id"})
        frame = latest.merge(meta, on="sec_id", how="left", suffixes=("", "_meta"))
        if query:
            text = query.strip().lower()
            frame = frame[
                frame["code"].astype(str).str.lower().str.contains(text)
                | frame["name"].astype(str).str.lower().str.contains(text)
                | frame["sec_id"].astype(str).str.lower().str.contains(text)
            ]
        frame = frame.sort_values("code").head(limit)
        rows = []
        for row in frame.to_dict(orient="records"):
            rows.append(
                {
                    "sec_id": str(row["sec_id"]),
                    "code": str(row.get("code", "")),
                    "name": str(row.get("name", row.get("name_meta", ""))),
                    "board": str(row.get("board", "MAIN")),
                    "industry": str(row.get("industry", "")),
                    "last": float(row.get("close", 0.0)),
                    "change_pct": round(
                        float(row.get("close", 0.0))
                        / float(row.get("pre_close", row.get("close", 1.0)))
                        * 100
                        - 100,
                        2,
                    )
                    if row.get("pre_close")
                    else 0.0,
                    "turnover": round(float(row.get("turnover", 0.0)) * 100.0, 4),
                    "mktcap": float(row.get("mktcap", 0.0)),
                    "float_mktcap": float(row.get("float_mktcap", 0.0)),
                    "suspended": bool(float(row.get("suspended", 0.0)) > 0.5),
                    "st": bool(float(row.get("st", 0.0)) > 0.5),
                    "exchange": str(row.get("exchange", "")),
                    "sec_type": str(row.get("sec_type", "STOCK")),
                    "list_date": int(row.get("list_date", 0) or 0),
                    "delist_date": int(row.get("delist_date", 0) or 0),
                    "source": str(row.get("source", "")),
                }
            )
        return json_safe(rows)

    @app.get("/api/market/securities/{code}")
    def security_profile(code: str, snapshot: str | None = Query(default=None)) -> Any:
        panel, _ = _latest_panel(ctx, snapshot)
        meta = panel.securities
        match = meta[
            (meta["code"].astype(str) == str(code)) | (meta["sec_id"].astype(str) == str(code))
        ]
        if match.empty:
            raise HTTPException(status_code=404, detail=f"unknown security: {code}")
        record = match.iloc[0].to_dict()
        bars = panel.bars[panel.bars["sec_id"].astype(str) == str(record["sec_id"])].sort_values(
            "date"
        )
        latest = bars.tail(1).to_dict(orient="records")
        quote = latest[0] if latest else {}
        previous = float(quote.get("pre_close") or quote.get("close") or 0.0)
        close = float(quote.get("close") or 0.0)
        return json_safe(
            {
                "sec_id": str(record["sec_id"]),
                "code": str(record.get("code", "")),
                "name": str(record.get("name", "")),
                "exchange": str(record.get("exchange", "")),
                "board": str(record.get("board", "MAIN")),
                "sec_type": str(record.get("sec_type", "STOCK")),
                "industry": str(record.get("industry", "")),
                "source": str(record.get("source", "")),
                "list_date": int(record.get("list_date", 0) or 0),
                "delist_date": int(record.get("delist_date", 0) or 0),
                "quote": {
                    "date": int(quote.get("date", 0) or 0),
                    "close": close,
                    "pre_close": previous,
                    "change_pct": round(close / previous * 100 - 100, 4) if previous else 0.0,
                    "open": float(quote.get("open") or 0.0),
                    "high": float(quote.get("high") or 0.0),
                    "low": float(quote.get("low") or 0.0),
                    "volume": float(quote.get("volume") or 0.0),
                    "amount": float(quote.get("amount") or 0.0),
                    "turnover": round(float(quote.get("turnover") or 0.0) * 100.0, 4),
                    "st": bool(float(quote.get("st") or 0.0) > 0.5),
                    "suspended": bool(float(quote.get("suspended") or 0.0) > 0.5),
                },
            }
        )
