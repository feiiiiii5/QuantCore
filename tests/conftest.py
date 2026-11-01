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
