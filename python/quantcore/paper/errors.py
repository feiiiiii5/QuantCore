"""Errors raised by the local paper-trading simulator (mapped to HTTP by the API layer)."""

from __future__ import annotations


class PaperError(Exception):
    """Base class; ``status_code`` is what the API route returns."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PaperValidationError(PaperError):
    """Invalid request/order for the current paper session (HTTP 400)."""

    status_code = 400


class PaperNotFoundError(PaperError):
    """Unknown session/order (HTTP 404)."""

    status_code = 404


class PaperConflictError(PaperError):
    """Valid request that conflicts with session state (HTTP 409)."""

    status_code = 409


__all__ = [
    "PaperConflictError",
    "PaperError",
    "PaperNotFoundError",
    "PaperValidationError",
]
