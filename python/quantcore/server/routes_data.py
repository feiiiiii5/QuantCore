"""Data status, provider, update, snapshot, quality and onboarding routes."""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from ..data.store import ParquetStore
from ..data.synthetic import SyntheticConfig
from ..errors import QuantCoreError
from ..experiments import ExperimentStore, run_experiment
from ..ingest import ProviderIngestor
from ..providers import create_provider, describe_providers
from ..providers.synthetic import SyntheticProvider
from ..snapshot.builder import build_snapshot_from_store
from ..snapshot.reader import list_snapshots
from ..strategy.spec import StrategySpec
from .schemas import DataUpdateRequest, OnboardingRequest, SnapshotBuildRequest
from .workspace import Workspace, json_safe

NETWORK_PROVIDERS = {"tushare", "akshare", "mootdx"}
PROVIDER_LABELS = {
    "synthetic": "Synthetic (合成)",
    "local": "LocalFile (本地文件)",
    "tushare": "Tushare Pro",
    "akshare": "AKShare",
    "mootdx": "mootdx",
}


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _provider_available(name: str) -> bool:
    if name == "synthetic":
        return True
    if name == "local":
        return True
    if name == "tushare":
        return bool(os.environ.get("TUSHARE_TOKEN"))
    if name in {"akshare", "mootdx"}:
        return os.environ.get("QC_ALLOW_NETWORK") == "1" and (
            importlib.util.find_spec(name) is not None
        )
    return False


def _provider_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in describe_providers():
        name = str(item.get("name", "unknown"))
        permission = item.get("permission") or {}
        rows.append(
            {
                "id": name,
                "name": PROVIDER_LABELS.get(name, name),
                "requires_token": bool(permission.get("requires_credentials", False)),
                "requires_network": name in NETWORK_PROVIDERS,
                "available": _provider_available(name),
                "capabilities": item.get("capabilities", {}),
            }
        )
    return rows


def _date_label(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(int(value))
    if len(text) != 8:
        return text
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _snapshot_view(manifest: Any) -> dict[str, Any]:
    return {
        "id": manifest.snapshot_id,
        "content_hash": manifest.content_hash,
        "created_at": manifest.created_at,
        "synthetic": manifest.synthetic,
        "source": manifest.source,
        "n_sec": manifest.metadata.get("n_sec"),
        "n_time": manifest.metadata.get("n_time"),
        "start": _date_label(manifest.metadata.get("start")),
        "end": _date_label(manifest.metadata.get("end")),
        "panel_available": bool(manifest.panel.get("available", False)),
        "quality": manifest.quality,
        "fields": manifest.panel.get("fields", []),
    }


def _data_status(ctx: Workspace) -> dict[str, Any]:
    data_root = ctx.settings.data_root
    warehouse = ParquetStore(data_root / "warehouse", state=ctx.state)
    manifest = warehouse.manifest
    manifests = list_snapshots(ctx.settings.snapshots_root)
    free = shutil.disk_usage(data_root if data_root.exists() else Path.cwd()).free
    return json_safe(
        {
            "data_root": str(data_root),
            "warehouse": {
                "exists": bool(manifest.datasets),
                "datasets": {name: stats.rows for name, stats in manifest.datasets.items()},
                "rows": sum(stats.rows for stats in manifest.datasets.values()),
                "bytes": _size(data_root / "warehouse"),
                "manifest_hash": warehouse.manifest_hash(),
            },
            "snapshots": [_snapshot_view(item) for item in manifests],
            "storage": {
                "warehouse_bytes": _size(data_root / "warehouse"),
                "snapshot_bytes": _size(ctx.settings.snapshots_root),
                "experiments_bytes": _size(ctx.settings.experiments_root),
                "free_bytes": free,
            },
            "providers": _provider_rows(),
        }
    )


def _approved_roots(
    ctx: Workspace, data_root: str | None, snapshots_root: str | None
) -> tuple[Path, Path]:
    effective_data = Path(data_root) if data_root else ctx.settings.data_root
    effective_snapshots = Path(snapshots_root) if snapshots_root else ctx.settings.snapshots_root
    return effective_data, effective_snapshots


def register_data_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.get("/api/data/status")
    def status() -> Any:
        return _data_status(ctx)

    @app.get("/api/data/providers")
    def providers() -> Any:
        return _provider_rows()

    @app.get("/api/data/snapshots")
    def snapshots() -> Any:
        return json_safe(
            [_snapshot_view(item) for item in list_snapshots(ctx.settings.snapshots_root)]
        )

    @app.get("/api/data/quality")
    def quality(snapshot: str | None = None) -> Any:
        try:
            snap = ctx.snapshot(snapshot)
        except (FileNotFoundError, QuantCoreError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        report_path = snap.root / "quality_report.json"
        report: dict[str, Any] | None = None
        if report_path.exists():
            import json

            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - corrupt artefact
                report = None
        return json_safe(
            {
                "snapshot_id": snap.snapshot_id,
                "synthetic": snap.manifest.synthetic,
                "quality": snap.manifest.quality,
                "report": report,
            }
        )

    @app.post("/api/data/update", status_code=202)
    def update(payload: DataUpdateRequest) -> dict[str, Any]:
        name = payload.provider
        kwargs: dict[str, Any] = {}
        if name == "local":
            if not payload.local_dir:
                raise HTTPException(status_code=422, detail="local provider requires 'local_dir'")
            kwargs["data_dir"] = payload.local_dir
        elif name == "tushare" and payload.fixture_dir:
            kwargs["fixture_dir"] = payload.fixture_dir
        try:
            create_provider(name, **kwargs)
        except Exception as exc:  # provider construction errors are 422
            raise HTTPException(status_code=422, detail=f"invalid provider: {exc}") from exc
        data_root, snapshots_root = _approved_roots(ctx, None, str(ctx.settings.snapshots_root))
        job_payload = {
            "kind": "data_update",
            **payload.model_dump(),
            "data_root": str(data_root),
            "snapshots_root": str(snapshots_root),
            "state_path": str(ctx.settings.state_path),
        }
        return {"job_id": ctx.queue.submit("data_update", job_payload), "status": "pending"}

    @app.post("/api/data/snapshot", status_code=202)
    def snapshot(payload: SnapshotBuildRequest) -> dict[str, Any]:
        data_root, snapshots_root = _approved_roots(ctx, payload.data_root, payload.snapshots_root)
        state_path = ctx.settings.state_path
        if data_root != ctx.settings.data_root:
            state_path = data_root / "state.sqlite"
        job_payload = {
            "kind": "snapshot_build",
            "require_qpanel": payload.require_qpanel,
            "data_root": str(data_root),
            "snapshots_root": str(snapshots_root),
            "state_path": str(state_path),
        }
        return {"job_id": ctx.queue.submit("snapshot_build", job_payload), "status": "pending"}

    @app.post("/api/onboarding/bootstrap")
    def onboarding(payload: OnboardingRequest) -> Any:
        config = SyntheticConfig(
            n_sec=payload.n_sec, start=payload.start, end=payload.end, seed=payload.seed
        )
        data_root = ctx.settings.data_root
        snapshots_root = ctx.settings.snapshots_root
        snapshots_root.mkdir(parents=True, exist_ok=True)
        store = ParquetStore(data_root / "warehouse", state=ctx.state)
        ingestor = ProviderIngestor(SyntheticProvider(config), store)
        ingestor.update(payload.start, payload.end)
        manifest = build_snapshot_from_store(
            store, snapshots_root, state=ctx.state, require_qpanel=True
        )
        snapshot = ctx.snapshot(manifest.snapshot_id)
        experiment_store = ExperimentStore(ctx.settings.experiments_root)
        spec = StrategySpec(
            name="demo_momentum", template="momentum", params={"top_n": 5, "lookback": 60}
        )
        record = run_experiment(experiment_store, spec, snapshot=snapshot, report=True)
        return json_safe(
            {
                "snapshot": manifest.snapshot_id,
                "snapshot_dir": str(snapshots_root / manifest.snapshot_id),
                "snapshot_meta": _snapshot_view(manifest),
                "run_id": record.run_id,
                "report": str(record.directory / "report.html"),
                "synthetic": True,
                "message": (
                    "SYNTHETIC demo warehouse, snapshot and backtest created; "
                    "results are not real market performance and not investment advice."
                ),
            }
        )
