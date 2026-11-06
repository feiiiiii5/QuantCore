"""Account values survive restarts and portfolio allocations start at the same date."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from quantcore.calendar import TradingCalendar
from quantcore.data.panel import PanelData
from quantcore.paper import PaperMarketData, PaperSessionEngine, PaperStore
from quantcore.paper.models import PaperSession
from quantcore.paper.portfolio import build_portfolio


def _session(identifier: str, points: list[tuple[int, float]]) -> PaperSession:
    return PaperSession(
        id=identifier,
        name=identifier,
        status="active",
        created_at="2024-01-02T00:00:00+00:00",
        updated_at="2024-01-02T00:00:00+00:00",
        snapshot={"id": "accounting", "synthetic": True},
        start_date=points[0][0],
        end_date=points[-1][0],
        current_date=points[-1][0],
        initial_cash=points[0][1],
        cash=points[-1][1],
        equity_curve=[{"date": date, "equity": value} for date, value in points],
    )


def test_portfolio_allocations_apply_at_first_common_date() -> None:
    first = _session("paper_000000000001", [(20240102, 100), (20240103, 200), (20240104, 220)])
    second = _session("paper_000000000002", [(20240103, 500), (20240104, 450)])
    before = deepcopy([first.to_dict(), second.to_dict()])

    result = build_portfolio([first, second], [0.5, 0.5], initial_cash=10_000)

    # At the allocation date both strategies receive 50%; +10% and -10% cancel.
    assert result["dates"] == [20240103, 20240104]
    assert result["equity"] == [10_000, 10_000]
    assert result["metrics"]["total_return"] == 0
    assert [row["contribution"] for row in result["contributions"]] == [0.05, -0.05]
    assert sum(row["contribution"] for row in result["contributions"]) == pytest.approx(
        result["metrics"]["total_return"], abs=1e-6
    )
    assert [first.to_dict(), second.to_dict()] == before


def test_portfolio_tolerated_weight_rounding_preserves_starting_cash() -> None:
    first = _session("paper_000000000001", [(20240102, 100), (20240103, 110)])
    second = _session("paper_000000000002", [(20240102, 100), (20240103, 90)])

    result = build_portfolio([first, second], [0.5, 0.5000005], initial_cash=10_000_000)

    assert result["equity"][0] == 10_000_000
    assert result["normalized_equity"][0] == 1
    assert result["metrics"]["total_return"] == pytest.approx(
        sum(row["contribution"] for row in result["contributions"]), abs=1e-6
    )


def test_paper_restart_preserves_cost_basis_and_subsequent_buys(tmp_path: Path) -> None:
    dates = [20240102, 20240103, 20240104, 20240105]
    market = PaperMarketData(
        PanelData(
            calendar=TradingCalendar.from_dates(dates),
            securities=pd.DataFrame([{"sec_id": "600000.SH", "code": "600000", "board": "MAIN"}]),
            bars=pd.DataFrame(
                [
                    {
                        "date": date,
                        "sec_id": "600000.SH",
                        "open": 10.0,
                        "high": 10.1,
                        "low": 9.9,
                        "close": 10.0,
                        "pre_close": 10.0,
                        "volume": 100_000_000,
                        "source": "SYNTHETIC",
                    }
                    for date in dates
                ]
            ),
            meta={"synthetic": True, "source": "SYNTHETIC"},
        )
    )
    session = PaperSessionEngine.create(
        market, snapshot={"id": "accounting", "synthetic": True}, initial_cash=20_000_000
    )
    uninterrupted = PaperSessionEngine(market, session)
    uninterrupted.submit_order(code="600000", side="buy", qty=1_000_000)
    uninterrupted.step()
    position = session.positions["600000.SH"]
    assert position.avg_cost == pytest.approx(10.00322)
    cost_before = position.avg_cost * position.qty
    pnl_before = position.pnl()

    store = PaperStore(tmp_path / "paper")
    store.save(session)
    restored = store.load(session.id)
    assert restored.positions["600000.SH"].avg_cost * position.qty == cost_before
    assert restored.positions["600000.SH"].pnl() == pnl_before

    reopened = PaperSessionEngine(market, restored)
    for engine in (uninterrupted, reopened):
        engine.submit_order(code="600000", side="buy", qty=100)
        engine.step()
    assert restored.positions["600000.SH"].avg_cost == position.avg_cost
    assert restored.positions["600000.SH"].pnl() == position.pnl()
    assert restored.account_view() == session.account_view()
