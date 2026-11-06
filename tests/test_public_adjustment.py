"""Quoted OHLC distinguish additive cash adjustments from price-ratio drift."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore.errors import ProviderError
from quantcore.providers.public_web import (
    build_canonical_bars,
    derive_adjustment,
    parse_tencent_qfq,
)


def pair(closes: list[float], offsets: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.DataFrame(
        {
            "date": [20260105 + i for i in range(len(closes))],
            "sec_id": "SZ.000100",
            "close": closes,
            "volume": 1000,
        }
    )
    for field, delta in [("open", 0), ("high", 0.2), ("low", -0.2)]:
        raw[field] = np.asarray(closes) + delta
    adjusted = raw[["date", "open", "high", "low", "close"]].copy()
    adjusted[["open", "high", "low", "close"]] -= np.asarray(offsets)[:, None]
    adjusted.attrs["price_tick"] = 0.001
    return raw, adjusted


@pytest.mark.parametrize(
    "previous,current,offset", [(4.67, 5.14, 0.22), (4.82, 5.30, 0.14), (5.59, 6.15, 0.056)]
)
def test_constant_cash_offset_cannot_fabricate_an_event(previous, current, offset) -> None:
    raw, adjusted = pair([previous, current, current - 0.1], [offset] * 3)
    factors, actions = derive_adjustment(raw, adjusted)
    assert actions.empty
    np.testing.assert_allclose(factors, adjusted.close / raw.close)
    bars = build_canonical_bars(
        raw, factors, board="MAIN", st=False, source="SINA", actions=actions
    )
    assert bars.iloc[1].pre_close == previous
    assert bars.iloc[1].close <= bars.iloc[1].limit_up


def test_cash_offset_step_has_the_correct_cash_and_trading_reference() -> None:
    raw, adjusted = pair([10, 10.1, 9.7, 9.8], [0.5, 0.5, 0.1, 0.1])
    factors, actions = derive_adjustment(raw, adjusted)
    assert len(actions) == 1
    assert actions.iloc[0].ex_date == 20260107
    assert actions.iloc[0].cash_per_share == pytest.approx(0.4)
    bars = build_canonical_bars(
        raw, factors, board="MAIN", st=False, source="SINA", actions=actions
    )
    assert bars.iloc[2].pre_close == 9.7
    assert bars.iloc[3].pre_close == 9.7  # ratio drift is not another adjustment


def test_offset_increase_is_an_explicit_unsupported_event() -> None:
    raw, adjusted = pair([10, 10.1, 10.2], [0.1, 0.1, 0.4])
    with pytest.raises(ProviderError, match="non-positive"):
        derive_adjustment(raw, adjusted)


def test_mixed_affine_transform_is_not_mislabeled_as_cash_or_split() -> None:
    raw, adjusted = pair([10, 10.1, 10.2], [0, 0, 0])
    raw["high"] = raw.close + 1
    raw["low"] = raw.close - 1
    adjusted[["open", "high", "low", "close"]] = raw[["open", "high", "low", "close"]] * 0.5 - 2
    with pytest.raises(ProviderError, match="mixed affine"):
        derive_adjustment(raw, adjusted)


def test_verified_pure_multiplicative_split_keeps_its_existing_semantics() -> None:
    raw, adjusted = pair([10, 10, 10, 10, 5, 5], [0] * 6)
    adjusted.loc[:3, ["open", "high", "low", "close"]] *= 0.5
    factors, actions = derive_adjustment(raw, adjusted)
    np.testing.assert_allclose(factors, [0.5, 0.5, 0.5, 0.5, 1, 1])
    assert len(actions) == 1
    assert actions.iloc[0].split_ratio == 2
    assert actions.iloc[0].cash_per_share == 0


def test_adjustment_coverage_is_never_backfilled() -> None:
    raw, adjusted = pair([10, 10, 10], [0.1] * 3)
    with pytest.raises(ProviderError, match="coverage starts 20260106; missing date 20260105"):
        derive_adjustment(raw, adjusted.iloc[1:])


def test_qfq_parser_preserves_ohlc_and_reported_resolution() -> None:
    parsed = parse_tencent_qfq(
        {
            "data": {
                "sz000100": {
                    "qfqday": [
                        ["2026-01-05", "4.510", "4.920", "4.940", "4.500", "100"],
                    ]
                }
            }
        },
        "sz000100",
    )
    assert parsed.iloc[0][["open", "high", "low", "close"]].tolist() == [4.51, 4.94, 4.5, 4.92]
    assert parsed.attrs["price_tick"] == 0.001
