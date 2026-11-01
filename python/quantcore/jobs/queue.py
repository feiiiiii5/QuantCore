"""Simple SQLite-backed job queue with a single worker thread (M5 minimal).

Jobs run through a caller-supplied runner; the API server only accepts research
backtests.  There is no real order routing anywhere in this package.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

from ..data.state import SQLiteState

JobRunner = Callable[[dict[str, Any]], dict[str, Any]]


class JobQueue:
    """Background worker consuming jobs from :class:`SQLiteState`."""

    def __init__(
        self,
        state: SQLiteState,
        runner: JobRunner,
        *,
        poll_interval: float = 0.05,
        recover_on_start: bool = True,
    ) -> None:
        self.state = state
        self.runner = runner
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recover_on_start = recover_on_start

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if self._recover_on_start:
            self.state.recover_running_jobs()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="qc-job-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- worker loop ------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self.state.claim_job()
            if job is None:
                self._stop.wait(self.poll_interval)
                continue
            self._execute(job)

    def _execute(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        try:
            result = self.runner(dict(job.get("payload") or {}))
            self.state.complete_job(job_id, result)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
            self.state.fail_job(job_id, detail)

    # -- API --------------------------------------------------------------
    def submit(self, kind: str, payload: dict[str, Any]) -> str:
        return self.state.enqueue_job(kind, payload)

    def status(self, job_id: str) -> dict[str, Any] | None:
        return self.state.get_job(job_id)

    def result(self, job_id: str) -> Any:
        job = self.state.get_job(job_id)
        return None if job is None else job.get("result")

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self.state.list_jobs(status=status, limit=limit)

    def wait_for(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        """Block until a job finishes (tests and CLI convenience)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.state.get_job(job_id)
            if job is not None and job["status"] in {"done", "failed"}:
                return job
            time.sleep(0.01)
        return self.state.get_job(job_id)
