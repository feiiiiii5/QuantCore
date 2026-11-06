"""A slow worker remains owned while shutdown drains it; restart cannot duplicate it."""

import threading
from pathlib import Path

from quantcore.data.state import SQLiteState
from quantcore.jobs.queue import JobQueue


def test_stop_retains_live_worker_and_cooperatively_cancels(tmp_path: Path) -> None:
    entered, release = threading.Event(), threading.Event()

    def runner(payload):
        entered.set()
        assert release.wait(5)
        return payload

    queue = JobQueue(SQLiteState(tmp_path / "state.sqlite"), runner)
    first = queue.submit("test", {"first": True})
    queue.start()
    try:
        assert entered.wait(5)
        queue.stop(timeout=0.01)
        assert queue.running  # The timeout must not discard ownership of the live thread.
        assert queue.state.is_cancel_requested(first)
        second = queue.submit("test", {"second": True})
        queue.start()  # Still draining: never start a second consumer or recover its live job.
        assert queue.status(first)["status"] == "running"
        assert queue.status(second)["status"] == "pending"
        release.set()
        queue.stop()
        assert not queue.running
        assert queue.status(first)["status"] == "cancelled"
        assert queue.status(second)["status"] == "pending"
        queue.start()
        assert queue.wait_for(second, timeout=5)["status"] == "done"
    finally:
        release.set()
        queue.stop()


def test_stop_cancels_job_claimed_before_current_registration(tmp_path: Path) -> None:
    claimed, release = threading.Event(), threading.Event()
    calls = []
    queue = JobQueue(SQLiteState(tmp_path / "state.sqlite"), lambda payload: calls.append(payload))
    original_claim = queue.state.claim_job

    def hold_claim():
        job = original_claim()
        claimed.set()
        assert release.wait(5)
        return job

    queue.state.claim_job = hold_claim
    job_id = queue.submit("test", {})
    queue.start()
    try:
        assert claimed.wait(5)
        queue.stop(timeout=0)
        release.set()
        queue.stop()
        assert queue.status(job_id)["status"] == "cancelled"
        assert calls == []
    finally:
        release.set()
        queue.stop()
