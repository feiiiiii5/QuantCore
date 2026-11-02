"""Data-integrity audit tests: contract shape + real defect detection (offline)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pandas as pd
import pytest

from quantcore.data.integrity import audit_panel
from quantcore.data.panel import PanelData

CONTRACT_KEYS = {
    "status",
    "generated_at",
    "snapshot",
    "coverage",
    "checks",
    "gaps",
    "accuracy",
    "cross_source",
    "note",
}
CHECK_KEYS = {"id", "title", "status", "detail"}
CHECK_IDS = {"coverage", "gaps", "ohlc", "volume_amount", "limits", "adjustment", "cross_source"}
ACCURACY_KEYS = {
    "ohlc_violations",
    "volume_amount_mismatch",
    "limit_violations",
    "adjustment_breaks",
}
CROSS_KEYS = {"checked", "matched", "max_rel_diff", "source", "note"}


def snapshot_meta(panel: PanelData) -> dict[str, Any]:
    return {
        "snapshot_id": "snap_integrity_test",
        "synthetic": True,
        "source": "SYNTHETIC",
        "n_sec": panel.n_sec,
        "n_time": panel.n_time,
        "start": "2022-01-04",
        "end": "2024-12-31",
    }


def corrupt_panel(panel: PanelData, mutate: Any) -> PanelData:
    bars = panel.bars.copy()
    mutate(bars)
    broken = copy.copy(panel)
    broken.bars = bars.reset_index(drop=True)
    return broken


def test_contract_shape_and_clean_synthetic_panel(small_panel: PanelData) -> None:
    result = audit_panel(small_panel, snapshot=snapshot_meta(small_panel))
    assert set(result) == CONTRACT_KEYS
    assert result["status"] == "ok"
    assert isinstance(result["generated_at"], str) and result["generated_at"]
    snapshot = result["snapshot"]
    assert snapshot is not None
    assert snapshot["id"] == "snap_integrity_test"
    assert snapshot["synthetic"] is True
    assert snapshot["source"] == "SYNTHETIC"
    assert snapshot["start"] == 20220104  # ISO string normalised to YYYYMMDD int
    assert snapshot["end"] == 20241231
    coverage = result["coverage"]
    assert set(coverage) == {
        "expected_cells",
        "present_cells",
        "coverage_pct",
        "symbols",
        "trading_days",
    }
    assert coverage["symbols"] == small_panel.n_sec
    assert coverage["trading_days"] == small_panel.n_time
    assert coverage["expected_cells"] > 0
    assert coverage["present_cells"] == coverage["expected_cells"]
    assert coverage["coverage_pct"] == pytest.approx(100.0)
    assert set(result["checks"][0]) == CHECK_KEYS
    assert {item["id"] for item in result["checks"]} == CHECK_IDS
    assert all(item["status"] in {"pass", "warn", "fail"} for item in result["checks"])
    gaps = result["gaps"]
    assert set(gaps) == {"missing_days", "symbols_with_gaps", "examples"}
    assert gaps["missing_days"] == 0 and gaps["symbols_with_gaps"] == 0
    accuracy = result["accuracy"]
    assert set(accuracy) == ACCURACY_KEYS
    assert all(value == 0 for value in accuracy.values())
    cross = result["cross_source"]
    assert set(cross) == CROSS_KEYS
    assert cross["checked"] == 0 and cross["max_rel_diff"] is None
    assert "未启用" in cross["note"]
    assert "SYNTHETIC" in result["note"]
    assert "不构成投资建议" in result["note"]


def test_snapshot_none_still_returns_contract(small_panel: PanelData) -> None:
    result = audit_panel(small_panel)
    assert result["snapshot"] is None
    assert set(result) == CONTRACT_KEYS


def test_gap_detection(small_panel: PanelData) -> None:
    first = small_panel.securities.iloc[0]
    first_sec = str(first["sec_id"])
    first_code = str(first["code"])
    security_dates = sorted(
        small_panel.bars.loc[small_panel.bars["sec_id"] == first_sec, "date"].tolist()
    )
    dropped = security_dates[10:16]

    def mutate(bars: pd.DataFrame) -> None:
        keep = ~((bars["sec_id"] == first_sec) & (bars["date"].isin(dropped)))
        bars.drop(index=bars.index[~keep], inplace=True)

    result = audit_panel(corrupt_panel(small_panel, mutate))
    assert result["gaps"]["missing_days"] == 6
    assert result["gaps"]["symbols_with_gaps"] == 1
    assert {item["code"] for item in result["gaps"]["examples"]} == {first_code}
    assert {item["date"] for item in result["gaps"]["examples"]} <= set(dropped)
    gaps_check = next(item for item in result["checks"] if item["id"] == "gaps")
    assert gaps_check["status"] == "warn"
    assert result["status"] == "warn"


def test_ohlc_violation_detection(small_panel: PanelData) -> None:
    def mutate(bars: pd.DataFrame) -> None:
        bars.loc[0, "high"] = float(bars.loc[0, "low"]) - 1.0
        bars.loc[1, "low"] = float(bars.loc[1, "high"]) + 1.0

    result = audit_panel(corrupt_panel(small_panel, mutate))
    assert result["accuracy"]["ohlc_violations"] >= 2
    ohlc = next(item for item in result["checks"] if item["id"] == "ohlc")
    assert ohlc["status"] == "fail"
    assert result["status"] == "fail"


def test_limit_violation_detection(small_panel: PanelData) -> None:
    def mutate(bars: pd.DataFrame) -> None:
        tradable = bars.index[~bars["suspended"].astype(bool)]
        row = int(tradable[5])
        bars.loc[row, "limit_up"] = float(bars.loc[row, "close"]) * 0.5

    result = audit_panel(corrupt_panel(small_panel, mutate))
    assert result["accuracy"]["limit_violations"] >= 1
    limits = next(item for item in result["checks"] if item["id"] == "limits")
    assert limits["status"] == "warn"


def test_volume_amount_mismatch_detection(small_panel: PanelData) -> None:
    def mutate(bars: pd.DataFrame) -> None:
        for row in (10, 11):
            bars.loc[row, "amount"] = (
                float(bars.loc[row, "volume"]) * float(bars.loc[row, "close"]) * 1000.0
            )

    result = audit_panel(corrupt_panel(small_panel, mutate))
    assert result["accuracy"]["volume_amount_mismatch"] >= 2
    volume = next(item for item in result["checks"] if item["id"] == "volume_amount")
    assert volume["status"] in {"warn", "fail"}


def test_adjustment_break_detection(small_panel: PanelData) -> None:
    def mutate(bars: pd.DataFrame) -> None:
        for row in (20, 21):
            bars.loc[row, "pre_close"] = float(bars.loc[row, "close"]) / 2.0

    result = audit_panel(corrupt_panel(small_panel, mutate))
    assert result["accuracy"]["adjustment_breaks"] >= 2
    adjustment = next(item for item in result["checks"] if item["id"] == "adjustment")
    assert adjustment["status"] == "warn"


def test_cross_source_callback_is_used_and_merged(small_panel: PanelData) -> None:
    seen: dict[str, int] = {}

    def check(panel: PanelData, sample: int) -> dict[str, Any]:
        seen["sample"] = sample
        assert panel is small_panel
        return {
            "checked": 8,
            "matched": 8,
            "max_rel_diff": 0.0012,
            "source": "recorded-fixture",
            "note": "cross-check ok",
        }

    result = audit_panel(
        small_panel, snapshot=snapshot_meta(small_panel), sample=7, cross_source=check
    )
    assert seen["sample"] == 7
    cross = result["cross_source"]
    assert cross["checked"] == 8 and cross["matched"] == 8
    assert cross["max_rel_diff"] == pytest.approx(0.0012)
    assert cross["source"] == "recorded-fixture"
    check_row = next(item for item in result["checks"] if item["id"] == "cross_source")
    assert check_row["status"] == "pass"


def test_cross_source_failure_degrades_to_warning(small_panel: PanelData) -> None:
    def broken(panel: PanelData, sample: int) -> dict[str, Any]:
        raise RuntimeError("network disabled")

    result = audit_panel(small_panel, cross_source=broken)
    assert result["cross_source"]["checked"] == 0
    assert "失败" in result["cross_source"]["note"]
    assert result["status"] == "warn"


def test_empty_bars_panel_is_reported_not_crash(small_panel: PanelData) -> None:
    broken = copy.copy(small_panel)
    broken.bars = small_panel.bars.iloc[0:0].copy()
    result = audit_panel(broken, snapshot=snapshot_meta(small_panel))
    assert set(result) == CONTRACT_KEYS
    assert result["coverage"]["present_cells"] == 0
    assert result["status"] == "fail"
    json.dumps(result, allow_nan=False, ensure_ascii=False)


def test_quarantine_turns_row_level_errors_into_warnings(small_panel: PanelData) -> None:
    """A handful of vendor-glitch bars should be quarantined with a warning, not abort the
    import: real public feeds occasionally carry a bad OHLC/limit row."""
    from quantcore.quality.checks import quarantine_bad_rows

    broken = copy.copy(small_panel)
    bars = small_panel.bars.copy()
    index = bars.index[0]
    limit_up = float(bars.loc[index, "limit_up"])
    bars.loc[index, ["open", "high", "close"]] = limit_up * 2.0
    bars.loc[index, "low"] = limit_up * 0.5
    broken.bars = bars
    result = quarantine_bad_rows(broken)
    assert result.dropped >= 1
    payload = result.report.to_dict()
    assert payload["passed"] is True
    assert any(issue["check"] == "quarantined_rows" for issue in payload["issues"])
    assert len(result.clean.bars) == len(small_panel.bars) - result.dropped
