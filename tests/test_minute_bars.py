"""M8-002 synthetic minute bars: canonical generator + API/UI contract."""

from __future__ import annotations

import numpy as np

from quantcore.data.minute import INTRADAY_TIMES, synthetic_minute_bars
from quantcore.data.synthetic import SyntheticConfig, generate_synthetic_panel


def test_synthetic_minute_bars_are_consistent() -> None:
    panel = generate_synthetic_panel(
        SyntheticConfig(n_sec=3, start="2023-01-03", end="2023-12-29", seed=11)
    )
    code = str(panel.securities.iloc[0]["code"])
    frame = synthetic_minute_bars(panel, code, seed=11)
    assert len(frame) == len(INTRADAY_TIMES)
    assert frame["datetime"].is_monotonic_increasing
    assert set(frame["source"]) == {"SYNTHETIC_MINUTE"}
    for _, row in frame.iterrows():
        assert (
            row["low"]
            <= min(row["open"], row["close"])
            <= max(row["open"], row["close"])
            <= row["high"]
        )
    daily = panel.bars[panel.bars["code"] == code].sort_values("date").iloc[-1]
    assert int(frame["volume"].sum()) == int(daily["volume"])
    assert np.isclose(float(frame["amount"].sum()), float(daily["amount"]), rtol=1e-9)
    again = synthetic_minute_bars(panel, code, seed=11)
    assert frame.equals(again)


def test_minute_bars_api(api_client) -> None:
    securities = api_client.get("/api/market/securities?limit=5").json()
    code = securities[0]["code"]
    response = api_client.get(f"/api/market/minute-bars?code={code}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["synthetic"] is True
    assert payload["source"] == "SYNTHETIC_MINUTE"
    assert len(payload["bars"]) == 5
    invalid = api_client.get("/api/market/minute-bars?code=999999")
    assert invalid.status_code == 404
