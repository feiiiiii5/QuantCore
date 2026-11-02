"""Data-integrity (data health) route over the current snapshot panel.

Read-only and offline: the route reuses the workspace snapshot panel and the local audit
module; it never calls a market-data provider. The response dict mirrors
ui/src/api/types.ts DataIntegrity. This module is registered by server/app.py (Lead wires
it in), so it deliberately avoids server-side schemas.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from ..data.integrity import audit_panel
from ..errors import QuantCoreError
from .workspace import Workspace, json_safe


def register_integrity_routes(app: FastAPI, workspace: Workspace) -> None:
    @app.get("/api/data/integrity")
    def data_integrity(snapshot: str | None = None) -> Any:
        try:
            panel, meta = workspace.panel(snapshot)
        except (FileNotFoundError, QuantCoreError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return json_safe(audit_panel(panel, snapshot=meta))
