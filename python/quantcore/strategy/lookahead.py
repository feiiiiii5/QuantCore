"""Future-function (lookahead) detection.

Two complementary checks:

1. **Dynamic truncation check** — regenerate targets on data truncated at several
   decision dates and require the weights at and before those dates to be unchanged.
   A strategy that peeks at future data (e.g. full-sample normalisation) fails.
2. **Static audit** — flag explicit negative shifts in custom strategy source
   (``series.shift(-1)``, ``iloc[-1]``-style future access) as suspicious.

The dynamic check is authoritative; the static audit is an early warning.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..data.panel import PanelData
from .base import Strategy


@dataclass(frozen=True)
class LookaheadMismatch:
    cut: int
    date: int
    rows: int
    max_abs_diff: float
    first_row: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cut_index": self.cut,
            "cut_date": self.date,
            "mismatched_rows": self.rows,
            "max_abs_diff": self.max_abs_diff,
            "first_mismatch_row": self.first_row,
        }


@dataclass
class LookaheadReport:
    strategy: str
    cuts: list[int] = field(default_factory=list)
    mismatches: list[LookaheadMismatch] = field(default_factory=list)
    static_issues: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and not self.mismatches and not self.static_issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "passed": self.passed,
            "cuts": self.cuts,
            "mismatches": [item.to_dict() for item in self.mismatches],
            "static_issues": list(self.static_issues),
            "error": self.error,
        }


def default_cut_indices(n_time: int, n_cuts: int = 5) -> list[int]:
    """Decision indices spread across the middle of the sample."""
    if n_time < 8:
        raise ValueError("lookahead check needs at least 8 bars")
    lo = max(1, n_time // 3)
    hi = max(lo + 1, n_time - 2)
    points = np.linspace(lo, hi, num=max(1, n_cuts), dtype=int)
    return sorted({int(point) for point in points})


def _static_issues(source_path: str | Path | None) -> list[str]:
    if source_path is None:
        return []
    path = Path(source_path)
    if not path.exists():
        return [f"source not found: {path}"]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"syntax error during static audit: {exc}"]
    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else (func.id if isinstance(func, ast.Name) else "")
        )
        if name == "shift":
            for argument in node.args:
                if isinstance(argument, ast.UnaryOp) and isinstance(argument.op, ast.USub):
                    issues.append(
                        f"negative shift offset at line {node.lineno}: possible future access"
                    )
        if name in {"iloc", "__getitem__"}:
            for argument in node.args:
                if isinstance(argument, ast.UnaryOp) and isinstance(argument.op, ast.USub):
                    issues.append(f"negative index at line {node.lineno}: possible future access")
    return issues


def _compare_rows(full: np.ndarray, truncated: np.ndarray, cut: int) -> tuple[int, float, int]:
    rows = 0
    max_diff = 0.0
    first = -1
    for row in range(cut + 1):
        left = full[row]
        right = truncated[row]
        left_nan = np.isnan(left)
        right_nan = np.isnan(right)
        if not np.array_equal(left_nan, right_nan):
            rows += 1
            first = row if first < 0 else first
            continue
        valid = ~left_nan
        if not valid.any():
            continue
        diff = float(np.max(np.abs(left[valid] - right[valid])))
        if diff > 1e-9:
            rows += 1
            max_diff = max(max_diff, diff)
            first = row if first < 0 else first
    return rows, max_diff, first


def check_lookahead(
    strategy: Strategy,
    panel: PanelData,
    *,
    n_cuts: int = 5,
    source_path: str | Path | None = None,
) -> LookaheadReport:
    """Run the truncation and static checks for ``strategy`` on ``panel``."""
    report = LookaheadReport(strategy=strategy.name)
    cuts = default_cut_indices(panel.n_time, n_cuts)
    report.cuts = [int(panel.dates[cut]) for cut in cuts]
    report.static_issues = _static_issues(source_path)
    try:
        full = strategy.generate_weights(panel)
    except Exception as exc:  # pragma: no cover - surfaced to CLI
        report.error = f"strategy failed on full panel: {exc}"
        return report
    for cut in cuts:
        truncated_panel = panel.truncate(int(panel.dates[cut]))
        try:
            truncated = strategy.generate_weights(truncated_panel)
        except Exception as exc:
            report.mismatches.append(
                LookaheadMismatch(
                    cut=cut,
                    date=int(panel.dates[cut]),
                    rows=cut + 1,
                    max_abs_diff=float("inf"),
                    first_row=0,
                )
            )
            report.error = f"strategy failed on truncated panel at {panel.dates[cut]}: {exc}"
            continue
        rows, max_diff, first = _compare_rows(full, truncated, cut)
        if rows:
            report.mismatches.append(
                LookaheadMismatch(
                    cut=cut,
                    date=int(panel.dates[cut]),
                    rows=rows,
                    max_abs_diff=max_diff,
                    first_row=first,
                )
            )
    return report


def lookahead_report_to_json(report: LookaheadReport) -> str:
    import json

    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
