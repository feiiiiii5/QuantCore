"""Beginner onboarding, presets and watchlist API tests (offline, synthetic only)."""

from __future__ import annotations

from typing import Any

import pytest

import quantcore
from quantcore.backtest.config import BacktestConfig
from quantcore.backtest.engine import run_backtest
from quantcore.data.state import SQLiteState
from quantcore.strategy.spec import StrategySpec
from quantcore.templates.registry import create_template, template_ids

STEP_FIELDS = {"id", "title", "description", "action", "label", "done"}
PRESET_FIELDS = {
    "id",
    "name",
    "tagline",
    "description",
    "plain_terms",
    "risk_note",
    "template",
    "params",
    "horizon",
    "suitable_for",
}


@pytest.fixture()
def client(api_client: Any) -> Any:
    """Thin alias for the shared api_client; app.py owns the real route wiring."""
    return api_client


def _by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["id"]: step for step in payload["steps"]}


def test_onboarding_initial_state_and_auto_detection(client: Any) -> None:
    response = client.get("/api/onboarding")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"first_run", "beginner", "steps", "progress"}
    assert payload["first_run"] is True
    assert payload["beginner"] is True
    assert [step["id"] for step in payload["steps"]] == [
        "data",
        "backtest",
        "result",
        "data_health",
    ]
    assert all(set(step) == STEP_FIELDS for step in payload["steps"])
    assert all(
        step["action"] in {"bootstrap", "backtest", "browse", "data"} for step in payload["steps"]
    )
    assert all(isinstance(step["done"], bool) for step in payload["steps"])

    steps = _by_id(payload)
    # The api_app fixture seeds a real synthetic snapshot and one experiment.
    assert steps["data"]["done"] is True
    assert steps["backtest"]["done"] is True
    assert steps["result"]["done"] is True
    assert steps["data_health"]["done"] is False
    assert payload["progress"] == {"done": 3, "total": 4}


def test_complete_step_is_idempotent_and_reset(client: Any) -> None:
    before = client.get("/api/onboarding").json()
    assert _by_id(before)["data_health"]["done"] is False

    response = client.post("/api/onboarding/complete", json={"step": "data_health"})
    assert response.status_code == 200
    after = response.json()
    assert after["first_run"] is False
    assert _by_id(after)["data_health"]["done"] is True
    assert after["progress"] == {"done": 4, "total": 4}
    assert client.app.state.state.get_meta("onboarding")["completed"] == ["data_health"]

    again = client.post("/api/onboarding/complete", json={"step": "data_health"}).json()
    assert again["progress"] == {"done": 4, "total": 4}
    assert again["first_run"] is False

    reset = client.post("/api/onboarding/reset")
    assert reset.status_code == 200
    cleared = reset.json()
    assert cleared["first_run"] is True
    assert _by_id(cleared)["data_health"]["done"] is False
    assert cleared["progress"] == before["progress"]
    assert client.app.state.state.get_meta("onboarding") is None


@pytest.mark.parametrize("body", [{"step": "nope"}, {}, {"step": 1}])
def test_invalid_complete_step_returns_400(client: Any, body: dict[str, Any]) -> None:
    before = client.get("/api/onboarding").json()
    response = client.post("/api/onboarding/complete", json=body)
    assert response.status_code == 400
    assert "detail" in response.json()
    assert client.get("/api/onboarding").json() == before


def test_presets_contract_and_template_params(client: Any) -> None:
    response = client.get("/api/onboarding/presets")
    assert response.status_code == 200
    presets = response.json()
    assert 4 <= len(presets) <= 6
    assert len({preset["id"] for preset in presets}) == len(presets)
    known_templates = set(template_ids())
    for preset in presets:
        assert set(preset) == PRESET_FIELDS
        assert all(
            isinstance(preset[key], str) and preset[key]
            for key in (
                "id",
                "name",
                "tagline",
                "description",
                "plain_terms",
                "risk_note",
                "horizon",
                "suitable_for",
            )
        )
        assert preset["template"] in known_templates
        assert isinstance(preset["params"], dict)
        spec = StrategySpec(name=preset["id"], template=preset["template"], params=preset["params"])
        assert spec.validate_params()["rebalance"] in {
            "daily",
            "weekly",
            "monthly",
            "quarterly",
        }


@pytest.mark.skipif(not quantcore.engine_available(), reason="C++ backtest engine is unavailable")
def test_two_presets_run_real_synthetic_backtests(client: Any, small_panel: Any) -> None:
    presets = client.get("/api/onboarding/presets").json()
    for preset in presets[:2]:
        strategy = create_template(preset["template"], preset["params"])
        weights = strategy.generate_targets(small_panel)
        result = run_backtest(small_panel, weights, BacktestConfig())
        assert result.engine_backend == "cpp"
        assert result.equity.size == small_panel.n_time
        assert result.equity_yuan.size > 0
        for key in ("total_return", "max_drawdown", "sharpe", "trade_count"):
            assert key in result.metrics


def test_watchlist_read_write_and_dedupe(client: Any) -> None:
    assert client.get("/api/watchlist").json() == {"codes": []}

    response = client.put(
        "/api/watchlist", json={"codes": ["600000", "000001", "600000", " 300750 "]}
    )
    assert response.status_code == 200
    assert response.json() == {"codes": ["600000", "000001", "300750"]}
    assert client.get("/api/watchlist").json() == {"codes": ["600000", "000001", "300750"]}

    state_path = client.app.state.settings.state_path
    # Plain list shape is what the live-quote service reads from meta.
    assert SQLiteState(state_path).get_meta("watchlist") == ["600000", "000001", "300750"]


@pytest.mark.parametrize(
    "codes",
    [
        ["12345"],
        ["1234567"],
        ["abcdef"],
        ["60000a"],
        [""],
        [600000],
        "600000",
    ],
)
def test_watchlist_rejects_invalid_codes(client: Any, codes: Any) -> None:
    assert client.put("/api/watchlist", json={"codes": ["600000"]}).status_code == 200
    response = client.put("/api/watchlist", json={"codes": codes})
    assert response.status_code == 400
    assert client.get("/api/watchlist").json() == {"codes": ["600000"]}


def test_watchlist_limit_is_fifty(client: Any) -> None:
    fifty = [f"{index:06d}" for index in range(1, 51)]
    response = client.put("/api/watchlist", json={"codes": fifty})
    assert response.status_code == 200
    assert response.json() == {"codes": fifty}

    too_many = [f"{index:06d}" for index in range(1, 52)]
    response = client.put("/api/watchlist", json={"codes": too_many})
    assert response.status_code == 400
    assert client.get("/api/watchlist").json() == {"codes": fifty}
