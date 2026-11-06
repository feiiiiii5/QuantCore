"""`qc serve` command: run the local research API + built UI on 127.0.0.1."""

# ruff: noqa: B008 - Typer options are intentionally declared in argument defaults.

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path

import typer

DEFAULT_DATA_ROOT = Path("data")
DEFAULT_EXPERIMENTS_ROOT = Path("experiments")


def serve_command(
    port: int = typer.Option(8000, min=1, max=65535),
    token: str | None = typer.Option(
        None, "--token", help="Bearer token (default: QC_SERVER_TOKEN or generated)"
    ),
    ui_dir: Path | None = typer.Option(
        None, "--ui-dir", help="Built UI directory (default: ui/dist when present)"
    ),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT),
    experiments_root: Path = typer.Option(DEFAULT_EXPERIMENTS_ROOT),
    state_path: Path | None = typer.Option(None),
    open_browser: bool = typer.Option(
        False, "--open/--no-open", help="Open the tokenised URL in a browser"
    ),
    start_worker: bool = typer.Option(True),
    allow_origin: list[str] | None = typer.Option(
        None, "--allow-origin", help="Exact trusted HTTPS browser origin; may be repeated"
    ),
) -> None:
    """Run the local research API + built UI on 127.0.0.1 (loopback only)."""
    import uvicorn

    from quantcore.server import SecurityMiddleware, ServerSecurity, create_app, resolve_token

    resolved_token, generated = resolve_token(token)
    try:
        configured_security = ServerSecurity(
            token=resolved_token,
            port=port,
            token_generated=generated,
            allowed_origins=tuple(allow_origin or ()),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--allow-origin") from exc
    application = create_app(
        security=configured_security,
        port=port,
        state_path=state_path if state_path is not None else data_root / "state.sqlite",
        data_root=data_root,
        experiments_root=experiments_root,
        ui_dir=ui_dir,
        start_worker=start_worker,
    )
    security = SecurityMiddleware(application, application.state.security).summary()
    url = f"http://127.0.0.1:{port}/?token={resolved_token}"
    effective_ui = Path(ui_dir) if ui_dir is not None else Path("ui/dist")
    if generated:
        typer.echo("qc serve: generated API token (set QC_SERVER_TOKEN or --token to pin it)")
    typer.echo(
        json.dumps(
            {
                "listen": f"127.0.0.1:{port}",
                "url": url,
                "security": security,
                "ui_served": (effective_ui / "index.html").exists(),
            }
        )
    )
    if open_browser:
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="info")


__all__ = ["serve_command"]
