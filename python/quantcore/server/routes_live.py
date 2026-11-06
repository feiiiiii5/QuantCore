"""Live quote REST + WebSocket routes (read-only; network is opt-in server side)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..realtime.quotes import QuoteSourceError, normalize_code
from ..realtime.service import LiveQuoteService
from .security import ServerSecurity

MAX_CODES = 50


def _parse_codes(raw: str | None) -> list[str]:
    """Parse a comma-separated A-share code list (deduplicated, bounded)."""
    if not raw:
        return []
    codes: list[str] = []
    for part in raw.replace(" ", ",").split(","):
        text = part.strip()
        if not text:
            continue
        try:
            code = normalize_code(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if code not in codes:
            codes.append(code)
    if len(codes) > MAX_CODES:
        raise HTTPException(status_code=400, detail=f"at most {MAX_CODES} codes per request")
    return codes


def register_live_routes(app: FastAPI, service: LiveQuoteService, security: ServerSecurity) -> None:
    """Expose /api/live/* and /ws/live; quotes come from the cached poller."""

    @app.get("/api/live/status")
    async def live_status() -> Any:
        return await service.status()

    @app.get("/api/live/indices")
    async def live_indices() -> Any:
        return await service.indices()

    @app.get("/api/live/quotes")
    async def live_quotes(codes: str | None = Query(default=None)) -> Any:
        return await service.quotes(_parse_codes(codes))

    @app.get("/api/live/bars")
    async def live_bars(
        code: str = Query(...), limit: int = Query(default=600, ge=10, le=2000)
    ) -> Any:
        try:
            normalized = normalize_code(code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not service.config.enabled:
            raise HTTPException(
                status_code=409, detail="live daily candles require QC_ALLOW_NETWORK=1"
            )
        try:
            return await service.bars(normalized, limit)
        except QuoteSourceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.websocket("/ws/live")
    async def live_socket(websocket: WebSocket, codes: str | None = Query(default=None)) -> None:
        token = websocket.query_params.get("token", "")
        host = websocket.headers.get("host", "")
        origin = websocket.headers.get("origin")
        if not security.allowed_host(host) or not security.authorized(f"Bearer {token}"):
            await websocket.close(code=1008, reason="unauthorized")
            return
        if origin is not None and not security.allowed_origin(origin):
            await websocket.close(code=1008, reason="origin not allowed")
            return
        try:
            requested = _parse_codes(codes)
        except HTTPException:
            await websocket.close(code=1008, reason="invalid codes")
            return
        await websocket.accept()
        interval = max(2.0, service.config.interval_seconds)
        try:
            while True:
                await websocket.send_json(await service.websocket_payload(requested))
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            return


__all__ = ["MAX_CODES", "register_live_routes"]
