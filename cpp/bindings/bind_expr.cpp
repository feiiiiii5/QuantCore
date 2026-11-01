#include <pybind11/gil.h>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cstddef>
#include <string>
#include <vector>

#include "../src/expr/expr_internal.h"
#include "qcore/expr.h"
#include "qcore/panel.h"

namespace py = pybind11;

namespace {

std::string expression_repr(const qc::Expression& expression) {
  const std::string& source = expression.source();
  return "Expression(" + (source.empty() ? std::string("<empty>") : source) + ")";
}

qc::Layout parse_layout(const py::object& layout) {
  if (layout.is_none()) return qc::Layout::SecTime;
  if (py::isinstance<qc::Layout>(layout)) return py::cast<qc::Layout>(layout);
  if (py::isinstance<py::str>(layout)) {
    std::string key;
    for (const char c : py::cast<std::string>(layout)) {
      if (c == '_' || c == '-' || c == ' ') continue;
      key.push_back(c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c);
    }
    if (key == "sectime") return qc::Layout::SecTime;
    if (key == "timesec") return qc::Layout::TimeSec;
    throw py::value_error("layout must be 'sec_time'/'time_sec' or qc.Layout, got '" +
                          py::cast<std::string>(layout) + "'");
  }
  throw py::type_error("layout must be 'sec_time'/'time_sec' or qc.Layout");
}

// Whole-panel evaluation used by Python research loops: one C++ call instead of
// n_sec * n_time Python calls into Expression.eval.
py::array_t<double> evaluate_panel(const qc::Panel& panel, const qc::Expression& expression,
                                   const py::object& layout_object) {
  const qc::Layout layout = parse_layout(layout_object);
  const auto n_sec = static_cast<py::ssize_t>(panel.n_sec());
  const auto n_time = static_cast<py::ssize_t>(panel.n_time());
  std::vector<py::ssize_t> shape;
  if (layout == qc::Layout::SecTime) {
    shape = {n_sec, n_time};
  } else {
    shape = {n_time, n_sec};
  }
  py::array_t<double> array(shape);
  if (panel.n_sec() == 0 || panel.n_time() == 0) return array;
  py::buffer_info buffer = array.request();
  auto* data = static_cast<double*>(buffer.ptr);
  qc::expr::Program program;
  if (!expression.source().empty()) program = qc::expr::compile(expression.source());
  {
    py::gil_scoped_release release;
    qc::expr::eval_panel_values(program, panel, layout, data);
  }
  return array;
}

}  // namespace

void bind_expr(py::module_& m) {
  py::class_<qc::Expression>(
      m, "Expression",
      "Compiled factor-expression DAG: parse once, evaluate many times.\n\n"
      "Fields: open, high, low, close, volume, amount, returns (returns is derived from\n"
      "close when the panel has no explicit returns column).\n"
      "Operators: + - * /, comparisons (>, <, >=, <=, ==, !=), and/or/not,\n"
      "ts_mean/ts_std/ts_sum/ts_min/ts_max/ts_rank(x, n), rank(x), zscore(x),\n"
      "delay(x, n), abs(x), log(x), sqrt(x), min(a, b), max(a, b), pow(a, b).\n"
      "Semantics: NaN means missing and propagates through every operator (comparisons\n"
      "included); logical truthiness is value != 0; division by zero, log(x<=0),\n"
      "sqrt(x<0) and invalid pow are NaN; overflow to inf is normalised to NaN.\n"
      "ts_* need the whole window [t-n+1, t] present and NaN-free (ts_std ddof=1;\n"
      "ts_rank is a [0,1] percentile of the newest value, average ties).\n"
      "rank/zscore are cross-sectional over the non-NaN securities at that time.\n"
      "Windows that are not fully covered and out-of-range (sec, time) return NaN;\n"
      "syntax errors raise ValueError.")
      .def(py::init<>(), "Empty expression; eval()/eval_cross() return NaN.")
      .def_static("parse", &qc::Expression::parse, py::arg("source"),
                  "Compile `source` into a common-subexpression-eliminated DAG.")
      .def(
          "eval",
          [](const qc::Expression& expression, const qc::Panel& panel, size_t sec, size_t time) {
            py::gil_scoped_release release;
            return expression.eval(panel, sec, time);
          },
          py::arg("panel"), py::arg("sec"), py::arg("time"),
          "Evaluate the expression at one (sec, time) point.")
      .def(
          "eval_cross",
          [](const qc::Expression& expression, const qc::Panel& panel, size_t sec, size_t time) {
            py::gil_scoped_release release;
            return expression.eval_cross(panel, sec, time);
          },
          py::arg("panel"), py::arg("sec"), py::arg("time"),
          "Evaluate at (sec, time) through the cross-section at `time`; use this for "
          "rank()/zscore() expressions.")
      .def("explain", &qc::Expression::explain,
           "Readable AST/DAG summary; the node count exposes CSE sharing.")
      .def_property_readonly("source", &qc::Expression::source, "Original expression text.")
      .def("__repr__", &expression_repr);

  m.def("evaluate_panel", &evaluate_panel, py::arg("panel"), py::arg("expr"),
        py::arg("layout") = py::none(),
        "Evaluate `expr` over every (sec, time) of `panel` in one C++ pass and return a\n"
        "float64 array in the requested layout:\n"
        "  'sec_time' (default, or qc.Layout.SecTime) -> (n_sec, n_time)\n"
        "  'time_sec'  (or qc.Layout.TimeSec)         -> (n_time, n_sec)\n"
        "Same NaN semantics as Expression.eval/eval_cross.");
}
