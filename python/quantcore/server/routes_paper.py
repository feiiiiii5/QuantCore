"""Paper-trading API: local virtual accounts over historical data or public live quotes.

State persists under ``<data_root>/paper/paper_<hex>.json`` (atomic JSON); every mutation
is serialised per session with :class:`quantcore.paper.PaperStore` locks. Historical
accounts use immutable snapshots; live accounts read the existing quote service.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, NoReturn

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from ..errors import QuantCoreError
from ..paper import (
    LivePaperSessionEngine,
    PaperConflictError,
    PaperError,
    PaperMarketData,
    PaperSession,
    PaperSessionEngine,
    PaperStore,
)
from ..paper.portfolio import build_portfolio
from .schemas import (
    PaperAutoRequest,
    PaperOrderRequest,
    PaperPortfolioRequest,
    PaperSessionCreateRequest,
    PaperStepRequest,
)
from .workspace import Workspace, json_safe


def _snapshot_meta(workspace: Workspace, snapshot: Any, panel: Any) -> dict[str, Any]:
    return {
        "id": snapshot.snapshot_id,
        "snapshots_root": str(workspace.settings.snapshots_root),
        "content_hash": snapshot.manifest.content_hash,
        "synthetic": bool(snapshot.manifest.synthetic),
        "source": snapshot.manifest.source,
        "created_at": snapshot.manifest.created_at,
        "n_sec": int(panel.n_sec),
        "n_time": int(panel.n_time),
        "start": int(panel.calendar.dates[0]),
        "end": int(panel.calendar.dates[-1]),
    }


def register_paper_routes(app: FastAPI, workspace: Workspace) -> None:
    store = PaperStore(Path(workspace.settings.data_root) / "paper")
    auto_runs: dict[str, dict[str, Any]] = {}

    def _fail(exc: PaperError) -> NoReturn:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    def _engine_for(session: PaperSession) -> PaperSessionEngine:
        if session.mode == "live":
            return LivePaperSessionEngine(session)
        reference = str(session.snapshot.get("id") or "")
        try:
            snapshot = workspace.snapshot(reference or None)
        except (FileNotFoundError, QuantCoreError) as exc:
            raise PaperConflictError(f"snapshot unavailable for paper session: {exc}") from exc
        panel = workspace.snapshot_panel(snapshot)
        return PaperSessionEngine(PaperMarketData(panel), session)

    def _load_engine(session_id: str) -> PaperSessionEngine:
        try:
            session = store.load(session_id)
            return _engine_for(session)
        except PaperError as exc:
            _fail(exc)

    def _mutate(session_id: str, callback: Any) -> Any:
        with store.session_lock(session_id):
            try:
                session = store.load(session_id)
            except PaperError as exc:
                _fail(exc)
            try:
                engine = _engine_for(session)
                result = callback(engine)
            except PaperError as exc:
                _fail(exc)
            store.save(session)
            return result

    @app.post("/api/paper/sessions", status_code=201)
    def create_session(payload: PaperSessionCreateRequest) -> Any:
        if payload.mode == "live":
            session = LivePaperSessionEngine.create_live(
                initial_cash=float(payload.initial_cash),
                name=payload.name,
                now=app.state.live.clock(),
            )
            store.save(session)
            return json_safe(session.session_view())
        try:
            snapshot = workspace.snapshot(payload.snapshot)
        except (FileNotFoundError, QuantCoreError) as exc:
            raise HTTPException(
                status_code=404,
                detail=f"snapshot unavailable: {exc}; run onboarding or build a snapshot first",
            ) from exc
        panel = workspace.snapshot_panel(snapshot)
        market = PaperMarketData(panel)
        try:
            session = PaperSessionEngine.create(
                market,
                snapshot=_snapshot_meta(workspace, snapshot, panel),
                initial_cash=float(payload.initial_cash),
                start=payload.start,
                end=payload.end,
                name=payload.name,
            )
            # Validate event models and dates before persisting the account.
            PaperSessionEngine(market, session)
        except PaperError as exc:
            _fail(exc)
        store.save(session)
        return json_safe(session.session_view())

    def _auto_loop(session_id: str, stop: threading.Event, interval_ms: int, days: int) -> None:
        state = auto_runs.setdefault(session_id, {})
        state.update(running=True, ticks=0, error=None)
        while not stop.wait(interval_ms / 1000.0):
            with store.session_lock(session_id):
                try:
                    session = store.load(session_id)
                    engine = _engine_for(session)
                    if session.status != "active" or session.current_date >= session.end_date:
                        state["running"] = False
                        return
                    engine.step(days=days)
                    store.save(session)
                    state["ticks"] = int(state.get("ticks") or 0) + 1
                except PaperError as exc:
                    state.update(running=False, error=exc.message)
                    return
        state["running"] = False

    @app.post("/api/paper/sessions/{session_id}/auto")
    def start_auto(session_id: str, payload: PaperAutoRequest | None = None) -> Any:
        body = payload or PaperAutoRequest()
        current = auto_runs.get(session_id)
        if current and current.get("running"):
            raise HTTPException(status_code=409, detail="paper auto-run is already active")
        try:
            session = store.load(session_id)
        except PaperError as exc:
            _fail(exc)
        if session.mode == "live":
            raise HTTPException(
                status_code=400, detail="live accounts use quote refresh, not historical auto-run"
            )
        if session.status != "active" or session.current_date >= session.end_date:
            raise HTTPException(status_code=409, detail="paper session is already finished")
        stop = threading.Event()
        state: dict[str, Any] = {
            "stop": stop,
            "thread": None,
            "running": True,
            "ticks": 0,
            "error": None,
        }
        thread = threading.Thread(
            target=_auto_loop,
            args=(session_id, stop, int(body.interval_ms), int(body.days_per_tick)),
            daemon=True,
            name=f"qc-paper-auto-{session_id}",
        )
        state["thread"] = thread
        auto_runs[session_id] = state
        thread.start()
        return {
            "session_id": session_id,
            "running": True,
            "interval_ms": body.interval_ms,
            "days_per_tick": body.days_per_tick,
        }

    @app.post("/api/paper/sessions/{session_id}/auto/stop")
    def stop_auto(session_id: str) -> Any:
        state = auto_runs.get(session_id)
        if state is None:
            return {"session_id": session_id, "running": False, "stopped": False}
        stop = state.get("stop")
        if isinstance(stop, threading.Event):
            stop.set()
        state["running"] = False
        return {
            "session_id": session_id,
            "running": False,
            "stopped": True,
            "ticks": state.get("ticks", 0),
        }

    @app.get("/api/paper/sessions/{session_id}/auto")
    def auto_status(session_id: str) -> Any:
        state = auto_runs.get(session_id) or {}
        return {
            "session_id": session_id,
            "running": bool(state.get("running")),
            "ticks": int(state.get("ticks") or 0),
            "error": state.get("error"),
        }

    @app.get("/api/paper/sessions")
    def list_sessions() -> Any:
        return json_safe([session.session_view() for session in store.list()])

    @app.post("/api/paper/portfolio")
    def paper_portfolio(payload: PaperPortfolioRequest) -> Any:
        sessions: list[PaperSession] = []
        seen: set[str] = set()
        for allocation in payload.allocations:
            session_id = allocation.session_id
            if session_id in seen:
                raise HTTPException(
                    status_code=400, detail=f"duplicate paper session: {session_id}"
                )
            seen.add(session_id)
            try:
                sessions.append(store.load(session_id))
            except PaperError as exc:
                _fail(exc)
        try:
            report = build_portfolio(
                sessions,
                [float(item.weight) for item in payload.allocations],
                float(payload.initial_cash),
            )
        except PaperError as exc:
            _fail(exc)
        return json_safe(report)

    @app.get("/api/paper/sessions/{session_id}")
    def get_session(session_id: str) -> Any:
        return json_safe(_load_engine(session_id).detail())

    @app.post("/api/paper/sessions/{session_id}/refresh")
    async def refresh_session(session_id: str) -> Any:
        try:
            session = store.load(session_id)
        except PaperError as exc:
            _fail(exc)
        if session.mode != "live":
            raise HTTPException(
                status_code=400, detail="quote refresh requires a live paper account"
            )
        codes = sorted(
            {position.code for position in session.positions.values()}
            | {order.code for order in session.orders if order.is_open}
        )
        live = app.state.live
        quotes = await live.quotes(codes) if codes else {"quotes": [], "stale": False}
        status = await live.status()
        with store.session_lock(session_id):
            try:
                session = store.load(session_id)
                result = LivePaperSessionEngine(session).refresh(quotes, status, now=live.clock())
                store.save(session)
            except PaperError as exc:
                _fail(exc)
        return json_safe(result)

    @app.post("/api/paper/sessions/{session_id}/step")
    def step_session(session_id: str, payload: PaperStepRequest | None = None) -> Any:
        body = payload or PaperStepRequest()
        if body.to_date is not None and body.days != 1:
            raise HTTPException(
                status_code=400, detail="provide either 'days' or 'to_date', not both"
            )

        def operation(engine: PaperSessionEngine) -> Any:
            return engine.step(days=body.days, to_date=body.to_date)

        return json_safe(_mutate(session_id, operation))

    @app.post("/api/paper/sessions/{session_id}/reset")
    def reset_session(session_id: str) -> Any:
        def operation(engine: PaperSessionEngine) -> Any:
            return engine.reset()

        return json_safe(_mutate(session_id, operation))

    @app.post("/api/paper/sessions/{session_id}/orders")
    def submit_order(session_id: str, payload: PaperOrderRequest) -> Any:
        def operation(engine: PaperSessionEngine) -> Any:
            order = engine.submit_order(
                code=payload.code,
                side=payload.side,
                qty=int(payload.qty),
                order_type=payload.order_type,
                limit_price=payload.limit_price,
            )
            return {"order": order.to_dict()}

        return json_safe(_mutate(session_id, operation))

    @app.post("/api/paper/sessions/{session_id}/orders/{order_id}/cancel")
    def cancel_order(session_id: str, order_id: str) -> Any:
        def operation(engine: PaperSessionEngine) -> Any:
            order = engine.cancel_order(order_id)
            return {"order": order.to_dict(), "cancelled": True}

        return json_safe(_mutate(session_id, operation))

    @app.get("/api/paper/sessions/{session_id}/signals.csv")
    def signals_csv(session_id: str) -> Response:
        engine = _load_engine(session_id)
        csv_text = engine.signals_csv()
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{session_id}_signals.csv"'},
        )

    @app.delete("/api/paper/sessions/{session_id}")
    def delete_session(session_id: str) -> Any:
        state = auto_runs.get(session_id)
        if state and isinstance(state.get("stop"), threading.Event):
            state["stop"].set()
        with store.session_lock(session_id):
            try:
                store.delete(session_id)
            except PaperError as exc:
                _fail(exc)
        return {"id": session_id, "deleted": True}
