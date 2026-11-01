#pragma once
// Shared helpers and the documented semantics of the qcore kernel family.
//
// Conventions (apply to every kernel in qcore/kernels.h):
//  * NaN means "missing"; any output slot whose inputs are missing is NaN.
//  * Rolling kernels only produce a value at i when the full window [i-window+1, i] exists
//    (i + 1 >= window) AND every value in that window is non-NaN. Warm-up rows are NaN.
//  * Rolling reductions accumulate left-to-right (oldest -> newest) in double precision;
//    the std/cov/corr two-pass form (mean first, then deviations) keeps results
//    deterministic and independent of worker count. No FMA contraction (-ffp-contract=off).
//  * Exponential indicators skip missing observations: a missing input yields NaN output
//    and leaves the internal state unchanged.
//  * All functions throw std::invalid_argument for window/pointer/parameter misuse and
//    treat n == 0 as a no-op.
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>

#include "qcore/types.h"

namespace qc::kernels::detail {

inline bool valid(double v) { return !std::isnan(v); }

inline void require_series(const double* x, size_t n, const char* name) {
  if (n != 0 && x == nullptr) {
    throw std::invalid_argument(std::string(name) + ": null series pointer");
  }
}

inline void require_output(double* out, size_t n, const char* name) {
  if (n != 0 && out == nullptr) {
    throw std::invalid_argument(std::string(name) + ": null output pointer");
  }
}

inline void require_window(size_t window, const char* name) {
  if (window == 0) {
    throw std::invalid_argument(std::string(name) + ": window must be >= 1");
  }
}

inline void require_positive(int value, const char* name, const char* param) {
  if (value <= 0) {
    throw std::invalid_argument(std::string(name) + ": " + param + " must be >= 1");
  }
}

// True when [begin, end) is fully populated with finite-or-infinite (i.e. non-NaN) values.
inline bool window_valid(const double* x, size_t begin, size_t end) {
  for (size_t j = begin; j < end; ++j) {
    if (!valid(x[j])) return false;
  }
  return true;
}

}  // namespace qc::kernels::detail
