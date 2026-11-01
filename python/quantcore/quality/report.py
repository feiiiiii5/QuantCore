"""Quality report types shared by the checks, ingest pipeline and snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.panel import PanelData

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class CheckIssue:
    """One detected data-quality problem."""

    check: str
    severity: str
    message: str
    count: int
    samples: tuple[dict[Any, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "count": int(self.count),
            "samples": list(self.samples),
        }


@dataclass
class QualityReport:
    """Aggregated quality report for a panel."""

    rows: int
    issues: list[CheckIssue] = field(default_factory=list)
    synthetic: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def errors(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == ERROR]

    @property
    def warnings(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == WARNING]

    @property
    def passed(self) -> bool:
        return not self.errors

    def add(self, issue: CheckIssue) -> None:
        self.issues.append(issue)

    def raise_if_failed(self) -> None:
        if self.errors:
            summary = "; ".join(issue.message for issue in self.errors)
            raise ValueError(f"data quality checks failed: {summary}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": int(self.rows),
            "synthetic": self.synthetic,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def write(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )


@dataclass
class QuarantineResult:
    clean: PanelData
    bad_rows: pd.DataFrame
    report: QualityReport
    dropped: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "dropped_rows": self.dropped,
            "clean_rows": len(self.clean.bars),
            "quality": self.report.to_dict(),
        }
