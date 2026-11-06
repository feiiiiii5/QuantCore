"""Fixed candidate studies exercise the real native engine on labelled fabricated data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from quantcore.data.store import ParquetStore
from quantcore.errors import ExperimentError
from quantcore.experiments import ExperimentStore
from quantcore.research.candidates import (
    BASELINE,
    candidate_specs,
    replay_candidate_run,
    run_candidate_study,
)


@pytest.fixture(scope="module")
def panel() -> PanelData:
    # Weekdays including fabricated holiday treatment: explicitly NOT real market data.
    dates = pd.bdate_range("2019-01-02", "2024-12-31").strftime("%Y%m%d").astype(int).tolist()
    frames = []
    securities = []
    t = np.arange(len(dates), dtype=float)
    for index in range(4):
        sec = f"TEST{index}"
        close = (10 + index) * np.exp(0.0003 * t) * (1 + 0.002 * np.sin(t / 7 + index))
        previous = np.r_[close[0], close[:-1]]
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "sec_id": sec,
                    "code": f"60000{index}",
                    "open": close,
                    "high": close * 1.005,
                    "low": close * 0.995,
                    "close": close,
                    "pre_close": previous,
                    "volume": 1000000,
                    "amount": close * 1000000,
                    "adj_factor": 1.0,
                    "limit_up": np.round(previous * 1.1, 2),
                    "limit_down": np.round(previous * 0.9, 2),
                    "source": "SYNTHETIC",
                }
            )
        )
        securities.append(
            {
                "sec_id": sec,
                "code": f"60000{index}",
                "name": sec,
                "exchange": "SH",
                "board": "MAIN",
                "list_date": 20000101,
                "source": "SYNTHETIC",
            }
        )
    return PanelData(
        TradingCalendar.from_dates(dates),
        pd.DataFrame(securities),
        pd.concat(frames, ignore_index=True),
        meta={
            "source": "SYNTHETIC",
            "synthetic": True,
            "disclaimer": "Fabricated software-check fixture, not profitability evidence.",
        },
    )


@pytest.fixture(scope="module")
def study(panel, tmp_path_factory):
    root = tmp_path_factory.mktemp("candidate-study")
    result = run_candidate_study(panel, root, annual_holdout=True)
    return root, result


def test_fixed_specs_windows_cost_pairs_and_native_results(panel, study) -> None:
    root, result = study
    assert len(result["results"]) == 32
    assert {row["phase"] for row in result["results"]} == {
        "development",
        "holdout",
        "holdout_2023",
        "holdout_2024",
    }
    assert all(spec.params["top_n"] == 3 for spec in candidate_specs())
    assert candidate_specs()[0].params == {
        "lookback": 252,
        "skip": 21,
        "trend_window": 200,
        "top_n": 3,
        "rebalance": "monthly",
    }
    store = ExperimentStore(root / "experiments")
    for phase in result["phase_definitions"]:
        for candidate in [spec.name for spec in candidate_specs()] + [BASELINE]:
            pair = [
                row
                for row in result["results"]
                if row["phase"] == phase["name"] and row["candidate"] == candidate
            ]
            base, stress = (store.get(row["run_id"]) for row in pair)
            assert base.metadata["signals"] == stress.metadata["signals"]
            assert base.metadata["signal_hash"] == stress.metadata["signal_hash"]
            assert base.metadata["config"]["exec"]["slippage_bps"] == 5
            assert stress.metadata["config"]["exec"]["slippage_bps"] == 10
            for field in (
                "commission_rate",
                "min_commission",
                "stamp_duty_rate",
                "transfer_fee_rate",
                "exchange_fee_rate",
                "reg_fee_rate",
            ):
                assert (
                    stress.metadata["config"]["costs"][field]
                    == 2 * base.metadata["config"]["costs"][field]
                )
            for record in (base, stress):
                saved = store.load_result(record.run_id)
                assert saved.engine_backend == "cpp"
                assert saved.cash[0] == saved.equity[0] == 1000000 * 10000
                assert saved.market_value[0] == 0
                assert saved.dates[0] == phase["start"]
            if candidate == BASELINE:
                assert pair[0]["trade_count"] > 0
                assert pair[0]["excess_equal_weight"] == 0
                weights = np.load(base.directory / base.metadata["signals"])
                assert np.flatnonzero(np.isfinite(weights).any(axis=1)).tolist() == [
                    panel.calendar.index_of(phase["start"])
                ]
    # Full pre-2021 history lets the 252-day candidate trade at its first phase rebalance.
    weights = np.load(root / "signals/trend_momentum.npy")
    assert np.nansum(weights[panel.calendar.index_of(20210101)]) == pytest.approx(1)


def test_shared_data_replay_and_honest_labels(study) -> None:
    root, result = study
    assert len(list((root / "data").glob("*.parquet"))) == 5
    store = ExperimentStore(root / "experiments")
    for candidate in (BASELINE, "trend_momentum"):
        row = next(
            row
            for row in result["results"]
            if row["phase"] == "holdout" and row["candidate"] == candidate
        )
        record = store.get(row["run_id"])
        assert not (record.directory / "panel").exists()
        assert (record.directory / "strategy.yaml").is_file()
        assert replay_candidate_run(store, record.run_id).matched
    assert result["data"]["synthetic"] is True
    assert "SYNTHETIC" in (root / "report.md").read_text()
    assert "cannot support investment conclusions" in (root / "report.md").read_text()
    assert (root / "results.csv").is_file()
    assert len(json.loads((root / "phases/holdout.json").read_text())) == 8


def test_replay_compares_saved_metrics_and_rejects_changed_signals(study) -> None:
    root, result = study
    store = ExperimentStore(root / "experiments")
    row = next(
        row
        for row in result["results"]
        if row["phase"] == "holdout" and row["candidate"] == BASELINE
    )
    record = store.get(row["run_id"])
    saved = store.load_result(record.run_id)
    original_return = saved.metrics["total_return"]
    try:
        saved.metrics["total_return"] += 0.01
        store.save_result(record.run_id, saved)
        replayed = replay_candidate_run(store, record.run_id)
        assert not replayed.matched and not replayed.metrics_match
        assert replayed.equity_match and replayed.trades_match
    finally:
        saved.metrics["total_return"] = original_return
        store.save_result(record.run_id, saved)
    path = record.directory / record.metadata["signals"]
    original = np.load(path, allow_pickle=False)
    try:
        changed = original.copy()
        changed[0] = 0
        np.save(path, changed, allow_pickle=False)
        with pytest.raises(ExperimentError, match="signal hash changed"):
            replay_candidate_run(store, record.run_id)
    finally:
        np.save(path, original, allow_pickle=False)


@pytest.mark.parametrize("custom_dates", [False, True])
def test_cli_reads_local_warehouse_and_uses_one_data_copy(panel, tmp_path, custom_dates) -> None:
    store = ParquetStore(tmp_path / "input/warehouse")
    store.write_panel(panel)
    output = tmp_path / "study"
    script = Path(__file__).resolve().parents[1] / "scripts/research_candidates.py"
    args = [
        sys.executable,
        str(script),
        "--data-root",
        str(store.root.parent),
        "--output",
        str(output),
    ]
    if custom_dates:
        args.extend(["--development-start", "20230403", "--holdout-start", "20240101"])
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["synthetic"] is True and receipt["runs"] == 16
    assert len(list((output / "data").glob("*.parquet"))) == 5
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["development_start"] == (20230403 if custom_dates else 20210101)
    assert protocol["holdout_start"] == (20240101 if custom_dates else 20230101)


def test_custom_split_clips_annual_window_and_keeps_parameters_fixed(panel, tmp_path) -> None:
    study = run_candidate_study(
        panel,
        tmp_path / "custom",
        development_start=20230403,
        holdout_start="2024-07-01",
        annual_holdout=True,
    )
    assert study["date_protocol"] == {"development_start": 20230403, "holdout_start": 20240701}
    phases = {phase["name"]: phase for phase in study["phase_definitions"]}
    assert phases["development"]["end"] < 20240701
    assert phases["holdout"]["start"] == phases["holdout_2024"]["start"] == 20240701
    assert phases["development"]["warmup"]["sufficient"] is True
    assert study["candidate_specs"][:3] == [spec.to_dict() for spec in candidate_specs()]


def test_short_warmup_is_reported_without_backfilling(panel, tmp_path) -> None:
    short = panel.select(start=20231002)
    output = tmp_path / "short"
    study = run_candidate_study(short, output, development_start=20231101, holdout_start=20240101)
    warmup = study["phase_definitions"][0]["warmup"]
    assert not warmup["sufficient"]
    assert warmup["available_preceding_rows"] < 252
    assert all(count < 252 for count in warmup["valid_preceding_by_security"].values())
    assert "INSUFFICIENT" in (output / "report.md").read_text()
    assert study["data"]["first_date"] == 20231002


@pytest.mark.parametrize(
    "development,holdout", [(20240101, 20240101), (20250101, 20240101), (20241230, 20241231)]
)
def test_invalid_or_one_day_windows_are_rejected_before_results(
    panel, tmp_path, development, holdout
) -> None:
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match=r"before|at least two"):
        run_candidate_study(panel, output, development_start=development, holdout_start=holdout)
    assert not output.exists()
