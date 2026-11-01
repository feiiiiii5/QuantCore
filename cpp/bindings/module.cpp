#include <pybind11/pybind11.h>
#include "qcore/version.h"

namespace py = pybind11;
void bind_panel(py::module_& m);
void bind_kernels(py::module_& m);
void bind_engine(py::module_& m);

PYBIND11_MODULE(_qcore, m) {
  m.doc() = "QuantCore C++20 core (panel, kernels, backtest engine)";
  m.attr("__version__") = qc::version();
  m.attr("engine_backend") = qc::engine_backend();
  bind_panel(m);
  bind_kernels(m);
  bind_engine(m);
}
