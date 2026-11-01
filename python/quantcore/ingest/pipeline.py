"""Ingestion pipeline: provider -> canonical panel -> quality gate -> Parquet warehouse.

The pipeline enforces provider quotas/retries, supports incremental updates keyed by the
stored watermark, quarantines bad rows instead of dropping them silently, and records a
quality report with every ingest run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import (
    PanelData,
    normalize_bars,
    normalize_corporate_actions,
    normalize_financials,
)
from ..data.store import ParquetStore
from ..errors import ProviderError
from ..providers.base import DataProvider, RetryPolicy, retry_call
from ..quality import QualityReport, quarantine_bad_rows, run_quality_checks


@dataclass
class IngestResult:
    provider: str
    start: int
    end: int
    synthetic: bool
    datasets: dict[str, int] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    quarantined_rows: int = 0
    quality_passed: bool = False
    manifest_hash: str = ""
    incremental: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "start": self.start,
            "end": self.end,
            "synthetic": self.synthetic,
            "datasets": self.datasets,
            "quality": self.quality,
            "quarantined_rows": self.quarantined_rows,
            "quality_passed": self.quality_passed,
            "manifest_hash": self.manifest_hash,
            "incremental": self.incremental,
        }


class ProviderIngestor:
    """Fetch, validate and persist data from a :class:`DataProvider`."""

    def __init__(
        self,
        provider: DataProvider,
        store: ParquetStore,
        *,
        enforce_quality: bool = True,
        quarantine: bool = True,
        retry: RetryPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.store = store
        self.enforce_quality = enforce_quality
        self.quarantine = quarantine
        self.retry = retry or RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0)

    def _call(self, fn: Callable[[], Any]) -> Any:
        return retry_call(fn, self.retry, sleeper=lambda _: None)

    def _existing(self, name: str) -> pd.DataFrame | None:
        if name in self.store.list_datasets():
            return self.store.read_dataset(name)
        return None

    def update(
        self,
        start: int | str,
        end: int | str,
        codes: Iterable[str] | None = None,
        incremental: bool = True,
    ) -> IngestResult:
        start_i, end_i = to_date_int(start), to_date_int(end)
        if start_i > end_i:
            raise ValueError("start date must not be after end date")
        self.provider.require("daily_bars")
        self.provider.ensure_available()

        existing_bars = self._existing("bars") if incremental else None
        effective_start = start_i
        if existing_bars is not None and not existing_bars.empty:
            watermark = int(existing_bars["date"].max())
            effective_start = max(start_i, watermark + 1)
            if effective_start > end_i:
                result = IngestResult(
                    provider=self.provider.name,
                    start=start_i,
                    end=end_i,
                    synthetic=self.provider.name == "synthetic",
                    datasets=self.store.state.dataset_rows(),
                    quality={"passed": True, "note": "no new trading days"},
                    quality_passed=True,
                    manifest_hash=self.store.manifest_hash(),
                    incremental=True,
                )
                self.store.state.set_meta("last_ingest", result.to_dict())
                return result

        calendar = self._call(lambda: self.provider.fetch_calendar(effective_start, end_i))
        securities = self._call(self.provider.fetch_security_master)
        bars_new = self._call(lambda: self.provider.fetch_daily_bars(codes, effective_start, end_i))
        financials_new = (
            self._call(lambda: self.provider.fetch_financials(codes, effective_start, end_i))
            if self.provider.supports("financials")
            else pd.DataFrame()
        )
        actions_new = (
            self._call(lambda: self.provider.fetch_corporate_actions(codes, effective_start, end_i))
            if self.provider.supports("corporate_actions")
            else pd.DataFrame()
        )

        if existing_bars is not None and not existing_bars.empty:
            bars = pd.concat([existing_bars, bars_new], ignore_index=True)
            bars = (
                normalize_bars(bars)
                .drop_duplicates(subset=["date", "sec_id"], keep="last")
                .reset_index(drop=True)
            )
            securities = (
                pd.concat([self.store.read_dataset("securities"), securities], ignore_index=True)
                .drop_duplicates(subset=["sec_id"], keep="last")
                .reset_index(drop=True)
            )
            full_calendar = TradingCalendar.from_dates(
                list(calendar.dates)
                + list(
                    TradingCalendar.from_dates(
                        self.store.read_dataset("calendar")["date"].tolist()
                    ).dates
                )
            )
            existing_financials = self._existing("financials")
            if existing_financials is not None and not financials_new.empty:
                financials = normalize_financials(
                    pd.concat([existing_financials, financials_new], ignore_index=True)
                ).drop_duplicates(
                    subset=["sec_id", "end_date", "ann_date", "update_flag"], keep="last"
                )
            else:
                financials = (
                    normalize_financials(financials_new)
                    if not financials_new.empty
                    else (
                        existing_financials if existing_financials is not None else pd.DataFrame()
                    )
                )
            existing_actions = self._existing("corporate_actions")
            if existing_actions is not None and not actions_new.empty:
                corporate_actions = normalize_corporate_actions(
                    pd.concat([existing_actions, actions_new], ignore_index=True)
                ).drop_duplicates(subset=["sec_id", "ex_date"], keep="last")
            else:
                corporate_actions = (
                    normalize_corporate_actions(actions_new)
                    if not actions_new.empty
                    else (existing_actions if existing_actions is not None else pd.DataFrame())
                )
        else:
            bars = normalize_bars(bars_new)
            full_calendar = calendar
            financials = (
                normalize_financials(financials_new) if not financials_new.empty else pd.DataFrame()
            )
            corporate_actions = (
                normalize_corporate_actions(actions_new)
                if not actions_new.empty
                else pd.DataFrame()
            )

        synthetic = self.provider.name == "synthetic"
        panel = PanelData(
            calendar=full_calendar,
            securities=securities,
            bars=bars,
            financials=financials,
            corporate_actions=corporate_actions,
            meta={
                "provider": self.provider.name,
                "source": "SYNTHETIC" if synthetic else self.provider.name.upper(),
                "synthetic": synthetic,
                "provider_info": self.provider.quota_info(),
                "disclaimer": (
                    "SYNTHETIC data: every value is fabricated and not a real market result"
                    if synthetic
                    else ""
                ),
            },
        )

        report: QualityReport = run_quality_checks(panel)
        quarantined = 0
        if self.quarantine:
            quarantined_result = quarantine_bad_rows(panel)
            if quarantined_result.dropped:
                bad = quarantined_result.bad_rows.copy()
                bad["quarantined_at"] = pd.Timestamp.now(tz="UTC").isoformat()
                self.store.write_dataset("quarantine", bad, partition_column="year")
                panel = quarantined_result.clean
                report = quarantined_result.report
                quarantined = quarantined_result.dropped
        if self.enforce_quality:
            report.raise_if_failed()

        datasets = self.store.write_panel(panel)
        quality = report.to_dict()
        quality["report_path"] = str(
            self.store.root / "quality" / f"ingest_{panel.content_hash()[:12]}.json"
        )
        _write_report(self.store, quality)
        ingest_result = IngestResult(
            provider=self.provider.name,
            start=start_i,
            end=end_i,
            synthetic=synthetic,
            datasets={name: stats.rows for name, stats in datasets.items()},
            quality=quality,
            quarantined_rows=quarantined,
            quality_passed=report.passed,
            manifest_hash=self.store.manifest_hash(),
            incremental=incremental,
        )
        self.store.state.set_meta("last_ingest", ingest_result.to_dict())
        return ingest_result


def _write_report(store: ParquetStore, quality: dict[str, Any]) -> None:
    import json

    directory = store.root / "quality"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "latest.json"
    path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = ["IngestResult", "ProviderError", "ProviderIngestor"]
