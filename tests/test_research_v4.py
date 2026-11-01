"""M7-003/004 tests: factor correlation matrix and deterministic random parameter sweeps."""

from __future__ import annotations

from typing import Any

import pytest

import quantcore

pytestmark = pytest.mark.skipif(not quantcore.engine_available(), reason="C++ engine unavailable")

AUTH = {"Authorization": "Bearer test-token"}
FACTORS = [
    "rank(ret(close,20))",
    "ret(close,20)",
    "ma(close,5) / ma(close,20) - 1",
]


def _date_text(value: int) -> str:
    text = str(int(value))
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def test_factor_correlation_contract(api_client: Any) -> None:
    response = api_client.post("/api/research/factor_correlation", json={"expressions": FACTORS})
    assert response.status_code == 200, response.text
    payload = response.json()
    for key in (
        "expressions",
        "labels",
        "matrix",
        "average_abs_correlation",
        "observations",
        "dates",
    ):
        assert key in payload, key
    assert payload["expressions"] == FACTORS
    assert payload["labels"] == FACTORS
    matrix = payload["matrix"]
    assert len(matrix) == len(FACTORS)
    assert all(len(row) == len(FACTORS) for row in matrix)
    for index in range(len(FACTORS)):
        assert matrix[index][index] == pytest.approx(1.0)
        for other in range(index + 1, len(FACTORS)):
            assert matrix[index][other] == pytest.approx(matrix[other][index])
            assert -1.0 <= matrix[index][other] <= 1.0
    assert 0.0 <= payload["average_abs_correlation"] <= 1.0
    assert payload["observations"] > 0
    assert payload["dates"] and all(isinstance(value, int) for value in payload["dates"])
    assert payload["method"] == "pearson"
    assert payload["synthetic"] is True

    again = api_client.post(
        "/api/research/factor_correlation", json={"expressions": FACTORS}
    ).json()
    assert again["matrix"] == matrix
    assert again["average_abs_correlation"] == payload["average_abs_correlation"]

    spearman = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": FACTORS[:2], "method": "spearman"},
    )
    assert spearman.status_code == 200
    assert spearman.json()["method"] == "spearman"
    assert spearman.json()["matrix"][0][1] == spearman.json()["matrix"][1][0]


def test_factor_correlation_date_window(api_client: Any) -> None:
    full = api_client.post("/api/research/factor_correlation", json={"expressions": FACTORS}).json()
    dates = full["dates"]
    start = _date_text(dates[len(dates) // 4])
    end = _date_text(dates[len(dates) * 3 // 4])
    windowed = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": FACTORS, "start": start, "end": end},
    )
    assert windowed.status_code == 200, windowed.text
    payload = windowed.json()
    assert payload["dates"] and payload["dates"][0] >= int(start.replace("-", ""))
    assert payload["dates"][-1] <= int(end.replace("-", ""))
    assert len(payload["dates"]) < len(dates)
    assert payload["periods"] == len(payload["dates"])


def test_factor_correlation_validation(api_client: Any) -> None:
    one = api_client.post("/api/research/factor_correlation", json={"expressions": ["close"]})
    assert one.status_code == 400
    too_many = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": [f"ret(close,{n})" for n in range(1, 12)]},
    )
    assert too_many.status_code == 422
    invalid = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": ["close", "unknown_func(close)"]},
    )
    assert invalid.status_code == 400
    bad_method = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": FACTORS[:2], "method": "kendall"},
    )
    assert bad_method.status_code == 422
    missing_snapshot = api_client.post(
        "/api/research/factor_correlation",
        json={"expressions": FACTORS[:2], "snapshot": "snap_missing"},
    )
    assert missing_snapshot.status_code in {400, 404}
    assert (
        api_client.post(
            "/api/research/factor_correlation",
            json={"expressions": FACTORS},
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )


def _sweep(client: Any, grid: dict[str, list[Any]], **extra: Any) -> Any:
    body = {"template": "momentum", "param_grid": grid, **extra}
    return client.post("/api/research/sweep", json=body)


def test_sweep_random_sampling(api_client: Any) -> None:
    grid = {
        "top_n": [1, 2, 3, 4, 5, 6],
        "lookback": [20, 40, 60, 80, 100, 120],
    }
    body = {"mode": "random", "sample_size": 5, "seed": 7}
    response = _sweep(api_client, grid, **body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["points"]) == 5
    assert payload["grid_size"] == 36
    assert payload["sampling"] == {
        "mode": "random",
        "requested": 5,
        "returned": 5,
        "seed": 7,
    }
    assert payload["best"] is not None
    for point in payload["points"]:
        assert point["error"] is None
        assert "sharpe" in point["metrics"]
        assert point["params"]

    again = _sweep(api_client, grid, **body).json()
    assert [point["params"] for point in again["points"]] == [
        point["params"] for point in payload["points"]
    ]
    assert [point["metrics"] for point in again["points"]] == [
        point["metrics"] for point in payload["points"]
    ]

    other_seed = _sweep(api_client, grid, mode="random", sample_size=5, seed=999).json()
    assert [point["params"] for point in other_seed["points"]] != [
        point["params"] for point in payload["points"]
    ]

    default_seed = _sweep(api_client, grid, mode="random", sample_size=4).json()
    assert default_seed["sampling"]["seed"] == 42


def test_sweep_random_large_grid_bounds(api_client: Any) -> None:
    # 20 x 20 = 400 combinations: rejected as a full grid, allowed via random sampling.
    grid = {"top_n": list(range(1, 21)), "lookback": list(range(20, 220, 10))}
    rejected = _sweep(api_client, grid)
    assert rejected.status_code == 400
    assert "bounded" in rejected.json()["detail"]
    sampled = _sweep(api_client, grid, mode="random", sample_size=3)
    assert sampled.status_code == 200, sampled.text
    payload = sampled.json()
    assert payload["grid_size"] == 400
    assert len(payload["points"]) == 3
    assert payload["sampling"]["returned"] == 3


def test_sweep_random_boundaries_and_grid_compatibility(api_client: Any) -> None:
    grid = {"top_n": [3, 5], "lookback": [60, 120]}
    assert _sweep(api_client, grid, mode="random", sample_size=0).status_code == 400
    assert _sweep(api_client, grid, mode="random", sample_size=201).status_code == 422
    assert _sweep(api_client, grid, mode="grid", sample_size=5).status_code == 400
    assert _sweep(api_client, grid, mode="bogus").status_code == 422

    oversampled = _sweep(api_client, grid, mode="random", sample_size=10)
    assert oversampled.status_code == 200
    assert oversampled.json()["sampling"]["returned"] == 4
    assert oversampled.json()["sampling"]["requested"] == 10

    grid_mode = _sweep(api_client, grid)
    assert grid_mode.status_code == 200
    payload = grid_mode.json()
    assert payload["sampling"] == {
        "mode": "grid",
        "requested": 4,
        "returned": 4,
        "seed": 42,
    }
    assert len(payload["points"]) == 4
    assert payload["grid_size"] == 4
