"""Fair comparison of persisted experiment results, including legacy provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.result import BacktestResult
from quantcore.experiments.comparison import compare_experiments
from quantcore.experiments.store import ExperimentStore
from quantcore.server import create_app


def _save(
    store: ExperimentStore,
    run_id: str,
    *,
    cash: float = 100.0,
    values: tuple[float, ...] = (100.0, 110.0, 99.0),
    dates: tuple[int, ...] = (20240102, 20240103, 20240104),
    config_updates: dict[str, Any] | None = None,
    snapshot_updates: dict[str, Any] | None = None,
    legacy: bool = False,
) -> None:
    config = BacktestConfig(initial_cash=cash).to_dict()
    config.update(config_updates or {})
    snapshot = {
        "snapshot_id": "synthetic-fixture",
        "content_hash": "synthetic-fixture-hash",
        "synthetic": True,
        "source": "SYNTHETIC",
        **(snapshot_updates or {}),
    }
    metadata = {
        "strategy_name": run_id,
        "strategy": {"template": "momentum", "params": {"top_n": 5}},
        "strategy_hash": run_id,
        "environment": {"git_commit": "fixture-commit"},
        "synthetic": True,
    }
    equity = np.round(np.array(values) * 10000).astype(np.int64)
    result = BacktestResult(
        dates=np.array(dates, dtype=np.int64),
        equity=equity,
        cash=equity.copy(),
        market_value=np.zeros(len(values), dtype=np.int64),
        trades=pd.DataFrame(),
        metrics={"total_return": values[-1] / cash - 1.0} if values else {},
        reasons={},
        engine_version="fixture-v1",
        seed=42,
        config={} if legacy else config,
        snapshot={} if legacy else snapshot,
    )
    store.create("backtest", metadata, run_id=run_id)
    store.save_result(run_id, result)


def test_normalizes_recorded_capital_and_preserves_raw_equity(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "small")
    _save(store, "large", cash=1000, values=(1000, 1100, 990))

    payload = compare_experiments(store, ["small", "large"])

    assert payload["ids"] == ["small", "large"]
    assert payload["equity"][0]["equity"] == [100, 110, 99]
    assert payload["equity"][1]["equity"] == [1000, 1100, 990]
    for series in payload["equity"]:
        assert series["normalized_equity"] == pytest.approx([1.0, 1.1, 0.99])
        assert series["drawdown"] == pytest.approx([0.0, 0.0, -0.1])
    assert payload["comparison"]["status"] == "different"
    assert {row["code"] for row in payload["comparison"]["warnings"]} == {"initial_cash"}


def test_first_observation_loss_is_not_normalized_away(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "loss", values=(90, 80, 100))
    _save(store, "other")

    series = compare_experiments(store, ["loss", "other"])["equity"][0]

    assert series["initial_cash"] == 100
    assert series["normalized_equity"] == pytest.approx([0.9, 0.8, 1.0])
    assert series["drawdown"] == pytest.approx([-0.1, -0.2, 0.0])


def test_matching_assumptions_allow_different_strategies(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "baseline")
    _save(store, "candidate", values=(100, 105, 103))
    store.update_metadata("candidate", {"strategy": {"template": "dual_ma", "params": {"fast": 5}}})

    payload = compare_experiments(store, ["baseline", "candidate"])

    assert payload["comparison"]["status"] == "matched"
    assert payload["comparison"]["warnings"] == []
    assert all(row["status"] == "matched" for row in payload["comparison"]["dimensions"])
    provenance = payload["equity"][1]["provenance"]
    assert provenance["template"] == "dual_ma"
    assert provenance["params"] == {"fast": 5}
    assert provenance["source"] == "SYNTHETIC"
    assert provenance["synthetic"] is True


def test_reports_data_dates_and_execution_mismatches(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "baseline")
    _save(
        store,
        "candidate",
        dates=(20240102, 20240104, 20240105),
        config_updates={"exec": {"type": "next_close", "slippage_bps": 10}},
        snapshot_updates={"content_hash": "other-fixture", "source": "LOCAL_FIXTURE"},
    )

    payload = compare_experiments(store, ["baseline", "candidate"])

    dimensions = {row["key"]: row for row in payload["comparison"]["dimensions"]}
    assert dimensions["data_hash"]["status"] == "different"
    assert dimensions["execution"]["status"] == "different"
    assert dimensions["dates"]["status"] == "different"
    assert dimensions["source"]["status"] == "different"
    assert payload["equity"][1]["dates"] == [20240102, 20240104, 20240105]


def test_same_endpoints_do_not_hide_different_trading_days(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "baseline", dates=(20240102, 20240103, 20240105))
    _save(store, "candidate", dates=(20240102, 20240104, 20240105))

    payload = compare_experiments(store, ["baseline", "candidate"])

    dimension = next(row for row in payload["comparison"]["dimensions"] if row["key"] == "dates")
    assert dimension["status"] == "different"


def test_legacy_missing_provenance_is_unknown_not_matching(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "legacy-a", legacy=True)
    _save(store, "legacy-b", legacy=True)

    payload = compare_experiments(store, ["legacy-a", "legacy-b"])

    assert payload["comparison"]["status"] == "unknown"
    assert payload["equity"][0]["normalized_equity"] is None
    assert payload["equity"][0]["initial_cash"] is None
    dimension = next(
        row for row in payload["comparison"]["dimensions"] if row["key"] == "data_hash"
    )
    assert dimension["status"] == "unknown"


def test_empty_equity_remains_explicit(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "empty", values=(), dates=())
    _save(store, "other")

    payload = compare_experiments(store, ["empty", "other"])

    assert payload["equity"][0]["normalized_equity"] == []
    assert payload["equity"][0]["drawdown"] == []
    assert (
        next(row for row in payload["comparison"]["dimensions"] if row["key"] == "dates")["status"]
        == "unknown"
    )


def test_provenance_uses_result_config_then_recorded_metadata(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    _save(store, "current")
    _save(store, "legacy", legacy=True)
    conflicting = BacktestConfig(initial_cash=1000).to_dict()
    store.update_metadata("current", {"config": conflicting})
    store.update_metadata("legacy", {"config": conflicting})

    series = compare_experiments(store, ["current", "legacy"])["equity"]

    assert series[0]["initial_cash"] == 100
    assert series[1]["initial_cash"] == 1000
    assert series[1]["normalized_equity"] == pytest.approx([0.1, 0.11, 0.099])


def test_api_keeps_old_contract_and_rejects_self_comparison(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    _save(store, "baseline")
    _save(store, "candidate")
    app = create_app(
        token="comparison-test-token",
        state_path=tmp_path / "state.sqlite",
        data_root=tmp_path / "data",
        snapshots_root=tmp_path / "snapshots",
        experiments_root=store.root,
        start_worker=False,
        serve_ui=False,
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.headers.update({"Authorization": "Bearer comparison-test-token"})
        response = client.get("/api/experiments/compare?ids=baseline,candidate")
        assert response.status_code == 200
        payload = response.json()
        assert set(payload["metrics"]) == {"baseline", "candidate"}
        assert payload["equity"][0]["equity"] == [100, 110, 99]
        assert payload["comparison"]["status"] == "matched"
        result = client.get("/api/experiments/baseline/result").json()
        assert result["config"]["initial_cash"] == 100
        assert result["snapshot"]["source"] == "SYNTHETIC"
        assert result["synthetic"] is True
        assert client.get("/api/experiments/compare?ids=baseline,baseline").status_code == 400
        assert client.get("/api/experiments/compare?ids=baseline,missing").status_code == 404
