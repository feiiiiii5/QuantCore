#include <pybind11/pybind11.h>
namespace py = pybind11;
// Replaced with real Panel/Writer bindings by the panel/kernels milestone.
void bind_panel(py::module_& m) { m.def("panel_ready", []() { return true; }); }
