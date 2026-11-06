"""Loopback API security with optional, explicitly trusted HTTPS browser origins."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
AUTH_SCHEME = "Bearer"


def https_origin(value: str) -> str:
    """Validate and canonicalize one exact HTTPS origin, never a URL or wildcard."""
    if not value or any(char.isspace() for char in value) or any(char in value for char in "*\\?#"):
        raise ValueError(
            "allowed origins must be exact HTTPS origins without wildcards or URL paths"
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.netloc.endswith(":")
            or "%" in parsed.netloc
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("invalid origin")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError) as exc:
        raise ValueError(
            "allowed origins must be exact HTTPS origins, e.g. https://example.com"
        ) from exc
    if ":" in host:
        host = f"[{host}]"
    return f"https://{host}" + (f":{port}" if port not in {None, 443} else "")


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

    def __post_init__(self) -> None:
        origins = tuple(dict.fromkeys(https_origin(value) for value in self.allowed_origins or ()))
        object.__setattr__(self, "allowed_origins", origins)

    def allowed_host(self, host_header: str) -> bool:
        """Validate the ``Host`` header hostname (and port when given)."""
        if (
            not host_header
            or any(char.isspace() for char in host_header)
            or any(char in host_header for char in "/\\?#@")
        ):
            return False
        try:
            parsed = urlsplit(f"//{host_header}")
            hostname, port = (parsed.hostname or "").lower(), parsed.port
        except ValueError:
            return False
        return (
            hostname in self.allowed_hosts
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and (port is None or port == self.port)
        )

    def allowed_origin(self, origin: str) -> bool:
        """Validate a browser origin against loopback or the exact HTTPS allowlist."""
        if (
            not origin
            or origin == "null"
            or any(char.isspace() for char in origin)
            or any(char in origin for char in "*\\?#")
        ):
            return False
        if self.allowed_origins is not None and origin in self.allowed_origins:
            return True
        try:
            parsed = urlsplit(origin)
            hostname, port = (parsed.hostname or "").lower(), parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme in {"http", "https"}
            and hostname in self.allowed_hosts
            and parsed.username is None
            and parsed.password is None
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and (port is None or port == self.port)
        )

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
            "cors": bool(self.allowed_origins),
            "allowed_origins": list(self.allowed_origins or ()),
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
        preflight = (
            request.method == "OPTIONS"
            and origin in (self.security.allowed_origins or ())
            and bool(request.headers.get("access-control-request-method"))
        )
        if (
            request.url.path.startswith(self.security.protected_prefix)
            and not preflight
            and not (self.security.authorized(request.headers.get("authorization")))
        ):
            headers = {"WWW-Authenticate": AUTH_SCHEME}
            # Security remains outside CORS to validate even preflight Host headers.
            # Let trusted frontends read the authentication error without cookies.
            if origin in (self.security.allowed_origins or ()):
                headers.update({"Access-Control-Allow-Origin": str(origin), "Vary": "Origin"})
            return JSONResponse(
                {"detail": "missing or invalid bearer token"},
                status_code=401,
                headers=headers,
            )
        return await call_next(request)

    def summary(self) -> dict[str, object]:
        return self.security.public_dict()
