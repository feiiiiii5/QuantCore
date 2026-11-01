"""SQLite-backed job queue with cooperative cancellation and progress reporting.

The worker consumes jobs from :class:`SQLiteState`.  A runner may accept either
``(payload)`` (legacy) or ``(payload, ctx)``; the latter receives a :class:`JobContext`
with coarse progress updates and cancellation checks.  Cancellation semantics:

- queued (``pending``) jobs are cancelled immediately by the API;
- running jobs get ``cancel_requested=1``; the worker/runner checks it before and after
  the heavy phase and the job ends as ``cancelled``;
- crashed jobs (status ``running`` while the process died) are marked ``failed`` on the
  next startup so the UI never hangs on a ghost job.
"""

from __future__ import annotations

import inspect
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..data.state import TERMINAL_JOB_STATUSES, SQLiteState


class JobCancelledError(Exception):
    """Raised by a runner when it observes a cancellation request."""


@dataclass
class JobContext:
    """Handed to cancellation-aware job runners."""

    job_id: str
    kind: str
    state: SQLiteState
    _last_progress: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_progress(self, value: float) -> None:
        """Persist monotonic progress in ``[0, 1]`` (throttled to 0.01 steps)."""
        progress = max(0.0, min(1.0, float(value)))
        with self._lock:
            if progress < self._last_progress + 0.01 and progress < 1.0:
                return
            self._last_progress = progress
        self.state.update_job_progress(self.job_id, progress)

    def cancel_requested(self) -> bool:
        return self.state.is_cancel_requested(self.job_id)

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested():
            raise JobCancelledError(f"job {self.job_id} was cancelled")

    def summary(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "kind": self.kind, "cancelled": self.cancel_requested()}


#: ``(payload)`` or ``(payload, ctx)`` runner.
JobRunner = Callable[..., dict[str, Any]]


def runner_accepts_context(runner: JobRunner) -> bool:
    """True when ``runner`` takes a second positional argument (the job context)."""
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):  # pragma: no cover - builtins/C functions
        return False
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return len(positional) >= 2


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
        self._pass_context = runner_accepts_context(runner)
        self._current: JobContext | None = None
        self._current_lock = threading.Lock()

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

    @property
    def current_job_id(self) -> str | None:
        with self._current_lock:
            return None if self._current is None else self._current.job_id

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
        context = JobContext(job_id=job_id, kind=str(job["kind"]), state=self.state)
        with self._current_lock:
            self._current = context
        try:
            if context.cancel_requested():
                self.state.mark_cancelled(job_id, error="cancelled before start")
                return
            payload = dict(job.get("payload") or {})
            result = self.runner(payload, context) if self._pass_context else self.runner(payload)
            if context.cancel_requested():
                self.state.mark_cancelled(job_id, error="cancelled by user")
            else:
                self.state.complete_job(job_id, result)
        except JobCancelledError:
            self.state.mark_cancelled(job_id, error="cancelled by user")
        except Exception as exc:  # job failures must be persisted, not raised
            detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
            self.state.fail_job(job_id, detail)
        finally:
            with self._current_lock:
                self._current = None

    # -- API --------------------------------------------------------------
    def submit(self, kind: str, payload: dict[str, Any]) -> str:
        return self.state.enqueue_job(kind, payload)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        """Request cancellation; running jobs end cooperatively via the worker."""
        return self.state.request_cancel(job_id)

    def status(self, job_id: str) -> dict[str, Any] | None:
        return self.state.get_job(job_id)

    def result(self, job_id: str) -> Any:
        job = self.state.get_job(job_id)
        return None if job is None else job.get("result")

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self.state.list_jobs(status=status, limit=limit)

    def is_terminal(self, job_id: str) -> bool:
        job = self.state.get_job(job_id)
        return job is not None and str(job["status"]) in TERMINAL_JOB_STATUSES

    def wait_for(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        """Block until a job finishes (tests and CLI convenience)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.state.get_job(job_id)
            if job is not None and str(job["status"]) in TERMINAL_JOB_STATUSES:
                return job
            time.sleep(0.01)
        return self.state.get_job(job_id)
