"""Beginner onboarding, plain-language presets and local watchlist routes.

The routes are local-only and never fetch quotes themselves.  They are registered by
``create_app`` (wiring owned by the integration lead) and must sit before the SPA
catch-all, like the other ``/api`` routes.  Tests can also mount this module directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from ..onboarding import (
    PRESETS,
    build_state,
    complete_step,
    read_watchlist,
    reset_onboarding,
    save_watchlist,
)
from .workspace import Workspace


def register_onboarding_routes(app: FastAPI, workspace: Workspace) -> None:
    """Register beginner onboarding, preset and watchlist endpoints."""

    @app.get("/api/onboarding")
    def onboarding_state() -> dict[str, Any]:
        return build_state(workspace)

    @app.post("/api/onboarding/complete")
    def onboarding_complete(payload: dict[str, Any]) -> dict[str, Any]:
        step = payload.get("step")
        if not isinstance(step, str):
            raise HTTPException(status_code=400, detail="body must be {'step': '<id>'}")
        try:
            return complete_step(workspace, step)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/onboarding/reset")
    def onboarding_reset() -> dict[str, Any]:
        return reset_onboarding(workspace)

    @app.get("/api/onboarding/presets")
    def onboarding_presets() -> list[dict[str, Any]]:
        return [dict(preset) for preset in PRESETS]

    @app.get("/api/watchlist")
    def watchlist() -> dict[str, Any]:
        return {"codes": read_watchlist(workspace)}

    @app.put("/api/watchlist")
    def update_watchlist(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            codes = save_watchlist(workspace, payload.get("codes"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"codes": codes}


__all__ = ["register_onboarding_routes"]
