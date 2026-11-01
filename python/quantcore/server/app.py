"""Local FastAPI research server (M5/M6): loopback-only, bearer-token protected.

Serves the built UI from the same origin (no CORS), exposes the UI-API v2 contract and
runs research jobs on a single worker.  There is no order routing or broker gateway.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

import quantcore

from ..data.state import SQLiteState
from ..errors import (
    CppUnavailableError,
    ExperimentError,
    QuantCoreError,
    SnapshotError,
    StrategyValidationError,
)
from ..jobs.queue import JobQueue
from .routes_data import register_data_routes
from .routes_experiments import register_experiment_routes
from .routes_jobs import register_job_routes
from .routes_market import register_market_routes
from .routes_research import register_research_routes
from .routes_screener import register_screener_routes
from .routes_strategies import register_strategy_routes
from .runner import run_job
from .schemas import HealthView
from .security import SecurityMiddleware, ServerSecurity, resolve_token
from .workspace import Settings, Workspace, json_safe

LOGGER = logging.getLogger(__name__)

DEFAULT_STATE_PATH = "data/state.sqlite"
DEFAULT_SNAPSHOTS_ROOT = "data/snapshots"
API_PREFIXES = ("api/", "ws/", "docs", "openapi", "redoc")

# Bootstrap the bearer token from the `?token=` URL printed by `qc serve --open`; the token
# is moved to localStorage and stripped from the address bar, so reloads stay authorised.
TOKEN_BOOTSTRAP = (
    "<script>/* qc_token_boot */"
    "(function(){try{var q=new URLSearchParams(location.search);"
    "var t=q.get('token');if(t){localStorage.setItem('qc_token',t);q.delete('token');"
    "history.replaceState(null,'',location.pathname+(q.toString()?'?'+q:''));}"
    "}catch(e){}})();</script>"
)


def default_job_runner(payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for the default job dispatcher."""
    return run_job(payload)


def _synthetic_only(workspace: Workspace) -> bool:
    manifests = workspace.list_snapshot_manifests()
    return True if not manifests else all(bool(item.synthetic) for item in manifests)


def create_app(
    *,
    token: str | None = None,
    port: int = 8000,
    state_path: str | Path = DEFAULT_STATE_PATH,
    runner: Any = None,
    start_worker: bool = True,
    security: ServerSecurity | None = None,
    data_root: str | Path | None = None,
    snapshots_root: str | Path | None = None,
    experiments_root: str | Path | None = None,
    ui_dir: str | Path | None = None,
    serve_ui: bool = True,
) -> FastAPI:
    """Build the FastAPI application (no CORS middleware, loopback security)."""
    if security is None:
        resolved_token, generated = resolve_token(token)
        security = ServerSecurity(token=resolved_token, port=port, token_generated=generated)
    settings = Settings.create(
        data_root=data_root,
        snapshots_root=snapshots_root,
        experiments_root=experiments_root,
        state_path=state_path,
        ui_dir=ui_dir,
    )
    state = SQLiteState(settings.state_path)
    queue = JobQueue(state, runner or run_job)
    workspace = Workspace(settings=settings, state=state, queue=queue)

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
    app.state.workspace = workspace
    app.state.settings = settings
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityMiddleware, security=security)

    # -- error contract: {"detail": ...}; 400/401/403/404/409/422/500 -------------------
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(SnapshotError)
    @app.exception_handler(ExperimentError)
    async def not_found(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(StrategyValidationError)
    async def invalid_strategy(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(CppUnavailableError)
    async def engine_unavailable(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": f"engine unavailable: {exc}"}, status_code=503)

    @app.exception_handler(QuantCoreError)
    async def quantcore_error(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("unhandled API error: %s", exc)
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    @app.get("/health", response_model=HealthView)
    def health() -> HealthView:
        return HealthView(
            version=quantcore.__version__,
            engine_backend=quantcore.engine_backend(),
            engine_available=quantcore.engine_available(),
            panel_available=quantcore.panel_available(),
            synthetic_only=_synthetic_only(workspace),
            cors=False,
        )

    @app.get("/api/meta")
    def meta() -> Any:
        index_path = settings.ui_dir / "index.html"
        return json_safe(
            {
                "version": quantcore.__version__,
                "engine_backend": quantcore.engine_backend(),
                "engine_available": quantcore.engine_available(),
                "synthetic_only": _synthetic_only(workspace),
                "data_root": str(settings.data_root),
                "snapshots_root": str(settings.snapshots_root),
                "experiments_root": str(settings.experiments_root),
                "token_required": True,
                "ui_served": bool(index_path.exists()),
                "cors": False,
                "api_version": "v2",
            }
        )

    register_job_routes(app, workspace, security)
    register_market_routes(app, workspace)
    register_screener_routes(app, workspace)
    register_strategy_routes(app, workspace)
    register_experiment_routes(app, workspace)
    register_data_routes(app, workspace)
    register_research_routes(app, workspace)

    # -- built UI (same origin): assets mount + SPA fallback; API routes always win -----
    ui_root = settings.ui_dir.resolve()
    index_path = ui_root / "index.html"
    assets_dir = ui_root / "assets"
    if serve_ui and assets_dir.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=assets_dir), name="ui-assets")

    def _ui_missing() -> JSONResponse:
        return JSONResponse(
            {"detail": "UI build not found; run `pnpm -C ui build`"},
            status_code=404,
        )

    def serve_index() -> Any:
        if not (serve_ui and index_path.exists()):
            return _ui_missing()
        html = index_path.read_text(encoding="utf-8")
        if "qc_token_boot" not in html:
            html = html.replace("</head>", TOKEN_BOOTSTRAP + "</head>")
        return HTMLResponse(html)

    @app.get("/", include_in_schema=False)
    def ui_index() -> Any:
        return serve_index()

    @app.get("/{full_path:path}", include_in_schema=False)
    def ui_fallback(full_path: str) -> Any:
        path = full_path.strip("/")
        if not path:
            return serve_index()
        if path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404, detail="not found")
        if not serve_ui:
            return _ui_missing()
        candidate = (ui_root / path).resolve()
        try:
            candidate.relative_to(ui_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="not found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        if Path(path).suffix:
            # A missing asset (js/css/png/...) must 404, not masquerade as index.html.
            raise HTTPException(status_code=404, detail="not found")
        return serve_index()

    return app


__all__ = ["create_app", "default_job_runner"]
