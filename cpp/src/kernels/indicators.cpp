// Technical indicators over single series. Semantics: see kernels_internal.h and the notes
// on each function. All outputs are NaN whenever a required input is missing.
#include "qcore/kernels.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <vector>

#include "kernels_internal.h"

namespace qc::kernels {
namespace {

constexpr double kNaNValue = std::numeric_limits<double>::quiet_NaN();

void fill_nan(double* out, size_t n) {
  for (size_t i = 0; i < n; ++i)
    out[i] = kNaNValue;
}

void require_single(const double* x, size_t n, double* out, const char* name) {
  detail::require_series(x, n, name);
  detail::require_output(out, n, name);
}

// Exponential moving average, alpha = 2/(window+1). Seeds on the first non-NaN value;
// missing observations produce NaN and leave the state unchanged.
void ema_inplace(const double* x, size_t n, size_t window, double* out) {
  const double alpha = 2.0 / (static_cast<double>(window) + 1.0);
  bool has_state = false;
  double state = 0.0;
  for (size_t i = 0; i < n; ++i) {
    if (!detail::valid(x[i])) {
      out[i] = kNaNValue;
      continue;
    }
    if (!has_state) {
      state = x[i];
      has_state = true;
    } else {
      state += alpha * (x[i] - state);
    }
    out[i] = state;
  }
}

double rsi_from_averages(double average_gain, double average_loss) {
  if (!(average_gain > 0.0) && !(average_loss > 0.0))
    return 50.0;  // flat window: neutral
  if (!(average_loss > 0.0))
    return 100.0;
  if (!(average_gain > 0.0))
    return 0.0;
  const double rs = average_gain / average_loss;
  if (!std::isfinite(rs))
    return 100.0;
  return 100.0 - 100.0 / (1.0 + rs);
}

}  // namespace

void ma(const double* close, size_t n, size_t window, double* out) {
  rolling_mean(close, n, window, out);
}

void ema(const double* close, size_t n, size_t window, double* out) {
  require_single(close, n, out, "ema");
  detail::require_window(window, "ema");
  ema_inplace(close, n, window, out);
}

void macd(const double* close, size_t n, int fast, int slow, int signal, double* dif, double* dea,
          double* hist) {
  detail::require_series(close, n, "macd");
  detail::require_positive(fast, "macd", "fast");
  detail::require_positive(slow, "macd", "slow");
  detail::require_positive(signal, "macd", "signal");
  detail::require_output(dif, n, "macd/dif");
  detail::require_output(dea, n, "macd/dea");
  detail::require_output(hist, n, "macd/hist");
  std::vector<double> fast_ema(n, kNaNValue);
  std::vector<double> slow_ema(n, kNaNValue);
  ema_inplace(close, n, static_cast<size_t>(fast), fast_ema.data());
  ema_inplace(close, n, static_cast<size_t>(slow), slow_ema.data());
  for (size_t i = 0; i < n; ++i) {
    dif[i] = (detail::valid(fast_ema[i]) && detail::valid(slow_ema[i])) ? fast_ema[i] - slow_ema[i]
                                                                        : kNaNValue;
  }
  // Signal line is an EMA of DIF; DIF is NaN during warm-up and ema_inplace seeds on the
  // first valid value (index 0 here because both EMAs start at close[0]).
  ema_inplace(dif, n, static_cast<size_t>(signal), dea);
  for (size_t i = 0; i < n; ++i) {
    hist[i] = (detail::valid(dif[i]) && detail::valid(dea[i])) ? dif[i] - dea[i] : kNaNValue;
  }
}

void rsi(const double* close, size_t n, size_t window, double* out) {
  require_single(close, n, out, "rsi");
  detail::require_window(window, "rsi");
  fill_nan(out, n);
  if (n <= window)
    return;  // need window changes => window + 1 closes
  // Seed with the first fully valid run of window + 1 closes (simple average of changes).
  std::size_t seed = n;  // sentinel
  for (std::size_t s = 0; s + window < n; ++s) {
    bool ok = true;
    for (std::size_t j = s; j <= s + window; ++j) {
      if (!detail::valid(close[j])) {
        ok = false;
        break;
      }
    }
    if (ok) {
      seed = s;
      break;
    }
  }
  if (seed == n)
    return;
  double average_gain = 0.0;
  double average_loss = 0.0;
  for (std::size_t j = seed + 1; j <= seed + window; ++j) {
    const double change = close[j] - close[j - 1];
    if (change > 0.0) {
      average_gain += change;
    } else {
      average_loss -= change;
    }
  }
  const double denominator = static_cast<double>(window);
  average_gain /= denominator;
  average_loss /= denominator;
  out[seed + window] = rsi_from_averages(average_gain, average_loss);
  // Wilder smoothing afterwards; a missing close yields NaN and preserves the state.
  for (std::size_t i = seed + window + 1; i < n; ++i) {
    if (!detail::valid(close[i]) || !detail::valid(close[i - 1]))
      continue;
    const double change = close[i] - close[i - 1];
    const double gain = change > 0.0 ? change : 0.0;
    const double loss = change < 0.0 ? -change : 0.0;
    average_gain = (average_gain * (denominator - 1.0) + gain) / denominator;
    average_loss = (average_loss * (denominator - 1.0) + loss) / denominator;
    out[i] = rsi_from_averages(average_gain, average_loss);
  }
}

void kdj(const double* high, const double* low, const double* close, size_t n, int k_period,
         int d_period, int j_period, double* k, double* d, double* j) {
  detail::require_series(high, n, "kdj/high");
  detail::require_series(low, n, "kdj/low");
  detail::require_series(close, n, "kdj/close");
  detail::require_positive(k_period, "kdj", "k_period");
  detail::require_positive(d_period, "kdj", "d_period");
  detail::require_positive(j_period, "kdj", "j_period");
  detail::require_output(k, n, "kdj/k");
  detail::require_output(d, n, "kdj/d");
  detail::require_output(j, n, "kdj/j");
  fill_nan(k, n);
  fill_nan(d, n);
  fill_nan(j, n);
  const std::size_t window = static_cast<std::size_t>(k_period);
  if (n < window)
    return;
  const double k_alpha = 1.0 / static_cast<double>(k_period);
  const double d_alpha = 1.0 / static_cast<double>(d_period);
  double k_state = 50.0;
  double d_state = 50.0;
  bool seeded = false;
  for (size_t i = window - 1; i < n; ++i) {
    const size_t begin = i + 1 - window;
    if (!detail::window_valid(high, begin, i + 1) || !detail::window_valid(low, begin, i + 1) ||
        !detail::valid(close[i])) {
      continue;  // output stays NaN, K/D state is preserved
    }
    double hh = high[begin];
    double ll = low[begin];
    for (size_t w = begin + 1; w <= i; ++w) {
      hh = std::max(hh, high[w]);
      ll = std::min(ll, low[w]);
    }
    const double rsv = (hh > ll) ? 100.0 * (close[i] - ll) / (hh - ll) : 50.0;
    if (!seeded) {
      k_state = 50.0;
      d_state = 50.0;
      seeded = true;
    }
    k_state = (1.0 - k_alpha) * k_state + k_alpha * rsv;
    d_state = (1.0 - d_alpha) * d_state + d_alpha * k_state;
    k[i] = k_state;
    d[i] = d_state;
    j[i] = static_cast<double>(j_period) * k_state - static_cast<double>(j_period - 1) * d_state;
  }
}

void boll(const double* close, size_t n, size_t window, double n_std, double* mid, double* upper,
          double* lower) {
  detail::require_series(close, n, "boll");
  detail::require_window(window, "boll");
  if (!std::isfinite(n_std) || n_std < 0.0) {
    throw std::invalid_argument("boll: n_std must be finite and >= 0");
  }
  detail::require_output(mid, n, "boll/mid");
  detail::require_output(upper, n, "boll/upper");
  detail::require_output(lower, n, "boll/lower");
  rolling_mean(close, n, window, mid);
  // Sample std (ddof=1), consistent with rolling_std; undefined for window == 1.
  rolling_std(close, n, window, upper);
  for (size_t i = 0; i < n; ++i) {
    if (!detail::valid(mid[i]) || !detail::valid(upper[i])) {
      upper[i] = kNaNValue;
      lower[i] = kNaNValue;
      continue;
    }
    const double sigma = upper[i];
    upper[i] = mid[i] + n_std * sigma;
    lower[i] = mid[i] - n_std * sigma;
  }
}

void atr(const double* high, const double* low, const double* close, size_t n, size_t window,
         double* out) {
  detail::require_series(high, n, "atr/high");
  detail::require_series(low, n, "atr/low");
  detail::require_series(close, n, "atr/close");
  detail::require_window(window, "atr");
  detail::require_output(out, n, "atr");
  fill_nan(out, n);
  if (n <= window)
    return;  // needs TR[1..window] for the seed
  auto true_range = [&](size_t index) -> double {
    if (!detail::valid(high[index]) || !detail::valid(low[index]) ||
        !detail::valid(close[index - 1])) {
      return kNaNValue;
    }
    const double range = high[index] - low[index];
    const double gap_high = std::abs(high[index] - close[index - 1]);
    const double gap_low = std::abs(low[index] - close[index - 1]);
    return std::max(range, std::max(gap_high, gap_low));
  };
  double atr_state = 0.0;
  bool seeded = false;
  const double denominator = static_cast<double>(window);
  for (size_t i = window; i < n; ++i) {
    const double tr = true_range(i);
    if (!seeded) {
      // Seed on the first fully valid window of true ranges ending at i.
      double sum = 0.0;
      bool ok = true;
      for (size_t j = i + 1 - window; j <= i; ++j) {
        const double candidate = (j == i) ? tr : true_range(j);
        if (!detail::valid(candidate)) {
          ok = false;
          break;
        }
        sum += candidate;
      }
      if (!ok)
        continue;
      atr_state = sum / denominator;
      seeded = true;
      out[i] = atr_state;
      continue;
    }
    if (!detail::valid(tr))
      continue;  // NaN stays, ATR state preserved
    atr_state = (atr_state * (denominator - 1.0) + tr) / denominator;
    out[i] = atr_state;
  }
}

void obv(const double* close, const double* volume, size_t n, double* out) {
  detail::require_series(close, n, "obv/close");
  detail::require_series(volume, n, "obv/volume");
  detail::require_output(out, n, "obv");
  if (n == 0)
    return;
  // OBV is defined as starting from zero on the first observation.
  double state = 0.0;
  out[0] = 0.0;
  for (size_t i = 1; i < n; ++i) {
    if (!detail::valid(close[i]) || !detail::valid(close[i - 1]) || !detail::valid(volume[i])) {
      out[i] = kNaNValue;
      continue;
    }
    if (close[i] > close[i - 1]) {
      state += volume[i];
    } else if (close[i] < close[i - 1]) {
      state -= volume[i];
    }
    out[i] = state;
  }
}

void cci(const double* high, const double* low, const double* close, size_t n, size_t window,
         double* out) {
  detail::require_series(high, n, "cci/high");
  detail::require_series(low, n, "cci/low");
  detail::require_series(close, n, "cci/close");
  detail::require_window(window, "cci");
  detail::require_output(out, n, "cci");
  fill_nan(out, n);
  if (n < window)
    return;
  const double denominator = static_cast<double>(window);
  std::vector<double> typical;  // reused per window; no cross-window state
  typical.reserve(window);
  for (size_t i = window - 1; i < n; ++i) {
    const size_t begin = i + 1 - window;
    if (!detail::window_valid(high, begin, i + 1) || !detail::window_valid(low, begin, i + 1) ||
        !detail::window_valid(close, begin, i + 1)) {
      continue;
    }
    typical.clear();
    double sum = 0.0;
    for (size_t j = begin; j <= i; ++j) {
      const double tp = (high[j] + low[j] + close[j]) / 3.0;
      typical.push_back(tp);
      sum += tp;
    }
    const double mean = sum / denominator;
    double mean_deviation = 0.0;
    for (const double tp : typical)
      mean_deviation += std::abs(tp - mean);
    mean_deviation /= denominator;
    if (!(mean_deviation > 0.0) || !std::isfinite(mean_deviation))
      continue;
    out[i] = (typical.back() - mean) / (0.015 * mean_deviation);
  }
}

}  // namespace qc::kernels
