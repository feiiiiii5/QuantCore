"""M8-004 ETF / convertible-bond canonical data + paper lot rules (synthetic fixtures)."""

from __future__ import annotations

import pytest

from quantcore.backtest.config import RuleSetConfig
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel
from quantcore.paper.errors import PaperValidationError
from quantcore.paper.rules import canonical_buy_qty


def test_synthetic_etf_and_cb_assets() -> None:
    panel = generate_synthetic_panel(
        SyntheticConfig(n_sec=6, start="2023-01-03", end="2023-12-29", n_etf=2, n_cb=2)
    )
    assert panel.n_sec == 10
    types = panel.securities["sec_type"].value_counts().to_dict()
    assert types == {"STOCK": 6, "ETF": 2, "CONVERTIBLE": 2}
    etf = panel.securities[panel.securities["sec_type"] == "ETF"].iloc[0]
    cb = panel.securities[panel.securities["sec_type"] == "CONVERTIBLE"].iloc[0]
    assert etf["code"].startswith("510")
    assert cb["code"].startswith("110")
    assert panel.bars[panel.bars["sec_id"] == etf["sec_id"]].shape[0] > 100
    assert float(panel.bars.loc[panel.bars["sec_id"] == cb["sec_id"], "close"].iloc[0]) > 50


def test_paper_lot_rules_for_etf_and_cb() -> None:
    rules = RuleSetConfig()
    assert canonical_buy_qty("MAIN", 200, rules) == 200
    assert canonical_buy_qty("MAIN", 200, rules, "ETF") == 200
    assert canonical_buy_qty("MAIN", 20, rules, "CONVERTIBLE") == 20
    with pytest.raises(PaperValidationError):
        canonical_buy_qty("MAIN", 150, rules, "ETF")
    with pytest.raises(PaperValidationError):
        canonical_buy_qty("MAIN", 15, rules, "CONVERTIBLE")
