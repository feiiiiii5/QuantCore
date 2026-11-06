"""qc data commands: provider update, warehouse status and the data-health audit.

Extracted from cli.py to keep files below the 500-line project limit; registered on the
qc data Typer app by quantcore.cli. Research/simulation only - network access requires
QC_ALLOW_NETWORK=1 (or --allow-network).
"""

# ruff: noqa: B008 -- typer's documented API uses function calls in argument defaults

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

DEFAULT_DATA_ROOT = Path("data")
DEFAULT_SNAPSHOTS_ROOT = DEFAULT_DATA_ROOT / "snapshots"


def _emit(payload: dict[str, Any], json_output: bool = True) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def data_update(
    provider: str = typer.Option("synthetic", help="synthetic | local | tushare | ..."),
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT, help="data directory"),
    start: str = typer.Option("2020-01-02"),
    end: str = typer.Option("2024-12-31"),
    n_sec: int = typer.Option(200, min=1),
    seed: int = typer.Option(42),
    local_dir: Path | None = typer.Option(None, help="local provider data directory"),
    fixture_dir: Path | None = typer.Option(None, help="tushare fixture directory"),
    codes: str | None = typer.Option(None, help="comma-separated codes for sina/eastmoney/tushare"),
    limit: int | None = typer.Option(None, min=1, help="cap securities for sina/eastmoney"),
    allow_network: bool = typer.Option(
        False, envvar="QC_ALLOW_NETWORK", help="explicitly allow network access for data providers"
    ),
    derive_actions: bool = typer.Option(
        True,
        "--derive-actions/--no-derive-actions",
        help="sina: derive adj factors/corporate actions from Tencent qfq (slower)",
    ),
    incremental: bool = typer.Option(True),
    reset: bool = typer.Option(False),
    json_output: bool = typer.Option(True),
) -> None:
    """Fetch/normalise data into the Parquet warehouse (quality-gated)."""
    from quantcore.data.store import ParquetStore
    from quantcore.ingest import ProviderIngestor
    from quantcore.providers import create_provider

    store = ParquetStore(data_root / "warehouse")
    provider = provider.strip().lower()
    kwargs: dict[str, Any] = {}
    if provider == "synthetic":
        from quantcore.data.synthetic import SyntheticConfig

        kwargs["config"] = SyntheticConfig(n_sec=n_sec, start=start, end=end, seed=seed)
    elif provider == "local":
        if local_dir is None:
            raise typer.BadParameter("--local-dir is required for the local provider")
        kwargs["data_dir"] = local_dir
    elif provider == "tushare" and fixture_dir is not None:
        kwargs["fixture_dir"] = fixture_dir
    if provider == "tushare":
        kwargs["allow_network"] = allow_network
    code_list = [part.strip() for part in codes.split(",") if part.strip()] if codes else None
    if provider in {"sina", "eastmoney"}:
        kwargs["allow_network"] = allow_network
        if code_list:
            kwargs["codes"] = code_list
        if limit is not None:
            kwargs["limit"] = limit
        if provider == "sina":
            kwargs["derive_actions"] = derive_actions
    elif limit is not None or (code_list and provider != "tushare"):
        raise typer.BadParameter(
            "--codes requires sina/eastmoney/tushare; --limit requires sina/eastmoney"
        )
    prov = create_provider(provider, **kwargs)
    ingestor = ProviderIngestor(prov, store)
    result = ingestor.update(start, end, codes=code_list, incremental=incremental, reset=reset)
    payload = result.to_dict()
    payload["manifest_hash"] = store.manifest_hash()
    _emit(payload, json_output)


def data_integrity(
    snapshot: str | None = typer.Option(
        None, help="snapshot id/prefix; default: latest snapshot or the SYNTHETIC demo"
    ),
    snapshots_root: Path = typer.Option(DEFAULT_SNAPSHOTS_ROOT),
    json_output: bool = typer.Option(True, "--json-output/--no-json-output"),
) -> None:
    """Run the offline data-integrity audit (exit code 1 when status=fail)."""
    from quantcore.data.integrity import audit_panel
    from quantcore.data.synthetic import generate_quick_panel
    from quantcore.errors import SnapshotError
    from quantcore.snapshot import find_snapshot, list_snapshots

    meta: dict[str, Any]
    if snapshot is not None:
        try:
            snap = find_snapshot(snapshots_root, snapshot)
        except (SnapshotError, FileNotFoundError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        panel = snap.to_panel_data()
        meta = snap.describe()
    else:
        manifests = list_snapshots(snapshots_root)
        if manifests:
            snap = find_snapshot(snapshots_root, manifests[0].snapshot_id)
            panel = snap.to_panel_data()
            meta = snap.describe()
        else:
            panel = generate_quick_panel(n_sec=40)
            meta = {
                "snapshot_id": "synthetic",
                "synthetic": True,
                "source": "SYNTHETIC",
                "n_sec": panel.n_sec,
                "n_time": panel.n_time,
                "start": int(panel.calendar.dates[0]),
                "end": int(panel.calendar.dates[-1]),
            }
    result = audit_panel(panel, snapshot=meta)
    _emit(result, json_output)
    if result["status"] == "fail":
        raise typer.Exit(code=1)


def data_status(
    data_root: Path = typer.Option(DEFAULT_DATA_ROOT),
    json_output: bool = typer.Option(True),
) -> None:
    """Show warehouse datasets, manifest hash and ingest metadata."""
    from quantcore.data.store import ParquetStore

    store = ParquetStore(data_root / "warehouse")
    payload = store.describe()
    payload["last_ingest"] = store.get_metadata("last_ingest")
    _emit(payload, json_output)
