"""Data-integrity audit for canonical panels (data health for UI/CLI).

Produces the dict contract consumed by GET /api/data/integrity and qc data integrity;
the shape mirrors ui/src/api/types.ts DataIntegrity. The audit is offline by default:
cross-source verification only runs when a callback is supplied, because the default test
suite and first-run UI must never touch the network.

Checks: coverage (list-date aware), gaps, OHLC self-consistency, volume/amount magnitude
consistency, price-limit consistency and adjustment continuity vs corporate actions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..calendar import to_date_int
from ..data.panel import PanelData

TOLERANCE = 0.011
MAX_GAP_EXAMPLES = 5
CrossSourceCheck = Callable[[PanelData, int], Mapping[str, Any]]
STATUS_RANK = {"pass": 0, "warn": 1, "fail": 2}


def _check(identifier: str, title: str, status: str, detail: str) -> dict[str, Any]:
    return {"id": identifier, "title": title, "status": status, "detail": detail}


def _ratio(count: int, total: int) -> float:
    return float(count) / float(total) if total else 0.0


def _snapshot_info(snapshot: Any, panel: PanelData) -> dict[str, Any] | None:
    """Normalise snapshot metadata into the DataIntegrity.snapshot contract."""
    if snapshot is None:
        return None
    payload: Mapping[str, Any]
    if isinstance(snapshot, Mapping):
        payload = snapshot
    elif hasattr(snapshot, "describe"):
        described = snapshot.describe()
        payload = described if isinstance(described, Mapping) else {}
    else:
        payload = {}
    dates = panel.calendar.dates
    first = int(dates[0]) if len(dates) else 0
    last = int(dates[-1]) if len(dates) else 0
    start_raw = payload.get("start")
    end_raw = payload.get("end")
    start = _as_date_int(start_raw) if start_raw is not None else first
    end = _as_date_int(end_raw) if end_raw is not None else last
    n_time_raw = payload.get("n_time")
    return {
        "id": str(payload.get("snapshot_id") or payload.get("id") or "unknown"),
        "synthetic": bool(payload.get("synthetic", panel.meta.get("synthetic", False))),
        "source": str(payload.get("source") or panel.meta.get("source") or "unknown"),
        "n_sec": int(payload.get("n_sec") or panel.n_sec),
        "n_time": int(n_time_raw or panel.n_time),
        "start": start,
        "end": end,
    }


def _as_date_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return to_date_int(value)
    except (TypeError, ValueError):
        return 0


def _coverage(
    panel: PanelData,
) -> tuple[dict[str, Any], dict[str, np.ndarray], list[dict[str, Any]], np.ndarray, np.ndarray]:
    """List-date-aware coverage, returning the contract dict and gap details.

    Expected cells are calendar days from a security's list date (and up to its delist
    date) to the panel end, so a staggered IPO schedule does not look like missing data.
    """
    dates = np.asarray(panel.calendar.dates, dtype=np.int64)
    securities = panel.securities.reset_index(drop=True)
    n_sec, n_time = len(securities), len(dates)
    empty_mask = np.zeros((n_sec, n_time), dtype=bool)
    if not n_sec or not n_time:
        coverage = {
            "expected_cells": 0,
            "present_cells": 0,
            "coverage_pct": 100.0,
            "symbols": 0,
            "trading_days": 0,
        }
        return coverage, {}, [], empty_mask, empty_mask
    sec_index = {str(sec): position for position, sec in enumerate(securities["sec_id"])}
    date_index = {int(day): position for position, day in enumerate(dates)}
    bars = panel.bars
    rows = bars["sec_id"].map(sec_index).to_numpy()
    columns = bars["date"].map(date_index).to_numpy()
    valid = ~(pd.isna(rows) | pd.isna(columns))
    present = np.zeros((n_sec, n_time), dtype=bool)
    present[rows[valid].astype(int), columns[valid].astype(int)] = True
    list_dates = securities["list_date"].to_numpy(dtype=np.int64)
    delist_dates = securities["delist_date"].to_numpy(dtype=np.int64)
    eligible = dates[None, :] >= list_dates[:, None]
    eligible &= (delist_dates[:, None] <= 0) | (dates[None, :] <= delist_dates[:, None])
    expected_per_sec = eligible.sum(axis=1)
    missing = eligible & ~present
    expected_cells = int(expected_per_sec.sum())
    present_cells = int((present & eligible).sum())
    examples: list[dict[str, Any]] = []
    for position in np.flatnonzero(missing.sum(axis=1) > 0):
        code = str(securities["code"].iloc[position])
        for day_position in np.flatnonzero(missing[position])[:MAX_GAP_EXAMPLES]:
            examples.append({"code": code, "date": int(dates[day_position])})
            if len(examples) >= MAX_GAP_EXAMPLES:
                break
        if len(examples) >= MAX_GAP_EXAMPLES:
            break
    coverage = {
        "expected_cells": expected_cells,
        "present_cells": present_cells,
        "coverage_pct": round(100.0 * _ratio(present_cells, expected_cells), 2),
        "symbols": int(n_sec),
        "trading_days": int(n_time),
    }
    masks = {"eligible": eligible, "present": present, "missing": missing}
    return coverage, masks, examples, present, missing


def _accuracy(bars: pd.DataFrame, actions: pd.DataFrame) -> dict[str, Any]:
    """Compute the accuracy counters shared by the checks and the accuracy contract."""
    counters = {
        "ohlc_violations": 0,
        "volume_amount_mismatch": 0,
        "limit_violations": 0,
        "adjustment_breaks": 0,
    }
    if bars.empty:
        return counters
    open_px = bars["open"].to_numpy(float)
    high = bars["high"].to_numpy(float)
    low = bars["low"].to_numpy(float)
    close = bars["close"].to_numpy(float)
    tolerance = TOLERANCE
    ohlc_bad = (high < low) | (high + tolerance < np.maximum(open_px, close))
    ohlc_bad |= low - tolerance > np.minimum(open_px, close)
    counters["ohlc_violations"] = int(ohlc_bad.sum())
    volume = bars["volume"].to_numpy(float)
    amount = bars["amount"].to_numpy(float)
    tradable = ~bars["suspended"].to_numpy(bool)
    bad_volume = (volume < 0) | (amount < 0)
    traded = tradable & (volume > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        average_price = np.where(volume > 0, amount / np.maximum(volume, 1.0), 0.0)
    mid = (high + low + close) / 3.0
    bad_amount = traded & (
        (amount <= 0) | (average_price < mid * 0.5) | (average_price > mid * 2.0)
    )
    counters["volume_amount_mismatch"] = int((bad_volume | bad_amount).sum())
    limit_up = bars["limit_up"].to_numpy(float)
    limit_down = bars["limit_down"].to_numpy(float)
    limit_bad = tradable & (
        (limit_up <= 0) | (limit_down <= 0) | (limit_up + tolerance < limit_down)
    )
    limit_bad |= tradable & ((close > limit_up + tolerance) | (close < limit_down - tolerance))
    counters["limit_violations"] = int(limit_bad.sum())
    return counters


def _adjustment_breaks(bars: pd.DataFrame, actions: pd.DataFrame) -> int:
    """Count close/pre_close jumps and factor changes not explained by a known action."""
    if bars.empty:
        return 0
    frame = bars.sort_values(["sec_id", "date"], kind="stable")
    ex_dates: set[tuple[str, int]] = set()
    if not actions.empty:
        ex_dates = {
            (str(sec), int(day))
            for sec, day in zip(actions["sec_id"], actions["ex_date"], strict=False)
        }
    sec_ids = frame["sec_id"].astype(str).to_numpy()
    dates = frame["date"].to_numpy(dtype=np.int64)
    pre_close = frame["pre_close"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    tradable = ~frame["suspended"].to_numpy(bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.where(pre_close > 0, close / pre_close - 1.0, 0.0)
    jump = (np.abs(np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)) > 0.55) & tradable
    jumps = int(
        sum(1 for pos in np.flatnonzero(jump) if (sec_ids[pos], int(dates[pos])) not in ex_dates)
    )
    factors = frame["adj_factor"].to_numpy(dtype=float)
    previous_sec = np.roll(sec_ids, 1)
    previous_factor = np.roll(factors, 1)
    same = sec_ids == previous_sec
    changed = same & (previous_factor > 0) & (np.abs(factors / previous_factor - 1.0) > 1e-4)
    factor_breaks = int(
        sum(1 for pos in np.flatnonzero(changed) if (sec_ids[pos], int(dates[pos])) not in ex_dates)
    )
    return jumps + factor_breaks


def _cross_source_result(
    callback: CrossSourceCheck | None, panel: PanelData, sample: int
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "checked": 0,
        "matched": 0,
        "max_rel_diff": None,
        "source": None,
        "note": "跨源抽样校验未启用(默认离线;传入 cross_source 回调可在具备网络时开启)",
    }
    if callback is None:
        return result
    try:
        payload = callback(panel, int(sample))
    except Exception as exc:  # a broken optional check must not fail the whole audit
        result["note"] = f"跨源校验失败: {exc}"
        return result
    checked = int(payload.get("checked") or 0)
    matched = int(payload.get("matched") or 0)
    max_rel = payload.get("max_rel_diff")
    source = payload.get("source")
    result.update(
        {
            "checked": checked,
            "matched": matched,
            "max_rel_diff": float(max_rel) if max_rel is not None else None,
            "source": str(source) if source else None,
        }
    )
    result["note"] = str(payload.get("note") or f"跨源抽样 {matched}/{checked} 匹配")
    return result


def _gap_detail(gaps: dict[str, Any], examples: list[dict[str, Any]]) -> str:
    if gaps["missing_days"] == 0:
        return "无缺失格:覆盖率按上市日计算,全部应有交易日均有行情"
    sample = ", ".join(f"{item['code']}@{item['date']}" for item in examples[:3])
    suffix = f";例如 {sample}" if sample else ""
    return f"{gaps['missing_days']} 个缺失格,涉及 {gaps['symbols_with_gaps']} 个标的{suffix}"


def audit_panel(
    panel: PanelData,
    *,
    snapshot: Any = None,
    sample: int = 2000,
    cross_source: CrossSourceCheck | None = None,
) -> dict[str, Any]:
    """Run the full integrity audit and return the DataIntegrity-shaped dict.

    Args:
        panel: canonical panel to audit.
        snapshot: snapshot metadata (mapping or object with describe()); None yields null.
        sample: max cross-source sample size (and cap on reported examples).
        cross_source: optional callable(panel, sample) returning checked/matched/... ; the
            default is fully offline.
    """
    bars = panel.bars
    actions = panel.corporate_actions
    coverage, _masks, examples, _, missing_mask = _coverage(panel)
    accuracy = _accuracy(bars, actions)
    accuracy["adjustment_breaks"] = _adjustment_breaks(bars, actions)
    expected_cells = int(coverage["expected_cells"])
    present_cells = int(coverage["present_cells"])
    missing_days = max(0, expected_cells - present_cells)
    missing_ratio = _ratio(missing_days, expected_cells)
    gap_data = {
        "missing_days": missing_days,
        "symbols_with_gaps": int((missing_mask.sum(axis=1) > 0).sum()) if missing_days else 0,
        "examples": examples,
    }
    rows = max(0, len(bars))
    checks = [
        _check(
            "coverage",
            "数据覆盖率",
            "pass"
            if coverage["coverage_pct"] >= 99.5
            else ("warn" if coverage["coverage_pct"] >= 95.0 else "fail"),
            f"覆盖 {coverage['coverage_pct']:.2f}%({present_cells}/{expected_cells} 格);"
            f"{coverage['symbols']} 个标的、{coverage['trading_days']} 个交易日(按上市日计)",
        ),
        _check(
            "gaps",
            "缺口与停牌",
            "pass" if missing_days == 0 else ("warn" if missing_ratio <= 0.01 else "fail"),
            _gap_detail(gap_data, examples),
        ),
        _check(
            "ohlc",
            "OHLC 自洽",
            "pass" if accuracy["ohlc_violations"] == 0 else "fail",
            f"{accuracy['ohlc_violations']} 行违反 low<=open/close<=high(共 {rows} 行)",
        ),
        _check(
            "volume_amount",
            "成交量与成交额",
            "pass"
            if accuracy["volume_amount_mismatch"] == 0
            else ("warn" if _ratio(accuracy["volume_amount_mismatch"], rows) <= 0.002 else "fail"),
            f"{accuracy['volume_amount_mismatch']} 行 volume/amount 量级不一致或为负",
        ),
        _check(
            "limits",
            "涨跌停一致性",
            "pass"
            if accuracy["limit_violations"] == 0
            else ("warn" if _ratio(accuracy["limit_violations"], rows) <= 0.005 else "fail"),
            f"{accuracy['limit_violations']} 行收盘价超出涨跌停或涨跌停缺失",
        ),
        _check(
            "adjustment",
            "复权连续性",
            "pass" if accuracy["adjustment_breaks"] == 0 else "warn",
            f"{accuracy['adjustment_breaks']} 处价格/因子断点未对应公司行为",
        ),
    ]
    cross = _cross_source_result(cross_source, panel, sample)
    if cross_source is None:
        cross_status, cross_detail = "pass", cross["note"]
    else:
        checked = cross["checked"]
        if checked == 0:
            cross_status, cross_detail = "warn", cross["note"]
        else:
            matched_ratio = _ratio(cross["matched"], checked)
            cross_status = (
                "pass" if matched_ratio >= 0.95 else ("warn" if matched_ratio >= 0.8 else "fail")
            )
            cross_detail = (
                f"{cross['matched']}/{checked} 个抽样一致,最大相对误差 {cross['max_rel_diff']}"
            )
    checks.append(_check("cross_source", "跨源抽样校验", cross_status, cross_detail))
    status = "pass"
    for item in checks:
        if STATUS_RANK[item["status"]] > STATUS_RANK[status]:
            status = item["status"]
    overall = {"pass": "ok", "warn": "warn", "fail": "fail"}[status]
    info = _snapshot_info(snapshot, panel)
    synthetic = bool(panel.meta.get("synthetic", False))
    note_parts = [
        (
            "SYNTHETIC 合成数据:仅用于流程演示与测试,不代表任何真实市场表现。"
            if synthetic
            else "数据来源:"
            + str(panel.meta.get("source") or panel.meta.get("provider") or "unknown")
            + ";研究结果仍需自行核实。"
        ),
        "历史表现不代表未来,不构成投资建议。",
    ]
    return {
        "status": overall,
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot": info,
        "coverage": coverage,
        "checks": checks,
        "gaps": gap_data,
        "accuracy": {
            "ohlc_violations": int(accuracy["ohlc_violations"]),
            "volume_amount_mismatch": int(accuracy["volume_amount_mismatch"]),
            "limit_violations": int(accuracy["limit_violations"]),
            "adjustment_breaks": int(accuracy["adjustment_breaks"]),
        },
        "cross_source": cross,
        "note": " ".join(note_parts),
    }
