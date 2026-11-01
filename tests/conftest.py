"""Shared pytest fixtures: synthetic panels, snapshots, warehouse roots and markers."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

import quantcore
from quantcore.data.panel import PanelData
from quantcore.data.store import ParquetStore
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
from quantcore.snapshot import Snapshot, build_snapshot, load_snapshot


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "bench: performance scale tests (QC_BENCH=1)")
    config.addinivalue_line("markers", "network: network-dependent tests (skipped by default)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("QC_BENCH") != "1":
        skip_bench = pytest.mark.skip(reason="performance test: set QC_BENCH=1 to run")
        for item in items:
            if "bench" in item.keywords:
                item.add_marker(skip_bench)
    if os.environ.get("QC_ALLOW_NETWORK") != "1":
        skip_network = pytest.mark.skip(reason="network test: set QC_ALLOW_NETWORK=1 to run")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)


@pytest.fixture(scope="session")
def small_panel() -> PanelData:
    """40 securities x 3 years of SYNTHETIC data (fast, covers all edge scenarios)."""
    return generate_synthetic_panel(
        SyntheticConfig(n_sec=40, start="2022-01-04", end="2024-12-31", seed=11)
    )


@pytest.fixture(scope="session")
def monthly_weights(small_panel: PanelData) -> np.ndarray:
    """Equal-weight the first 10 securities on month-start rebalances."""
    n_time, n_sec = small_panel.n_time, small_panel.n_sec
    weights = np.full((n_time, n_sec), np.nan, dtype=np.float64)
    count = min(10, n_sec)
    for day, flag in enumerate(small_panel.calendar.month_start_flags()):
        if flag:
            weights[day] = 0.0
            weights[day, :count] = 1.0 / count
    return weights


@pytest.fixture(scope="session")
def snapshot_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("snapshots")


@pytest.fixture(scope="session")
def synthetic_snapshot(small_panel: PanelData, snapshot_root: Path) -> Snapshot:
    if not quantcore.panel_available():
        pytest.skip("C++ .qpanel writer is unavailable")
    manifest = build_snapshot(small_panel, snapshot_root)
    return load_snapshot(snapshot_root, manifest.snapshot_id)


@pytest.fixture
def warehouse(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "warehouse")


def require_engine() -> None:
    if not quantcore.engine_available():
        pytest.skip("C++ backtest engine is unavailable")


# ---------------------------------------------------------------------------
# API v2 fixtures: real synthetic snapshot + experiment workspace (no network)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def experiments_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("experiments")


@pytest.fixture(scope="session")
def seeded_experiment(synthetic_snapshot: Snapshot, experiments_root: Path) -> object:
    """One real persistent backtest used by experiment/replay/attribution tests."""
    if not quantcore.engine_available():
        pytest.skip("C++ backtest engine is unavailable")
    from quantcore.experiments import ExperimentStore, run_experiment
    from quantcore.strategy.spec import StrategySpec

    spec = StrategySpec(
        name="api_momentum", template="momentum", params={"top_n": 5, "lookback": 60}
    )
    return run_experiment(
        ExperimentStore(experiments_root), spec, snapshot=synthetic_snapshot, report=True
    )


@pytest.fixture(scope="session")
def fake_ui_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Minimal built-UI tree so static serving can be tested without the real frontend."""
    root = tmp_path_factory.mktemp("ui-dist")
    (root / "assets").mkdir()
    (root / "index.html").write_text(
        "<!doctype html><html><head><title>QuantCore</title></head>"
        "<body><div id='root'>QuantCore UI</div>"
        "<script type='module' src='./assets/app.js'></script></body></html>",
        encoding="utf-8",
    )
    (root / "assets" / "app.js").write_text("console.log('quantcore ui');", encoding="utf-8")
    return root


@pytest.fixture()
def api_app(
    tmp_path: Path,
    snapshot_root: Path,
    experiments_root: Path,
    seeded_experiment: object,
    fake_ui_dir: Path,
):
    from quantcore.server import create_app

    return create_app(
        token="test-token",
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path,
        snapshots_root=snapshot_root,
        experiments_root=experiments_root,
        ui_dir=fake_ui_dir,
        start_worker=True,
    )


@pytest.fixture()
def api_client(api_app: object):
    from fastapi.testclient import TestClient

    with TestClient(api_app, base_url="http://127.0.0.1:8000") as client:
        client.headers.update({"Authorization": "Bearer test-token"})
        yield client


def api_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def ws_headers() -> dict[str, str]:
    """The Starlette TestClient sends ``Host: testserver`` for WebSockets; pin loopback."""
    return {"host": "127.0.0.1:8000"}


def local_app(tmp_path: Path, **kwargs: object):
    """Isolated app whose data/snapshots/experiments roots all live under ``tmp_path``."""
    from quantcore.server import create_app

    return create_app(
        token="test-token",
        port=8000,
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=tmp_path / "snapshots",
        experiments_root=tmp_path / "experiments",
        ui_dir=kwargs.pop("ui_dir", None),
        start_worker=True,
        **kwargs,
    )
