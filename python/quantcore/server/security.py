"""API security: loopback-only, bearer token, Host/Origin validation, CORS disabled.

The server is a local research UI backend: it binds to 127.0.0.1, requires a bearer
token on ``/api/*``, rejects non-loopback ``Host``/``Origin`` headers (DNS-rebinding
protection) and does not install any CORS middleware (no cross-origin browser access).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
AUTH_SCHEME = "Bearer"


def resolve_token(
    explicit: str | None = None,
    environ: dict[str, str] | None = None,
    *,
    generate: bool = True,
) -> tuple[str, bool]:
    """Resolve the bearer token and whether it was auto-generated."""
    import os

    env = os.environ if environ is None else environ
    if explicit:
        return explicit, False
    from_env = env.get("QC_SERVER_TOKEN")
    if from_env:
        return from_env, False
    if generate:
        return secrets.token_urlsafe(32), True
    raise RuntimeError("no API token provided (set QC_SERVER_TOKEN or pass token=...)")


@dataclass(frozen=True)
class ServerSecurity:
    """Security configuration for one server instance."""

    token: str
    port: int = 8000
    allowed_hosts: tuple[str, ...] = tuple(sorted(LOOPBACK_HOSTS))
    allowed_origins: tuple[str, ...] | None = None
    protected_prefix: str = "/api"
    token_generated: bool = False

    def allowed_host(self, host_header: str) -> bool:
        """Validate the ``Host`` header hostname (and port when given)."""
        if not host_header:
            return False
        parsed = urlsplit(f"//{host_header}")
        hostname = (parsed.hostname or "").lower()
        if hostname not in self.allowed_hosts:
            return False
        return parsed.port is None or parsed.port == self.port

    def allowed_origin(self, origin: str) -> bool:
        """Validate a browser ``Origin`` header against loopback origins."""
        if not origin or origin == "null":
            return False
        if self.allowed_origins is not None and origin in self.allowed_origins:
            return True
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"}:
            return False
        hostname = (parsed.hostname or "").lower()
        if hostname not in self.allowed_hosts:
            return False
        return parsed.port is None or parsed.port == self.port

    def authorized(self, authorization_header: str | None) -> bool:
        if not authorization_header:
            return False
        scheme, _, credentials = authorization_header.partition(" ")
        if scheme.lower() != AUTH_SCHEME.lower():
            return False
        return secrets.compare_digest(credentials.strip(), self.token)

    def public_dict(self) -> dict[str, object]:
        return {
            "port": self.port,
            "allowed_hosts": list(self.allowed_hosts),
            "protected_prefix": self.protected_prefix,
            "cors": False,
            "token_generated": self.token_generated,
        }


class SecurityMiddleware(BaseHTTPMiddleware):
    """Enforce Host/Origin checks and bearer auth for the protected prefix."""

    def __init__(self, app: object, security: ServerSecurity) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.security = security

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "")
        if not self.security.allowed_host(host):
            return JSONResponse(
                {"detail": f"host not allowed: {host!r} (server is loopback-only)"},
                status_code=400,
            )
        origin = request.headers.get("origin")
        if origin is not None and not self.security.allowed_origin(origin):
            return JSONResponse({"detail": f"origin not allowed: {origin!r}"}, status_code=403)
        if request.url.path.startswith(self.security.protected_prefix) and not (
            self.security.authorized(request.headers.get("authorization"))
        ):
            return JSONResponse(
                {"detail": "missing or invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": AUTH_SCHEME},
            )
        return await call_next(request)

    def summary(self) -> dict[str, object]:
        return self.security.public_dict()
