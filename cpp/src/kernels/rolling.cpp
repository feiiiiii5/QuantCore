// Rolling (time-series) kernels. Semantics: see kernels_internal.h.
#include "qcore/kernels.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>

#include "kernels_internal.h"

namespace qc::kernels {
namespace {

constexpr double kNaNValue = std::numeric_limits<double>::quiet_NaN();

void fill_nan(double* out, size_t n) {
  for (size_t i = 0; i < n; ++i) out[i] = kNaNValue;
}

void require_rolling(const double* x, size_t n, size_t window, double* out, const char* name) {
  detail::require_series(x, n, name);
  detail::require_window(window, name);
  detail::require_output(out, n, name);
}

// Window [i+1-window, i]; caller guarantees i + 1 >= window.
std::size_t window_begin(std::size_t i, std::size_t window) { return i + 1 - window; }

}  // namespace

void rolling_sum(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_sum");
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double sum = 0.0;
    for (size_t j = begin; j <= i; ++j) sum += x[j];
    out[i] = sum;
  }
}

void rolling_mean(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_mean");
  const double denominator = static_cast<double>(window);
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double sum = 0.0;
    for (size_t j = begin; j <= i; ++j) sum += x[j];
    out[i] = sum / denominator;
  }
}

void rolling_std(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_std");
  if (window < 2) {  // sample std (ddof=1) is undefined for a single observation
    fill_nan(out, n);
    return;
  }
  const double denominator = static_cast<double>(window);
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double sum = 0.0;
    for (size_t j = begin; j <= i; ++j) sum += x[j];
    const double mean = sum / denominator;
    double squared = 0.0;
    for (size_t j = begin; j <= i; ++j) {
      const double delta = x[j] - mean;
      squared += delta * delta;
    }
    double variance = squared / static_cast<double>(window - 1);
    if (variance < 0.0) variance = 0.0;  // guard against -0 / rounding
    out[i] = std::sqrt(variance);
  }
}

void rolling_min(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_min");
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double best = x[begin];
    for (size_t j = begin + 1; j <= i; ++j) best = std::min(best, x[j]);
    out[i] = best;
  }
}

void rolling_max(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_max");
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double best = x[begin];
    for (size_t j = begin + 1; j <= i; ++j) best = std::max(best, x[j]);
    out[i] = best;
  }
}

void rolling_argmax(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_argmax");
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    size_t best = 0;  // 0-based offset from the oldest window value; first max wins
    for (size_t k = 1; k < window; ++k) {
      if (x[begin + k] > x[begin + best]) best = k;
    }
    out[i] = static_cast<double>(best);
  }
}

void rolling_rank(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_rank");
  const double denominator = static_cast<double>(window);
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    const double current = x[i];
    size_t less = 0;
    size_t equal = 0;
    for (size_t j = begin; j <= i; ++j) {
      if (x[j] < current) {
        ++less;
      } else if (x[j] == current) {
        ++equal;
      }
    }
    // Average (mid-rank) percentile of the newest value, pandas rank(pct=True) compatible.
    out[i] = (static_cast<double>(less) + (static_cast<double>(equal) + 1.0) * 0.5) /
             denominator;
  }
}

void rolling_corr(const double* x, const double* y, size_t n, size_t window, double* out) {
  detail::require_series(x, n, "rolling_corr/x");
  detail::require_series(y, n, "rolling_corr/y");
  detail::require_window(window, "rolling_corr");
  detail::require_output(out, n, "rolling_corr");
  if (window < 2) {
    fill_nan(out, n);
    return;
  }
  const double denominator = static_cast<double>(window);
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1) || !detail::window_valid(y, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double sum_x = 0.0;
    double sum_y = 0.0;
    for (size_t j = begin; j <= i; ++j) {
      sum_x += x[j];
      sum_y += y[j];
    }
    const double mean_x = sum_x / denominator;
    const double mean_y = sum_y / denominator;
    double sxx = 0.0;
    double syy = 0.0;
    double sxy = 0.0;
    for (size_t j = begin; j <= i; ++j) {
      const double dx = x[j] - mean_x;
      const double dy = y[j] - mean_y;
      sxx += dx * dx;
      syy += dy * dy;
      sxy += dx * dy;
    }
    const double var_x = sxx / static_cast<double>(window - 1);
    const double var_y = syy / static_cast<double>(window - 1);
    const double scale = std::sqrt(var_x * var_y);
    if (!(scale > 0.0) || !std::isfinite(scale)) {
      out[i] = kNaNValue;
      continue;
    }
    const double corr = (sxy / static_cast<double>(window - 1)) / scale;
    out[i] = std::max(-1.0, std::min(1.0, corr));  // clamp rounding overshoot
  }
}

void rolling_cov(const double* x, const double* y, size_t n, size_t window, double* out) {
  detail::require_series(x, n, "rolling_cov/x");
  detail::require_series(y, n, "rolling_cov/y");
  detail::require_window(window, "rolling_cov");
  detail::require_output(out, n, "rolling_cov");
  if (window < 2) {
    fill_nan(out, n);
    return;
  }
  const double denominator = static_cast<double>(window);
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1) || !detail::window_valid(y, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    double sum_x = 0.0;
    double sum_y = 0.0;
    for (size_t j = begin; j <= i; ++j) {
      sum_x += x[j];
      sum_y += y[j];
    }
    const double mean_x = sum_x / denominator;
    const double mean_y = sum_y / denominator;
    double sxy = 0.0;
    for (size_t j = begin; j <= i; ++j) sxy += (x[j] - mean_x) * (y[j] - mean_y);
    out[i] = sxy / static_cast<double>(window - 1);
  }
}

void rolling_decay_linear(const double* x, size_t n, size_t window, double* out) {
  require_rolling(x, n, window, out, "rolling_decay_linear");
  const double denominator =
      static_cast<double>(window) * (static_cast<double>(window) + 1.0) * 0.5;
  for (size_t i = 0; i < n; ++i) {
    if (i + 1 < window) {
      out[i] = kNaNValue;
      continue;
    }
    const size_t begin = window_begin(i, window);
    if (!detail::window_valid(x, begin, i + 1)) {
      out[i] = kNaNValue;
      continue;
    }
    // Weight k = 1..window from oldest to newest, i.e. the newest value gets the largest
    // weight (Alpha101-style linear decay).
    double weighted = 0.0;
    for (size_t k = 0; k < window; ++k) {
      weighted += static_cast<double>(k + 1) * x[begin + k];
    }
    out[i] = weighted / denominator;
  }
}

}  // namespace qc::kernels
