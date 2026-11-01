"""Research API v2 tests: factor diagnostics, bounded sweep, walk-forward, attribution."""

from __future__ import annotations

import pytest

import quantcore

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")


def test_factor_analysis_contract(api_client: object) -> None:
    response = api_client.post(
        "/api/research/factor",
        json={
            "expression": "rank(ret(close,20))",
            "forward_days": 5,
            "quantiles": 4,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in (
        "name",
        "ic_mean",
        "rank_ic_mean",
        "icir",
        "ic_series",
        "quantile_returns",
        "decay",
        "coverage",
        "observations",
    ):
        assert key in payload, key
    assert payload["synthetic"] is True
    assert payload["quantile_returns"] and len(payload["quantile_returns"]) == 4
    buckets = [row["bucket"] for row in payload["quantile_returns"]]
    assert buckets == [1, 2, 3, 4]
    for row in payload["quantile_returns"]:
        assert set(row) >= {"bucket", "mean_return"}
    assert "rank_icir" in payload
    assert payload["decay"]
    for row in payload["decay"]:
        assert {"days", "ic", "rank_ic"} <= set(row)
    assert [row["days"] for row in payload["decay"]] == sorted(
        row["days"] for row in payload["decay"]
    )
    assert 0.0 <= payload["coverage"] <= 1.0
    assert payload["observations"] > 0
    assert payload["ic_series"]
    assert isinstance(payload["ic_series"][0]["date"], int)
    assert -1.0 <= payload["ic_mean"] <= 1.0

    bad_expression = api_client.post("/api/research/factor", json={"expression": "nope(close)"})
    assert bad_expression.status_code == 400
    assert (
        api_client.post(
            "/api/research/factor", json={"expression": "close", "forward_days": 0}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/research/factor", json={"expression": "close", "quantiles": 1}
        ).status_code
        == 422
    )


def test_sweep_bounded_with_heatmap(api_client: object) -> None:
    response = api_client.post(
        "/api/research/sweep",
        json={
            "template": "momentum",
            "param_grid": {"top_n": [3, 5], "lookback": [60, 120]},
            "workers": 2,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine_backend"] == "cpp"
    assert len(payload["points"]) == 4
    for point in payload["points"]:
        assert point["error"] is None
        assert "sharpe" in point["metrics"]
        assert point["params"]
    assert payload["best"] is not None
    heatmap = payload["heatmap"]
    assert heatmap["x_param"] in {"top_n", "lookback"}
    assert len(heatmap["x_values"]) == 2 and len(heatmap["y_values"]) == 2
    assert len(heatmap["z"]) == 2 and all(len(row) == 2 for row in heatmap["z"])

    too_large = api_client.post(
        "/api/research/sweep",
        json={
            "template": "momentum",
            "param_grid": {
                "top_n": list(range(1, 16)),
                "lookback": list(range(10, 151, 10)),
            },
        },
    )
    assert too_large.status_code == 400
    assert "bounded" in too_large.json()["detail"]

    unknown = api_client.post(
        "/api/research/sweep",
        json={"template": "not-a-template", "param_grid": {"top_n": [3]}},
    )
    assert unknown.status_code == 400


def test_walk_forward_basic(api_client: object) -> None:
    response = api_client.post(
        "/api/research/walk_forward",
        json={"template": "momentum", "params": {"top_n": 5}, "folds": 3},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine_backend"] == "cpp"
    assert len(payload["folds"]) == 3
    for index, fold in enumerate(payload["folds"], start=1):
        assert fold["fold"] == index
        assert fold["start"] <= fold["end"]
        assert "sharpe" in fold["metrics"]
    aggregate = payload["aggregate"]
    assert aggregate["folds"] == 3
    assert 0 <= aggregate["positive_folds"] <= 3
    assert isinstance(aggregate["mean_sharpe"], float)
    # metrics-shaped aliases for UI cards
    assert {"sharpe", "total_return", "max_drawdown", "trade_count"} <= set(aggregate)

    assert (
        api_client.post(
            "/api/research/walk_forward",
            json={"template": "momentum", "folds": 1},
        ).status_code
        == 422
    )


def test_attribution_contract(api_client: object, seeded_experiment: object) -> None:
    response = api_client.post(
        "/api/research/attribution", json={"run_id": seeded_experiment.run_id}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == seeded_experiment.run_id
    assert isinstance(payload["industries"], list)
    assert isinstance(payload["total_pnl"], float | int)
    for row in payload["industries"]:
        for key in ("industry", "pnl", "realized", "unrealized", "weight", "securities"):
            assert key in row, key
    assert (
        api_client.post("/api/research/attribution", json={"run_id": "does-not-exist"}).status_code
        == 404
    )
