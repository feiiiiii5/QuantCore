"""File-backed paper-trading state store (one small JSON file per session).

Why JSON instead of SQLite: a session is a single self-contained document (account,
orders, trades, equity curve) that the UI can back up or inspect; sessions stay re-openable
after a restart, writes are atomic (tmp file + ``os.replace``), and no schema migration is
needed for the M9 scope.  Files live under ``<data_root>/paper/paper_<hex>.json``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from collections.abc import Iterator
from pathlib import Path

from .errors import PaperNotFoundError, PaperValidationError
from .models import PaperSession

SESSION_ID_RE = re.compile(r"^paper_[0-9a-f]{12}$")
FILE_PREFIX = "paper_"


class PaperStore:
    """Atomic per-session JSON persistence with per-session locks."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    # -- paths -------------------------------------------------------------
    def _validate_id(self, session_id: str) -> str:
        text = str(session_id)
        if not SESSION_ID_RE.match(text):
            raise PaperNotFoundError(f"paper session not found: {session_id!r}")
        return text

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{self._validate_id(session_id)}.json"

    # -- locking -----------------------------------------------------------
    @contextlib.contextmanager
    def session_lock(self, session_id: str) -> Iterator[None]:
        """Serialise load-modify-save for one session across API worker threads."""
        sid = self._validate_id(session_id)
        with self._guard:
            lock = self._locks.setdefault(sid, threading.RLock())
        with lock:
            yield

    # -- CRUD --------------------------------------------------------------
    def save(self, session: PaperSession) -> None:
        self._validate_id(session.id)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path_for(session.id)
        temporary = target.with_name(f".{target.name}.tmp")
        payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=1, sort_keys=True)
        temporary.write_text(payload, encoding="utf-8")
        try:
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
        except OSError:  # pragma: no cover - fsync is best-effort on some filesystems
            pass
        os.replace(temporary, target)

    def load(self, session_id: str) -> PaperSession:
        path = self.path_for(session_id)
        if not path.exists():
            raise PaperNotFoundError(f"paper session not found: {session_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperValidationError(f"paper session file is corrupt: {path.name}") from exc
        if not isinstance(payload, dict):
            raise PaperValidationError(f"paper session file is corrupt: {path.name}")
        return PaperSession.from_dict(payload)

    def list(self) -> list[PaperSession]:
        if not self.root.exists():
            return []
        sessions: list[PaperSession] = []
        for path in sorted(self.root.glob(f"{FILE_PREFIX}*.json")):
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                session = PaperSession.from_dict(payload)
            except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue  # tolerate a half-written/foreign file instead of breaking the list
            sessions.append(session)
        sessions.sort(key=lambda item: item.created_at, reverse=True)
        return sessions

    def delete(self, session_id: str) -> None:
        path = self.path_for(session_id)
        if not path.exists():
            raise PaperNotFoundError(f"paper session not found: {session_id}")
        path.unlink()
        with self._guard:
            self._locks.pop(path.stem, None)


__all__ = ["PaperStore"]
