// pybind11 bindings for the qcore kernel family, exposed as the `_qcore.kernels` submodule.
// Every kernel wrapper allocates its NumPy output under the GIL and then releases the GIL
// for the numeric work. Inputs are cast to C-contiguous float64 (one copy only if needed).
// Returned panel-wide arrays follow storage order: SecTime -> (n_sec, n_time),
// TimeSec -> (n_time, n_sec).
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include "qcore/kernels.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace py = pybind11;

namespace {

using DoubleArray = py::array_t<double, py::array::c_style | py::array::forcecast>;

struct Series {
  const double* data = nullptr;
  py::ssize_t size = 0;
};

Series as_series(const DoubleArray& array, const char* name) {
  const auto info = array.request();
  if (info.ndim != 1)
    throw py::value_error(std::string(name) + " must be a 1-D array");
  return {static_cast<const double*>(info.ptr), static_cast<py::ssize_t>(info.size)};
}

py::array_t<double> allocate1(py::ssize_t n) {
  return py::array_t<double>(n);
}

template <typename Fn>
py::array_t<double> apply_unary(const DoubleArray& x, Fn&& fn) {
  const Series a = as_series(x, "x");
  py::array_t<double> out = allocate1(a.size);
  const auto info = out.request();
  const double* xp = a.data;
  auto* op = static_cast<double*>(info.ptr);
  const auto n = static_cast<std::size_t>(a.size);
  {
    py::gil_scoped_release release;
    fn(xp, n, op);
  }
  return out;
}

template <typename Fn>
py::array_t<double> apply_binary(const DoubleArray& x, const DoubleArray& y, Fn&& fn) {
  const Series a = as_series(x, "x");
  const Series b = as_series(y, "y");
  if (a.size != b.size)
    throw py::value_error("x and y must have the same length");
  py::array_t<double> out = allocate1(a.size);
  const auto info = out.request();
  const double* xp = a.data;
  const double* yp = b.data;
  auto* op = static_cast<double*>(info.ptr);
  const auto n = static_cast<std::size_t>(a.size);
  {
    py::gil_scoped_release release;
    fn(xp, yp, n, op);
  }
  return out;
}

template <typename Fn>
py::array_t<double> apply_ternary(const DoubleArray& x, const DoubleArray& y, const DoubleArray& z,
                                  Fn&& fn) {
  const Series a = as_series(x, "x");
  const Series b = as_series(y, "y");
  const Series c = as_series(z, "z");
  if (a.size != b.size || a.size != c.size) {
    throw py::value_error("input series must have the same length");
  }
  py::array_t<double> out = allocate1(a.size);
  const auto info = out.request();
  const double* xp = a.data;
  const double* yp = b.data;
  const double* zp = c.data;
  auto* op = static_cast<double*>(info.ptr);
  const auto n = static_cast<std::size_t>(a.size);
  {
    py::gil_scoped_release release;
    fn(xp, yp, zp, n, op);
  }
  return out;
}

// Copies a flat output buffer into a 2-D array in storage order.
py::array_t<double> flat_to_array(const std::vector<double>& values, qc::Layout layout,
                                  std::size_t n_sec, std::size_t n_time) {
  const std::vector<py::ssize_t> shape =
      layout == qc::Layout::SecTime ? std::vector<py::ssize_t>{static_cast<py::ssize_t>(n_sec),
                                                               static_cast<py::ssize_t>(n_time)}
                                    : std::vector<py::ssize_t>{static_cast<py::ssize_t>(n_time),
                                                               static_cast<py::ssize_t>(n_sec)};
  py::array_t<double> array(shape);
  auto info = array.request();
  if (!values.empty()) {
    std::memcpy(info.ptr, values.data(), values.size() * sizeof(double));
  }
  return array;
}

qc::Layout parse_layout(const py::object& layout) {
  if (py::isinstance<qc::Layout>(layout))
    return py::cast<qc::Layout>(layout);
  if (py::isinstance<py::str>(layout)) {
    const std::string text = py::cast<std::string>(layout);
    std::string key;
    for (const char c : text) {
      if (c == '_' || c == '-' || c == ' ')
        continue;
      if (c >= 'A' && c <= 'Z') {
        key.push_back(static_cast<char>(c - 'A' + 'a'));
      } else {
        key.push_back(c);
      }
    }
    if (key == "sectime")
      return qc::Layout::SecTime;
    if (key == "timesec")
      return qc::Layout::TimeSec;
  }
  throw py::value_error("layout must be 'sec_time' or 'time_sec' (or a qcore.Layout)");
}

bool kernels_ready_probe() {
  try {
    const double x[4] = {1.0, 2.0, 3.0, 4.0};
    double mean[4] = {0.0, 0.0, 0.0, 0.0};
    qc::kernels::rolling_mean(x, 4, 2, mean);
    if (!std::isnan(mean[0]) || mean[1] != 1.5 || mean[2] != 2.5 || mean[3] != 3.5)
      return false;
    const double y[3] = {3.0, 1.0, 2.0};
    double rank[3] = {0.0, 0.0, 0.0};
    qc::kernels::cross_rank(y, 3, rank);
    if (rank[0] != 1.0 || rank[1] != 0.0 || rank[2] != 0.5)
      return false;
    double smooth[3] = {0.0, 0.0, 0.0};
    qc::kernels::ema(x, 3, 2, smooth);
    return std::fabs(smooth[0] - 1.0) < 1e-12 && std::fabs(smooth[2] - 2.5555555555555554) < 1e-12;
  } catch (...) {
    return false;
  }
}

}  // namespace

void bind_kernels(py::module_& m) {
  py::module_ kernels =
      m.def_submodule("kernels", "Rolling, cross-sectional and indicator kernels.");

  // --- rolling -------------------------------------------------------------
  kernels.def(
      "rolling_sum",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_sum(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"));
  kernels.def(
      "rolling_mean",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_mean(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"));
  kernels.def(
      "rolling_std",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_std(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"), "Sample standard deviation (ddof=1).");
  kernels.def(
      "rolling_min",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_min(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"));
  kernels.def(
      "rolling_max",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_max(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"));
  kernels.def(
      "rolling_argmax",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_argmax(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"), "Offset of the first maximum from the oldest window value.");
  kernels.def(
      "rolling_rank",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_rank(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"), "Average-rank percentile of the newest window value.");
  kernels.def(
      "rolling_corr",
      [](const DoubleArray& x, const DoubleArray& y, std::size_t window) {
        return apply_binary(x, y,
                            [window](const double* a, const double* b, std::size_t n, double* out) {
                              qc::kernels::rolling_corr(a, b, n, window, out);
                            });
      },
      py::arg("x"), py::arg("y"), py::arg("window"));
  kernels.def(
      "rolling_cov",
      [](const DoubleArray& x, const DoubleArray& y, std::size_t window) {
        return apply_binary(x, y,
                            [window](const double* a, const double* b, std::size_t n, double* out) {
                              qc::kernels::rolling_cov(a, b, n, window, out);
                            });
      },
      py::arg("x"), py::arg("y"), py::arg("window"), "Sample covariance (ddof=1).");
  kernels.def(
      "rolling_decay_linear",
      [](const DoubleArray& x, std::size_t window) {
        return apply_unary(x, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rolling_decay_linear(a, n, window, out);
        });
      },
      py::arg("x"), py::arg("window"));

  // --- cross-sectional ----------------------------------------------------
  kernels.def(
      "cross_rank",
      [](const DoubleArray& x) {
        return apply_unary(x, [](const double* a, std::size_t n, double* out) {
          qc::kernels::cross_rank(a, n, out);
        });
      },
      py::arg("x"), "Percentile rank in [0, 1]; NaN stays NaN.");
  kernels.def(
      "cross_zscore",
      [](const DoubleArray& x) {
        return apply_unary(x, [](const double* a, std::size_t n, double* out) {
          qc::kernels::cross_zscore(a, n, out);
        });
      },
      py::arg("x"));
  kernels.def(
      "cross_mad_winsor",
      [](const DoubleArray& x, double n_mad) {
        return apply_unary(x, [n_mad](const double* a, std::size_t n, double* out) {
          qc::kernels::cross_mad_winsor(a, n, n_mad, out);
        });
      },
      py::arg("x"), py::arg("n_mad") = 3.0);
  kernels.def(
      "cross_quantile",
      [](const DoubleArray& x, int q, int nq) {
        return apply_unary(x, [q, nq](const double* a, std::size_t n, double* out) {
          qc::kernels::cross_quantile(a, n, q, nq, out);
        });
      },
      py::arg("x"), py::arg("q") = 0, py::arg("nq") = 10,
      "Equal-frequency bucket index in [0, nq-1]; q is reserved/validated.");

  // --- technical indicators ----------------------------------------------
  kernels.def(
      "ma",
      [](const DoubleArray& close, std::size_t window) {
        return apply_unary(close, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::ma(a, n, window, out);
        });
      },
      py::arg("close"), py::arg("window"));
  kernels.def(
      "ema",
      [](const DoubleArray& close, std::size_t window) {
        return apply_unary(close, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::ema(a, n, window, out);
        });
      },
      py::arg("close"), py::arg("window"));
  kernels.def(
      "macd",
      [](const DoubleArray& close, int fast, int slow, int signal) {
        const Series s = as_series(close, "close");
        py::array_t<double> dif = allocate1(s.size);
        py::array_t<double> dea = allocate1(s.size);
        py::array_t<double> hist = allocate1(s.size);
        const auto i1 = dif.request();
        const auto i2 = dea.request();
        const auto i3 = hist.request();
        const double* cp = s.data;
        auto* p1 = static_cast<double*>(i1.ptr);
        auto* p2 = static_cast<double*>(i2.ptr);
        auto* p3 = static_cast<double*>(i3.ptr);
        const auto n = static_cast<std::size_t>(s.size);
        {
          py::gil_scoped_release release;
          qc::kernels::macd(cp, n, fast, slow, signal, p1, p2, p3);
        }
        return py::make_tuple(dif, dea, hist);
      },
      py::arg("close"), py::arg("fast") = 12, py::arg("slow") = 26, py::arg("signal") = 9,
      "Returns (dif, dea, hist); hist = dif - dea.");
  kernels.def(
      "rsi",
      [](const DoubleArray& close, std::size_t window) {
        return apply_unary(close, [window](const double* a, std::size_t n, double* out) {
          qc::kernels::rsi(a, n, window, out);
        });
      },
      py::arg("close"), py::arg("window"));
  kernels.def(
      "kdj",
      [](const DoubleArray& high, const DoubleArray& low, const DoubleArray& close, int k_period,
         int d_period, int j_period) {
        const Series h = as_series(high, "high");
        const Series l = as_series(low, "low");
        const Series c = as_series(close, "close");
        if (h.size != l.size || h.size != c.size) {
          throw py::value_error("high, low and close must have the same length");
        }
        py::array_t<double> k = allocate1(h.size);
        py::array_t<double> d = allocate1(h.size);
        py::array_t<double> j = allocate1(h.size);
        const auto i1 = k.request();
        const auto i2 = d.request();
        const auto i3 = j.request();
        const double* hp = h.data;
        const double* lp = l.data;
        const double* cp = c.data;
        auto* p1 = static_cast<double*>(i1.ptr);
        auto* p2 = static_cast<double*>(i2.ptr);
        auto* p3 = static_cast<double*>(i3.ptr);
        const auto n = static_cast<std::size_t>(h.size);
        {
          py::gil_scoped_release release;
          qc::kernels::kdj(hp, lp, cp, n, k_period, d_period, j_period, p1, p2, p3);
        }
        return py::make_tuple(k, d, j);
      },
      py::arg("high"), py::arg("low"), py::arg("close"), py::arg("k_period") = 9,
      py::arg("d_period") = 3, py::arg("j_period") = 3);
  kernels.def(
      "boll",
      [](const DoubleArray& close, std::size_t window, double n_std) {
        const Series s = as_series(close, "close");
        py::array_t<double> mid = allocate1(s.size);
        py::array_t<double> upper = allocate1(s.size);
        py::array_t<double> lower = allocate1(s.size);
        const auto i1 = mid.request();
        const auto i2 = upper.request();
        const auto i3 = lower.request();
        const double* cp = s.data;
        auto* p1 = static_cast<double*>(i1.ptr);
        auto* p2 = static_cast<double*>(i2.ptr);
        auto* p3 = static_cast<double*>(i3.ptr);
        const auto n = static_cast<std::size_t>(s.size);
        {
          py::gil_scoped_release release;
          qc::kernels::boll(cp, n, window, n_std, p1, p2, p3);
        }
        return py::make_tuple(mid, upper, lower);
      },
      py::arg("close"), py::arg("window") = 20, py::arg("n_std") = 2.0);
  kernels.def(
      "atr",
      [](const DoubleArray& high, const DoubleArray& low, const DoubleArray& close,
         std::size_t window) {
        return apply_ternary(
            high, low, close,
            [window](const double* h, const double* l, const double* c, std::size_t n,
                     double* out) { qc::kernels::atr(h, l, c, n, window, out); });
      },
      py::arg("high"), py::arg("low"), py::arg("close"), py::arg("window"));
  kernels.def(
      "obv",
      [](const DoubleArray& close, const DoubleArray& volume) {
        return apply_binary(close, volume,
                            [](const double* c, const double* v, std::size_t n, double* out) {
                              qc::kernels::obv(c, v, n, out);
                            });
      },
      py::arg("close"), py::arg("volume"));
  kernels.def(
      "cci",
      [](const DoubleArray& high, const DoubleArray& low, const DoubleArray& close,
         std::size_t window) {
        return apply_ternary(
            high, low, close,
            [window](const double* h, const double* l, const double* c, std::size_t n,
                     double* out) { qc::kernels::cci(h, l, c, n, window, out); });
      },
      py::arg("high"), py::arg("low"), py::arg("close"), py::arg("window"));

  // --- panel-wide convenience --------------------------------------------
  kernels.def(
      "rolling_panel",
      [](const qc::Panel& panel, const std::string& field, std::size_t window,
         const std::string& op, const py::object& out_layout) {
        const qc::Layout layout = parse_layout(out_layout);
        std::vector<double> out;
        const std::size_t n_sec = panel.n_sec();
        const std::size_t n_time = panel.n_time();
        {
          py::gil_scoped_release release;
          qc::kernels::rolling_panel(panel, field, window, op, out, layout);
        }
        return flat_to_array(out, layout, n_sec, n_time);
      },
      py::arg("panel"), py::arg("field"), py::arg("window"), py::arg("op"),
      py::arg("out_layout") = py::str("sec_time"));
  kernels.def(
      "cross_panel",
      [](const qc::Panel& panel, const std::string& field, const std::string& op,
         const py::object& out_layout) {
        const qc::Layout layout = parse_layout(out_layout);
        std::vector<double> out;
        const std::size_t n_sec = panel.n_sec();
        const std::size_t n_time = panel.n_time();
        {
          py::gil_scoped_release release;
          qc::kernels::cross_panel(panel, field, op, out, layout);
        }
        return flat_to_array(out, layout, n_sec, n_time);
      },
      py::arg("panel"), py::arg("field"), py::arg("op"),
      py::arg("out_layout") = py::str("sec_time"));

  m.def("kernels_ready", &kernels_ready_probe,
        "True when a fixed rolling/cross/EMA sample produces the expected values.");
}
