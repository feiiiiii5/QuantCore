"""Synthetic market-data provider wrapping :mod:`quantcore.data.synthetic`."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

import pandas as pd

from ..calendar import TradingCalendar, to_date_int
from ..data.panel import PanelData
from ..data.synthetic import SyntheticConfig, generate_synthetic_panel
from .base import (
    DataProvider,
    ProviderCapabilities,
    ProviderPermission,
    ProviderQuota,
    subset_frame,
)


class SyntheticProvider(DataProvider):
    """Deterministic fully-offline provider; all values are labelled ``SYNTHETIC``."""

    name: ClassVar[str] = "synthetic"
    capabilities: ClassVar[ProviderCapabilities] = ProviderCapabilities(
        financials=True, corporate_actions=True
    )
    quota: ClassVar[ProviderQuota] = ProviderQuota(
        max_calls=10_000,
        window_seconds=1.0,
        tier="offline",
        notes="no network; quota only guards accidental generation loops",
    )
    permission: ClassVar[ProviderPermission] = ProviderPermission()

    def __init__(self, config: SyntheticConfig | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.config = config or SyntheticConfig()
        self._panel: PanelData | None = None

    def panel(self) -> PanelData:
        """Generate (once) and return the full synthetic panel."""
        if self._panel is None:
            self._panel = generate_synthetic_panel(self.config)
        return self._panel

    def fetch_calendar(self, start: int | str, end: int | str) -> TradingCalendar:
        start_i, end_i = to_date_int(start), to_date_int(end)
        self.limiter.acquire()
        return self.panel().calendar.slice(start_i, end_i)

    def fetch_security_master(self) -> pd.DataFrame:
        self.limiter.acquire()
        return self.panel().securities.copy()

    def fetch_daily_bars(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.limiter.acquire()
        start_i, end_i = to_date_int(start), to_date_int(end)
        return subset_frame(self.panel().bars, start_i, end_i, codes=codes)

    def fetch_financials(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.limiter.acquire()
        start_i, end_i = to_date_int(start), to_date_int(end)
        frame = self.panel().financials
        return subset_frame(
            frame, start_i, end_i, date_column="ann_date", codes=codes, code_column="sec_id"
        )

    def fetch_corporate_actions(
        self, codes: Iterable[str] | None, start: int | str, end: int | str
    ) -> pd.DataFrame:
        self.limiter.acquire()
        start_i, end_i = to_date_int(start), to_date_int(end)
        frame = self.panel().corporate_actions
        return subset_frame(
            frame, start_i, end_i, date_column="ex_date", codes=codes, code_column="sec_id"
        )

    def fetch_panel(
        self,
        start: int | str,
        end: int | str,
        codes: Iterable[str] | None = None,
    ) -> PanelData:
        self.limiter.acquire()
        panel = self.panel().select(to_date_int(start), to_date_int(end))
        if codes is not None:
            wanted = set(codes)
            panel = PanelData(
                calendar=panel.calendar,
                securities=panel.securities[panel.securities["sec_id"].isin(wanted)],
                bars=panel.bars[panel.bars["sec_id"].isin(wanted)],
                financials=panel.financials[panel.financials["sec_id"].isin(wanted)],
                corporate_actions=panel.corporate_actions[
                    panel.corporate_actions["sec_id"].isin(wanted)
                ],
                meta=dict(panel.meta),
            )
        return panel
