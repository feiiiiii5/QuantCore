#include <pybind11/pybind11.h>
namespace py = pybind11;
// Replaced with real BacktestConfig/Engine bindings by the engine milestone.
void bind_engine(py::module_& m) { m.def("engine_ready", []() { return true; }); }
