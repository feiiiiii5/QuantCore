"""Data-quality checks and bad-row quarantine for canonical panels.

Every check produces a :class:`CheckIssue` with a severity; row-level failures also
return a boolean mask so ingestion can quarantine bad rows instead of silently keeping
them.  The rules are calibrated for the canonical schema in
:mod:`quantcore.data.panel` and are exercised by SYNTHETIC panels in tests.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

from ..data.panel import PanelData
from .report import ERROR, WARNING, CheckIssue, QualityReport, QuarantineResult

TOLERANCE = 0.011  # half a cent of rounding slack
ST_LIMIT_CHANGE_DATE = 20260706
PRICE_LIMITS: dict[int, dict[str, float]] = {
    0: {"normal": 0.10, "st": 0.05},
    1: {"normal": 0.20, "st": 0.20},
    2: {"normal": 0.20, "st": 0.20},
    3: {"normal": 0.30, "st": 0.30},
}


def _sample(
    frame: pd.DataFrame, mask: np.ndarray | pd.Series, columns: list[str], n: int = 5
) -> tuple[dict, ...]:
    selected = frame.loc[np.asarray(mask, dtype=bool), columns].head(n)
    return tuple(record for record in selected.to_dict(orient="records"))


def _check_schema(panel: PanelData, report: QualityReport) -> None:
    problems = panel.schema_problems()
    if problems:
        report.add(CheckIssue("schema", ERROR, f"schema violations: {problems}", len(problems)))


def _check_duplicates(panel: PanelData, report: QualityReport) -> tuple[pd.DataFrame, np.ndarray]:
    bars = panel.bars
    if bars.empty:
        return bars, np.zeros(len(bars), dtype=bool)
    duplicated = bars.duplicated(subset=["date", "sec_id"], keep="first").to_numpy()
    if duplicated.any():
        report.add(
            CheckIssue(
                "duplicates",
                ERROR,
                f"{int(duplicated.sum())} duplicated (date, sec_id) rows",
                int(duplicated.sum()),
                _sample(bars, duplicated, ["date", "sec_id", "close"]),
            )
        )
    return bars, duplicated


def _check_required_values(panel: PanelData, report: QualityReport) -> np.ndarray:
    bars = panel.bars
    required = ["open", "high", "low", "close", "pre_close", "volume", "amount", "adj_factor"]
    missing = np.zeros(len(bars), dtype=bool)
    if bars.empty:
        return missing
    for column in required:
        values = bars[column].to_numpy()
        column_missing = pd.isna(values) | np.isinf(values.astype(float))
        missing |= column_missing
    if missing.any():
        report.add(
            CheckIssue(
                "missing_values",
                ERROR,
                f"{int(missing.sum())} bars missing required values",
                int(missing.sum()),
                _sample(bars, missing, ["date", "sec_id", *required]),
            )
        )
    return missing


def _check_price_consistency(panel: PanelData, report: QualityReport) -> np.ndarray:
    bars = panel.bars
    bad = np.zeros(len(bars), dtype=bool)
    if bars.empty:
        return bad
    open_px = bars["open"].to_numpy(float)
    high = bars["high"].to_numpy(float)
    low = bars["low"].to_numpy(float)
    close = bars["close"].to_numpy(float)
    bad |= (open_px <= 0) | (high <= 0) | (low <= 0) | (close <= 0)
    bad |= high < low
    bad |= (high + TOLERANCE) < np.maximum(open_px, close)
    bad |= (low - TOLERANCE) > np.minimum(open_px, close)
    limit_up = bars["limit_up"].to_numpy(float)
    limit_down = bars["limit_down"].to_numpy(float)
    tradable = ~bars["suspended"].to_numpy(bool)
    bad |= tradable & ((limit_up <= 0) | (limit_down <= 0))
    bad |= tradable & (limit_up + TOLERANCE < limit_down)
    bad |= tradable & ((close > limit_up + TOLERANCE) | (close < limit_down - TOLERANCE))
    bad |= (bars["volume"].to_numpy() < 0) | (bars["amount"].to_numpy() < 0)
    if bad.any():
        report.add(
            CheckIssue(
                "price_consistency",
                ERROR,
                f"{int(bad.sum())} bars violate OHLC/limit/price constraints",
                int(bad.sum()),
                _sample(
                    bars,
                    bad,
                    ["date", "sec_id", "open", "high", "low", "close", "limit_up", "limit_down"],
                ),
            )
        )
    return bad


def _check_units(panel: PanelData, report: QualityReport) -> np.ndarray:
    bars = panel.bars
    bad = np.zeros(len(bars), dtype=bool)
    if bars.empty:
        return bad
    close = bars["close"].to_numpy(float)
    volume = bars["volume"].to_numpy(float)
    amount = bars["amount"].to_numpy(float)
    low = bars["low"].to_numpy(float)
    high = bars["high"].to_numpy(float)
    turnover = bars["turnover"].to_numpy(float)
    shares = bars["float_shares"].to_numpy(float)
    tradable = ~bars["suspended"].to_numpy(bool)
    locked = (high - low) <= TOLERANCE  # one-line board: no intraday range, no trades
    bad |= (close > 100000.0) | (close < 0.001)
    bad |= tradable & ~locked & (volume <= 0)
    impossible_amount = (
        tradable & (volume > 0) & ((amount > volume * high * 1.05) | (amount < volume * low * 0.95))
    )
    bad |= impossible_amount
    bad |= (~np.isnan(turnover)) & ((turnover < 0) | (turnover > 10.0))
    derived_turnover = np.divide(volume, shares, out=np.zeros_like(volume), where=shares > 0)
    mismatch = tradable & (shares > 0) & (np.abs(turnover - derived_turnover) > 0.02)
    if np.any(impossible_amount):
        report.add(
            CheckIssue(
                "units",
                WARNING,
                f"{int(impossible_amount.sum())} bars have amount inconsistent with volume*price "
                "(possible unit error)",
                int(impossible_amount.sum()),
                _sample(
                    bars, impossible_amount, ["date", "sec_id", "volume", "amount", "low", "high"]
                ),
            )
        )
    if np.any(mismatch):
        report.add(
            CheckIssue(
                "turnover_units",
                WARNING,
                f"{int(mismatch.sum())} bars have turnover inconsistent with volume/float_shares",
                int(mismatch.sum()),
                _sample(bars, mismatch, ["date", "sec_id", "turnover", "volume", "float_shares"]),
            )
        )
    if bad.any():
        report.add(
            CheckIssue(
                "unit_ranges",
                ERROR,
                f"{int(bad.sum())} bars have out-of-range values (price/shares/amount)",
                int(bad.sum()),
                _sample(bars, bad, ["date", "sec_id", "close", "volume", "amount", "turnover"]),
            )
        )
    return bad


def _check_adjustment(panel: PanelData, report: QualityReport) -> None:
    bars = panel.bars
    if bars.empty:
        return
    adjusted = bars.copy()
    first_factor = adjusted.groupby("sec_id")["adj_factor"].transform("first")
    adjusted["adj_close"] = (
        adjusted["close"] * adjusted["adj_factor"] / first_factor.replace(0, np.nan)
    )
    ex_dates = (
        set(
            zip(panel.corporate_actions["sec_id"], panel.corporate_actions["ex_date"], strict=False)
        )
        if not panel.corporate_actions.empty
        else set()
    )
    for sec_id, group in adjusted.groupby("sec_id", sort=False):
        group = group.sort_values("date")
        returns = group["adj_close"].pct_change()
        date_values = group["date"].to_numpy()
        factor_values = group["adj_factor"].to_numpy(float)
        if np.any(np.diff(factor_values) < -1e-9):
            report.add(
                CheckIssue(
                    "adj_factor_monotonic",
                    WARNING,
                    f"adj_factor decreases for {sec_id}",
                    1,
                    ({"sec_id": sec_id},),
                )
            )
        extreme = returns.to_numpy(float)
        mask = np.abs(np.nan_to_num(extreme, nan=0.0)) > 0.55
        for position in np.flatnonzero(mask):
            day = int(date_values[position])
            if (sec_id, day) in ex_dates:
                continue
            if abs(extreme[position]) > 0.55:
                report.add(
                    CheckIssue(
                        "adj_return_jump",
                        ERROR,
                        f"adjusted return {extreme[position]:.3f} for {sec_id} on {day}",
                        1,
                        ({"sec_id": sec_id, "date": day, "return": float(extreme[position])},),
                    )
                )
                break


def _check_limits(panel: PanelData, report: QualityReport) -> None:
    bars = panel.bars
    if bars.empty:
        return
    board_names = dict(zip(panel.securities["sec_id"], panel.securities["board"], strict=False))
    board_index = {
        str(sec): {"MAIN": 0, "GEM": 1, "STAR": 2, "BSE": 3}.get(str(name), 0)
        for sec, name in board_names.items()
    }
    st = bars["st"].to_numpy(bool)
    dates = bars["date"].to_numpy(int)
    board_ids = bars["sec_id"].map(board_index).fillna(0).to_numpy(int)
    expected = np.empty(len(bars), dtype=float)
    for row, (board, is_st, day) in enumerate(zip(board_ids, st, dates, strict=False)):
        limits = PRICE_LIMITS[int(board)]
        if is_st and int(board) == 0:
            expected[row] = limits["st"] if day < ST_LIMIT_CHANGE_DATE else limits["normal"]
        else:
            expected[row] = limits["normal"]
    pre_close = bars["pre_close"].to_numpy(float)
    limit_up = bars["limit_up"].to_numpy(float)
    limit_down = bars["limit_down"].to_numpy(float)
    tradable = ~bars["suspended"].to_numpy(bool)
    up_error = tradable & (
        np.abs(limit_up - np.round(pre_close * (1.0 + expected), 2)) > TOLERANCE + 0.01
    )
    down_error = tradable & (
        np.abs(limit_down - np.round(pre_close * (1.0 - expected), 2)) > TOLERANCE + 0.01
    )
    bad = up_error | down_error
    if bad.any():
        report.add(
            CheckIssue(
                "limit_consistency",
                ERROR,
                f"{int(bad.sum())} bars have limit prices inconsistent with the board/ST rule set",
                int(bad.sum()),
                _sample(
                    bars,
                    bad,
                    ["date", "sec_id", "pre_close", "limit_up", "limit_down", "st"],
                ),
            )
        )


def _check_suspension(panel: PanelData, report: QualityReport) -> np.ndarray:
    bars = panel.bars
    bad = np.zeros(len(bars), dtype=bool)
    if bars.empty:
        return bad
    suspended = bars["suspended"].to_numpy(bool)
    if suspended.any():
        same = (
            np.abs(bars["close"].to_numpy(float) - bars["pre_close"].to_numpy(float)) <= TOLERANCE
        )
        no_trades = bars["volume"].to_numpy() == 0
        bad = suspended & ~(same & no_trades)
        if bad.any():
            report.add(
                CheckIssue(
                    "suspension",
                    ERROR,
                    f"{int(bad.sum())} suspended bars have prices/volume inconsistent with a suspension",
                    int(bad.sum()),
                    _sample(bars, bad, ["date", "sec_id", "close", "pre_close", "volume"]),
                )
            )
    return bad


def _check_reference(panel: PanelData, report: QualityReport) -> None:
    bars = panel.bars
    if bars.empty:
        return
    actions = panel.corporate_actions
    if actions.empty:
        return
    merged = bars.copy()
    merged["prev_close"] = merged.groupby("sec_id")["close"].shift(1)
    for action in actions.itertuples(index=False):
        matches = merged[(merged["sec_id"] == action.sec_id) & (merged["date"] == action.ex_date)]
        for row in matches.itertuples(index=False):
            prev = getattr(row, "prev_close", None)
            if prev is None or np.isnan(prev):
                continue
            expected = max(
                0.01,
                (float(cast(Any, prev)) - float(cast(Any, action.cash_per_share)))
                / float(cast(Any, action.split_ratio)),
            )
            if abs(float(cast(Any, row.pre_close)) - round(expected, 2)) > 2 * TOLERANCE:
                report.add(
                    CheckIssue(
                        "corporate_action_reference",
                        WARNING,
                        f"ex-date pre_close of {action.sec_id} on {action.ex_date} differs from the "
                        "adjusted reference",
                        1,
                        (
                            {
                                "sec_id": action.sec_id,
                                "ex_date": int(cast(Any, action.ex_date)),
                                "pre_close": float(cast(Any, row.pre_close)),
                                "expected": round(expected, 2),
                            },
                        ),
                    )
                )


def _check_pit(panel: PanelData, report: QualityReport) -> None:
    frame = panel.financials
    if frame.empty:
        return
    bad = (frame["ann_date"] < frame["end_date"]) | (frame["end_date"] <= 0)
    if bad.any():
        report.add(
            CheckIssue(
                "pit_announcement_order",
                ERROR,
                f"{int(bad.sum())} PIT financial rows announce before the reporting period ends",
                int(bad.sum()),
                tuple(
                    frame.loc[bad, ["sec_id", "end_date", "ann_date"]].head(5).to_dict("records")
                ),
            )
        )
    duplicated = frame.duplicated(
        subset=["sec_id", "end_date", "ann_date", "update_flag"], keep="first"
    )
    if duplicated.any():
        report.add(
            CheckIssue(
                "pit_duplicates",
                WARNING,
                f"{int(duplicated.sum())} duplicated PIT rows",
                int(duplicated.sum()),
                tuple(
                    frame.loc[duplicated, ["sec_id", "end_date", "ann_date"]]
                    .head(5)
                    .to_dict("records")
                ),
            )
        )
    if "sec_id" in frame.columns:
        unknown = set(frame["sec_id"]) - set(panel.securities["sec_id"])
        if unknown:
            report.add(
                CheckIssue(
                    "pit_unknown_sec",
                    ERROR,
                    f"PIT rows for unknown securities: {sorted(unknown)[:5]}",
                    len(unknown),
                )
            )


def _check_corporate_actions(panel: PanelData, report: QualityReport) -> None:
    frame = panel.corporate_actions
    if frame.empty:
        return
    bad = (
        (frame["ex_date"] < frame["ann_date"])
        | (frame["split_ratio"] <= 0)
        | (frame["cash_per_share"] < 0)
    )
    if bad.any():
        report.add(
            CheckIssue(
                "corporate_actions",
                ERROR,
                f"{int(bad.sum())} invalid corporate-action rows",
                int(bad.sum()),
                tuple(
                    frame.loc[bad, ["sec_id", "ex_date", "split_ratio", "cash_per_share"]]
                    .head(5)
                    .to_dict("records")
                ),
            )
        )


def _check_labeling(panel: PanelData, report: QualityReport) -> None:
    synthetic = bool(panel.meta.get("synthetic"))
    if synthetic:
        if not panel.meta.get("disclaimer"):
            report.add(
                CheckIssue("labeling", ERROR, "synthetic panel is missing its disclaimer", 1)
            )
        bars = panel.bars
        if (
            not bars.empty
            and "source" in bars.columns
            and not (bars["source"] == "SYNTHETIC").all()
        ):
            report.add(
                CheckIssue("labeling", ERROR, "synthetic bars must be labelled SYNTHETIC", 1)
            )


def _check_calendar(panel: PanelData, report: QualityReport) -> None:
    dates = list(panel.calendar.dates)
    if not dates:
        report.add(CheckIssue("calendar", ERROR, "empty trading calendar", 1))
        return
    if dates != sorted(set(dates)):
        report.add(CheckIssue("calendar", ERROR, "calendar dates not strictly increasing", 1))
    spanning = panel.bars[["date", "sec_id"]].copy()
    if not spanning.empty:
        outside = (spanning["date"] < dates[0]) | (spanning["date"] > dates[-1])
        if outside.any():
            report.add(
                CheckIssue(
                    "calendar", ERROR, "bars outside the calendar window", int(outside.sum())
                )
            )


def run_quality_checks(panel: PanelData, include_labeling: bool = True) -> QualityReport:
    """Run every quality check and return an aggregated report."""
    report = QualityReport(rows=len(panel.bars), synthetic=bool(panel.meta.get("synthetic")))
    _check_schema(panel, report)
    _check_calendar(panel, report)
    _check_duplicates(panel, report)
    _check_required_values(panel, report)
    _check_price_consistency(panel, report)
    _check_units(panel, report)
    _check_adjustment(panel, report)
    _check_limits(panel, report)
    _check_suspension(panel, report)
    _check_reference(panel, report)
    _check_pit(panel, report)
    _check_corporate_actions(panel, report)
    if include_labeling:
        _check_labeling(panel, report)
    return report


def quarantine_bad_rows(panel: PanelData) -> QuarantineResult:
    """Split row-level failures out of ``panel.bars`` and return a clean panel."""
    report = run_quality_checks(panel)
    bars = panel.bars
    if bars.empty:
        return QuarantineResult(clean=panel, bad_rows=bars.copy(), report=report, dropped=0)
    mask_report = QualityReport(rows=len(bars), synthetic=bool(panel.meta.get("synthetic")))
    bad = np.zeros(len(bars), dtype=bool)
    bad |= _check_required_values(panel, mask_report)
    bad |= _check_price_consistency(panel, mask_report)
    bad |= _check_units(panel, mask_report)
    bad |= _check_suspension(panel, mask_report)
    _, duplicated = _check_duplicates(panel, mask_report)
    bad |= duplicated
    bad_rows = bars.loc[bad].copy()
    clean = PanelData(
        calendar=panel.calendar,
        securities=panel.securities,
        bars=bars.loc[~bad].reset_index(drop=True),
        financials=panel.financials,
        corporate_actions=panel.corporate_actions,
        meta={**panel.meta, "quarantined_rows": int(bad.sum())},
    )
    return QuarantineResult(clean=clean, bad_rows=bad_rows, report=report, dropped=int(bad.sum()))
