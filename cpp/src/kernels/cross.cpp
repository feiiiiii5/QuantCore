// Cross-sectional kernels. Semantics: see kernels_internal.h plus the per-function notes.
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

struct RankedValue {
  double value;
  std::size_t index;
};

// Non-NaN observations in ascending index order, then stable-sorted by value.
std::vector<RankedValue> gather_sorted(const double* x, std::size_t n) {
  std::vector<RankedValue> items;
  items.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    if (detail::valid(x[i])) items.push_back({x[i], i});
  }
  std::sort(items.begin(), items.end(),
            [](const RankedValue& a, const RankedValue& b) { return a.value < b.value; });
  return items;
}

void require_cross(const double* x, std::size_t n, double* out, const char* name) {
  detail::require_series(x, n, name);
  detail::require_output(out, n, name);
}

double median_sorted(const std::vector<double>& sorted) {
  const std::size_t m = sorted.size();
  if (m == 0) return kNaNValue;
  if ((m % 2U) == 1U) return sorted[m / 2];
  return (sorted[m / 2 - 1] + sorted[m / 2]) * 0.5;
}

}  // namespace

void cross_rank(const double* x, size_t n, double* out) {
  require_cross(x, n, out, "cross_rank");
  for (std::size_t i = 0; i < n; ++i) out[i] = kNaNValue;
  const std::vector<RankedValue> items = gather_sorted(x, n);
  const std::size_t m = items.size();
  if (m == 0) return;
  if (m == 1) {
    out[items[0].index] = 0.5;  // a single name is neutral
    return;
  }
  // Ties share their average (mid) rank; rank 1 -> 0.0 and rank m -> 1.0.
  std::size_t start = 0;
  while (start < m) {
    std::size_t end = start;
    while (end + 1 < m && items[end + 1].value == items[start].value) ++end;
    const double average_rank = (static_cast<double>(start) + static_cast<double>(end)) * 0.5 + 1.0;
    const double pct = (average_rank - 1.0) / static_cast<double>(m - 1);
    for (std::size_t k = start; k <= end; ++k) out[items[k].index] = pct;
    start = end + 1;
  }
}

void cross_zscore(const double* x, size_t n, double* out) {
  require_cross(x, n, out, "cross_zscore");
  for (std::size_t i = 0; i < n; ++i) out[i] = kNaNValue;
  std::vector<std::size_t> valid_index;
  valid_index.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    if (detail::valid(x[i])) valid_index.push_back(i);
  }
  const std::size_t m = valid_index.size();
  if (m < 2) return;  // sample std (ddof=1) undefined
  double sum = 0.0;
  for (const std::size_t i : valid_index) sum += x[i];
  const double mean = sum / static_cast<double>(m);
  if (!std::isfinite(mean)) return;
  double squared = 0.0;
  for (const std::size_t i : valid_index) {
    const double delta = x[i] - mean;
    squared += delta * delta;
  }
  const double stddev = std::sqrt(squared / static_cast<double>(m - 1));
  if (!(stddev > 0.0) || !std::isfinite(stddev)) return;  // constant cross-section -> NaN
  for (const std::size_t i : valid_index) out[i] = (x[i] - mean) / stddev;
}

void cross_mad_winsor(const double* x, size_t n, double n_mad, double* out) {
  if (!std::isfinite(n_mad) || !(n_mad > 0.0)) {
    throw std::invalid_argument("cross_mad_winsor: n_mad must be finite and > 0");
  }
  require_cross(x, n, out, "cross_mad_winsor");
  for (std::size_t i = 0; i < n; ++i) out[i] = kNaNValue;
  const std::vector<RankedValue> items = gather_sorted(x, n);
  const std::size_t m = items.size();
  if (m == 0) return;
  std::vector<double> values;
  values.reserve(m);
  for (const RankedValue& item : items) values.push_back(item.value);
  const double median = median_sorted(values);
  if (!std::isfinite(median)) {
    // Non-finite centre: there is no meaningful robust scale, leave values untouched.
    for (const RankedValue& item : items) out[item.index] = item.value;
    return;
  }
  std::vector<double> deviations;
  deviations.reserve(m);
  for (const double value : values) deviations.push_back(std::abs(value - median));
  std::sort(deviations.begin(), deviations.end());
  const double mad = median_sorted(deviations);
  if (!(mad > 0.0) || !std::isfinite(mad)) {
    // More than half of the cross-section is identical: nothing to winsorize.
    for (const RankedValue& item : items) out[item.index] = item.value;
    return;
  }
  // Raw MAD (no 1.4826 normal-consistency factor): the caller chooses n_mad explicitly.
  const double lower = median - n_mad * mad;
  const double upper = median + n_mad * mad;
  for (const RankedValue& item : items) {
    out[item.index] = std::max(lower, std::min(upper, item.value));
  }
}

void cross_quantile(const double* x, size_t n, int q, int nq, double* out) {
  if (nq < 1) throw std::invalid_argument("cross_quantile: nq must be >= 1");
  if (q < 0 || q >= nq) throw std::invalid_argument("cross_quantile: q must be in [0, nq-1]");
  // Per the qcore/kernels.h contract q is reserved (validated only); out[i] is the
  // 0..nq-1 equal-frequency bucket index of x[i].
  (void)q;
  require_cross(x, n, out, "cross_quantile");
  for (std::size_t i = 0; i < n; ++i) out[i] = kNaNValue;
  const std::vector<RankedValue> items = gather_sorted(x, n);
  const std::size_t m = items.size();
  if (m == 0) return;
  std::size_t start = 0;
  while (start < m) {
    std::size_t end = start;
    while (end + 1 < m && items[end + 1].value == items[start].value) ++end;
    // Average 0-based ordinal position of the tie group, mapped to an equal-frequency
    // bucket: bucket = min(nq-1, floor(ordinal * nq / m)).
    const double ordinal = (static_cast<double>(start) + static_cast<double>(end)) * 0.5;
    double bucket = std::floor(ordinal * static_cast<double>(nq) / static_cast<double>(m));
    if (bucket < 0.0) bucket = 0.0;
    const double max_bucket = static_cast<double>(nq - 1);
    if (bucket > max_bucket) bucket = max_bucket;
    for (std::size_t k = start; k <= end; ++k) {
      out[items[k].index] = bucket;
    }
    start = end + 1;
  }
}

}  // namespace qc::kernels
