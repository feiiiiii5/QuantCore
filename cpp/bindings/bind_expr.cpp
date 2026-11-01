#include <pybind11/pybind11.h>
namespace py = pybind11;
// Replaced by the expression-DSL milestone.
void bind_expr(py::module_& m) { m.def("expr_ready", []() { return false; }); }
