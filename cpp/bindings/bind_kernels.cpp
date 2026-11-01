#include <pybind11/pybind11.h>
namespace py = pybind11;
void bind_kernels(py::module_& m) { m.def("kernels_ready", []() { return true; }); }
