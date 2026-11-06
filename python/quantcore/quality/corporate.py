"""Corporate-action checks before events enter snapshots or the native ledger."""

import numpy as np

from ..data.panel import PanelData
from .report import ERROR, CheckIssue, QualityReport


def check_corporate_actions(panel: PanelData, report: QualityReport) -> None:
    frame = panel.corporate_actions
    if frame.empty:
        return
    bad = (
        (frame["ex_date"] < frame["ann_date"])
        | ~np.isfinite(frame["cash_per_share"].to_numpy(float))
        | ~np.isfinite(frame["split_ratio"].to_numpy(float))
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
