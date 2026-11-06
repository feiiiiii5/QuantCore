"""A bounded result must not repeatedly materialise the entire market panel."""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from quantcore.data.matrices import MatrixLayout
from quantcore.data.panel import PanelData
from quantcore.server import create_app


@pytest.mark.parametrize("expression", ["close", "1"])
def test_screener_limits_rows_after_stable_ranking_without_repeated_pivots(
    tmp_path: Path,
    small_panel: PanelData,
    monkeypatch,
    expression: str,
) -> None:
    latest = small_panel.matrix("close")[-1]
    expected = np.flatnonzero(np.isfinite(latest) & (latest > 0))
    if expression == "close":
        expected = expected[np.argsort(-latest[expected], kind="stable")]
    app = create_app(data_root=tmp_path, start_worker=False, token="test-token")
    app.state.workspace._synthetic = small_panel
    calls: Counter[str] = Counter()
    original = MatrixLayout.matrix

    def counted(self, field_name, *args, **kwargs):
        calls[field_name] += 1
        return original(self, field_name, *args, **kwargs)

    monkeypatch.setattr(MatrixLayout, "matrix", counted)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/screener/run",
            headers={"Authorization": "Bearer test-token"},
            json={
                "expression": expression,
                "limit": 5,
                "universe": {"exclude_st": False, "exclude_suspended": False, "min_price": 0},
            },
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["matched_count"] == len(expected)
    assert [row["sec_id"] for row in result["rows"]] == [
        small_panel.sec_id_list[i] for i in expected[:5]
    ]
    assert max(calls.values()) == 1, calls
