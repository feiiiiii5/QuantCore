// Panel-wide convenience wrappers: flatten a single panel field into rolling (per security)
// or cross-sectional (per date) kernel calls, then scatter into the requested output layout.
//
// Supported op strings:
//   rolling_panel: sum, mean, std, min, max, argmax, rank, decay_linear
//                  (corr/cov need a second field, so they are intentionally unsupported)
//   cross_panel:   rank, zscore, mad_winsor (n_mad = 3.0), quantile (q = 0, nq = 10 buckets)
#include "qcore/kernels.h"

#include <algorithm>
#include <cstddef>
#include <limits>
#include <string>
#include <vector>

#include "kernels_internal.h"

namespace qc::kernels {
namespace {

constexpr double kNaNValue = std::numeric_limits<double>::quiet_NaN();

using RollingFn = void (*)(const double*, size_t, size_t, double*);

struct RollingEntry {
  const char* name;
  RollingFn fn;
};

constexpr RollingEntry kRollingOps[] = {
    {"sum", &rolling_sum},   {"mean", &rolling_mean},
    {"std", &rolling_std},   {"min", &rolling_min},
    {"max", &rolling_max},   {"argmax", &rolling_argmax},
    {"rank", &rolling_rank}, {"decay_linear", &rolling_decay_linear},
};

RollingFn find_rolling_op(const std::string& op) {
  for (const RollingEntry& entry : kRollingOps) {
    if (op == entry.name)
      return entry.fn;
  }
  if (op == "corr" || op == "cov") {
    throw std::invalid_argument("rolling_panel: op '" + op + "' needs two fields; call rolling_" +
                                op + " directly");
  }
  throw std::invalid_argument("rolling_panel: unknown op '" + op + "'");
}

void require_layout(Layout layout, const char* name) {
  if (layout != Layout::SecTime && layout != Layout::TimeSec) {
    throw std::invalid_argument(std::string(name) + ": unsupported output layout");
  }
}

std::size_t out_index(Layout layout, std::size_t sec, std::size_t time, std::size_t n_sec,
                      std::size_t n_time) {
  return layout == Layout::SecTime ? sec * n_time + time : time * n_sec + sec;
}

}  // namespace

void rolling_panel(const Panel& panel, const std::string& field, size_t window,
                   const std::string& op, std::vector<double>& out, Layout out_layout) {
  detail::require_window(window, "rolling_panel");
  require_layout(out_layout, "rolling_panel");
  const RollingFn fn = find_rolling_op(op);
  const FieldView view = panel.field(field);  // throws std::runtime_error when absent
  const std::size_t n_sec = panel.n_sec();
  const std::size_t n_time = panel.n_time();
  out.assign(n_sec * n_time, kNaNValue);
  std::vector<double> series(n_time, kNaNValue);
  std::vector<double> result(n_time, kNaNValue);
  for (std::size_t sec = 0; sec < n_sec; ++sec) {
    for (std::size_t t = 0; t < n_time; ++t)
      series[t] = view.at(sec, t);
    fn(series.data(), n_time, window, result.data());
    for (std::size_t t = 0; t < n_time; ++t) {
      out[out_index(out_layout, sec, t, n_sec, n_time)] = result[t];
    }
  }
}

void cross_panel(const Panel& panel, const std::string& field, const std::string& op,
                 std::vector<double>& out, Layout out_layout) {
  require_layout(out_layout, "cross_panel");
  const FieldView view = panel.field(field);  // throws std::runtime_error when absent
  const std::size_t n_sec = panel.n_sec();
  const std::size_t n_time = panel.n_time();
  out.assign(n_sec * n_time, kNaNValue);
  std::vector<double> section(n_sec, kNaNValue);
  std::vector<double> result(n_sec, kNaNValue);
  for (std::size_t t = 0; t < n_time; ++t) {
    for (std::size_t sec = 0; sec < n_sec; ++sec)
      section[sec] = view.at(sec, t);
    if (op == "rank") {
      cross_rank(section.data(), n_sec, result.data());
    } else if (op == "zscore") {
      cross_zscore(section.data(), n_sec, result.data());
    } else if (op == "mad_winsor") {
      cross_mad_winsor(section.data(), n_sec, 3.0, result.data());
    } else if (op == "quantile") {
      cross_quantile(section.data(), n_sec, 0, 10, result.data());
    } else {
      throw std::invalid_argument("cross_panel: unknown op '" + op + "'");
    }
    for (std::size_t sec = 0; sec < n_sec; ++sec) {
      out[out_index(out_layout, sec, t, n_sec, n_time)] = result[sec];
    }
  }
}

}  // namespace qc::kernels
