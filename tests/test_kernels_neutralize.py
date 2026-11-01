"""Python binding for the M1 cross-sectional neutralize kernel."""

from __future__ import annotations

import numpy as np


def test_cross_neutralize_binding_demeans_and_preserves_nan() -> None:
    from quantcore import _qcore

    values = np.array([3.0, 1.0, 2.0, np.nan, 2.0, 10.0], dtype=np.float64)
    out = _qcore.kernels.cross_neutralize(values)
    assert out.shape == values.shape
    assert np.isnan(out[3])
    mean = np.nanmean(values)
    assert np.allclose(out[~np.isnan(values)], values[~np.isnan(values)] - mean)
    assert abs(float(np.nansum(out))) < 1e-12
    assert np.allclose(
        _qcore.kernels.cross_neutralize(np.array([5.0, np.nan])), [0.0, np.nan], equal_nan=True
    )
