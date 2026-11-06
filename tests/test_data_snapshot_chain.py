"""A promised import-to-snapshot job must finish without a second browser request."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantcore.data.store import ParquetStore
from quantcore.jobs.queue import JobCancelledError
from quantcore.server import create_app
from quantcore.server.runner import run_data_update_job, run_snapshot_job
from quantcore.snapshot import load_snapshot
from quantcore.snapshot.builder import snapshot_content_hash


def payload(root: Path, **updates):
    return {
        "provider": "synthetic",
        "data_root": str(root),
        "n_sec": 3,
        "start": "2023-01-03",
        "end": "2023-12-29",
        "seed": 19,
        "reset": True,
        "incremental": False,
        **updates,
    }


def test_app_factory_keeps_jobs_in_the_selected_workspace(tmp_path):
    app = create_app(data_root=tmp_path, token="test-token", start_worker=False)
    assert app.state.settings.state_path == tmp_path / "state.sqlite"


def test_one_update_request_builds_a_usable_snapshot_without_a_ui_followup(tmp_path):
    data, snapshots = tmp_path / "data", tmp_path / "custom-snapshots"
    app = create_app(
        data_root=data,
        snapshots_root=snapshots,
        state_path=tmp_path / "api.sqlite",
        token="test-token",
    )
    auth = {"Authorization": "Bearer test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        body = payload(data, build_snapshot=True)
        body.pop("data_root")
        accepted = client.post("/api/data/update", json=body, headers=auth)
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]
        for _ in range(400):
            job = client.get(f"/api/jobs/{job_id}", headers=auth).json()
            if job["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(0.02)
        assert job["status"] == "done", job
        result = client.get(f"/api/jobs/{job_id}/result", headers=auth).json()["result"]
        snapshot = load_snapshot(snapshots, result["snapshot_id"])
        panel = ParquetStore(data / "warehouse").load_panel()
        assert snapshot.manifest.content_hash == snapshot_content_hash(panel)[0]
        assert snapshot.manifest.synthetic and snapshot.manifest.panel["available"]
        assert result["kind"] == "data_update" and result["snapshot"]["n_sec"] == 3
        assert len(app.state.state.list_jobs()) == 1  # No browser-submitted snapshot job.


def test_legacy_import_does_not_build_an_unsolicited_snapshot(tmp_path):
    result = run_data_update_job(payload(tmp_path))
    assert result["quality_passed"]
    assert "snapshot_id" not in result and not (tmp_path / "snapshots").exists()


def test_snapshot_failure_retains_import_for_manual_retry(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("snapshot disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr("quantcore.server.runner.build_snapshot_from_store", unavailable)
        with pytest.raises(RuntimeError, match=r"import succeeded.*snapshot.*failed"):
            run_data_update_job(payload(tmp_path, build_snapshot=True))
    assert len(ParquetStore(tmp_path / "warehouse").read_dataset("bars")) > 0
    retry = run_snapshot_job({"data_root": str(tmp_path)})
    assert load_snapshot(tmp_path / "snapshots", retry["snapshot_id"]).manifest.synthetic


def test_cancel_after_import_does_not_publish_a_snapshot(tmp_path):
    class Cancellation:
        progress = 0.0

        def update_progress(self, value):
            self.progress = value

        def raise_if_cancelled(self):
            if self.progress >= 0.8:
                raise JobCancelledError("cancelled after import")

    with pytest.raises(JobCancelledError):
        run_data_update_job(payload(tmp_path, build_snapshot=True), Cancellation())
    assert len(ParquetStore(tmp_path / "warehouse").read_dataset("bars")) > 0
    assert not (tmp_path / "snapshots").exists()


def test_queued_imports_freeze_their_own_cohort_before_the_next_job(tmp_path):
    app = create_app(data_root=tmp_path, state_path=tmp_path / "api.sqlite", token="test-token")
    auth = {"Authorization": "Bearer test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        jobs = []
        for count in (3, 4):
            body = payload(tmp_path, n_sec=count, build_snapshot=True)
            body.pop("data_root")
            response = client.post("/api/data/update", json=body, headers=auth)
            assert response.status_code == 202, response.text
            jobs.append(response.json()["job_id"])
        for job_id, count in zip(jobs, (3, 4), strict=True):
            for _ in range(400):
                job = client.get(f"/api/jobs/{job_id}", headers=auth).json()
                if job["status"] in {"done", "failed", "cancelled"}:
                    break
                time.sleep(0.02)
            assert job["status"] == "done", job
            result = job["result"]
            snap = load_snapshot(tmp_path / "snapshots", result["snapshot_id"])
            assert snap.manifest.metadata["n_sec"] == count
        assert len(app.state.state.list_jobs()) == 2


def test_cancel_during_freeze_retains_the_committed_snapshot(tmp_path, monkeypatch):
    from quantcore.server import runner

    class Cancellation:
        cancelled = False

        def update_progress(self, value):
            pass

        def raise_if_cancelled(self):
            if self.cancelled:
                raise JobCancelledError("cancelled during freeze")

    context = Cancellation()
    original = runner.build_snapshot_from_store

    def committed_then_cancelled(*args, **kwargs):
        manifest = original(*args, **kwargs)
        context.cancelled = True
        return manifest

    monkeypatch.setattr(runner, "build_snapshot_from_store", committed_then_cancelled)
    with pytest.raises(JobCancelledError):
        run_data_update_job(payload(tmp_path, build_snapshot=True), context)
    directories = list((tmp_path / "snapshots").glob("snap_*"))
    assert len(directories) == 1
    snapshot = load_snapshot(tmp_path / "snapshots", directories[0].name)
    assert snapshot.manifest.panel["available"]
