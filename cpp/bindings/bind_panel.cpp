// pybind11 bindings for the .qpanel container, trading calendar and date helpers.
// Panel.field(name) returns a read-only zero-copy NumPy view whose `base` keeps the Panel
// alive; the array shape follows the stored layout (SecTime -> (n_sec, n_time),
// TimeSec -> (n_time, n_sec)) with C-contiguous strides.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qcore/calendar.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace py = pybind11;

namespace {

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

std::string layout_name(qc::Layout layout) {
  return layout == qc::Layout::SecTime ? "sec_time" : "time_sec";
}

int64_t python_int(py::handle value, const char* what) {
  if (PyLong_Check(value.ptr())) {
    int overflow = 0;
    const long long result = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
    if (overflow != 0)
      throw py::value_error(std::string(what) + " is outside int64 range");
    if (result == -1 && PyErr_Occurred()) {
      PyErr_Clear();
      throw py::value_error(std::string(what) + " is not an integer");
    }
    return static_cast<int64_t>(result);
  }
  if (PyIndex_Check(value.ptr())) {
    py::object index = py::reinterpret_steal<py::object>(PyNumber_Index(value.ptr()));
    if (!index)
      throw py::value_error(std::string(what) + " is not an integer");
    return python_int(index, what);
  }
  throw py::value_error(std::string(what) + " must be an integer");
}

qc::Date python_date(py::handle value, const char* what) {
  const int64_t raw = python_int(value, what);
  if (raw < INT32_MIN || raw > INT32_MAX)
    throw py::value_error(std::string(what) + " out of range");
  return static_cast<qc::Date>(raw);
}

std::vector<qc::Date> parse_dates(const py::object& dates) {
  std::vector<qc::Date> out;
  if (py::isinstance<py::array>(dates)) {
    const auto array =
        py::cast<py::array_t<int64_t, py::array::c_style | py::array::forcecast>>(dates);
    const auto info = array.request();
    if (info.ndim != 1)
      throw py::value_error("dates must be a 1-D sequence");
    const auto* values = static_cast<const int64_t*>(info.ptr);
    out.reserve(static_cast<std::size_t>(info.shape[0]));
    for (py::ssize_t i = 0; i < info.shape[0]; ++i) {
      if (values[i] < INT32_MIN || values[i] > INT32_MAX) {
        throw py::value_error("dates entry out of int32 range");
      }
      out.push_back(static_cast<qc::Date>(values[i]));
    }
    return out;
  }
  const py::sequence sequence = py::cast<py::sequence>(dates);
  out.reserve(static_cast<std::size_t>(py::len(sequence)));
  for (const py::handle& item : sequence)
    out.push_back(python_date(item, "dates entry"));
  return out;
}

std::string security_string(const py::dict& dict, const char* key, const char* fallback) {
  if (!dict.contains(key)) {
    if (fallback == nullptr)
      throw py::value_error(std::string("security is missing '") + key + "'");
    return std::string(fallback);
  }
  return py::cast<std::string>(dict[key]);
}

qc::Security security_from_dict(const py::dict& dict, std::size_t index) {
  qc::Security sec;
  sec.sec_id = security_string(dict, "sec_id", nullptr);
  sec.code = security_string(dict, "code", nullptr);
  sec.name = security_string(dict, "name", "");
  if (dict.contains("board")) {
    sec.board = static_cast<int32_t>(python_int(dict["board"], "board"));
  }
  if (dict.contains("list_date"))
    sec.list_date = python_date(dict["list_date"], "list_date");
  if (dict.contains("delist_date"))
    sec.delist_date = python_date(dict["delist_date"], "delist_date");
  (void)index;
  return sec;
}

std::vector<qc::Security> parse_securities(const py::object& securities) {
  std::vector<qc::Security> out;
  const py::sequence sequence = py::cast<py::sequence>(securities);
  out.reserve(static_cast<std::size_t>(py::len(sequence)));
  for (const py::handle& item : sequence) {
    if (py::isinstance<qc::Security>(item)) {
      out.push_back(py::cast<qc::Security>(item));
    } else if (py::isinstance<py::dict>(item)) {
      out.push_back(security_from_dict(py::cast<py::dict>(item), out.size()));
    } else {
      throw py::value_error("each security must be a dict or a qcore.Security");
    }
  }
  return out;
}

py::dict security_to_dict(const qc::Security& sec) {
  py::dict dict;
  dict["sec_id"] = sec.sec_id;
  dict["code"] = sec.code;
  dict["name"] = sec.name;
  dict["board"] = sec.board;
  dict["list_date"] = sec.list_date;
  dict["delist_date"] = sec.delist_date;
  return dict;
}

// Read-only zero-copy view of a field; `base` owns the Panel lifetime.
py::array_t<double> make_view(const qc::FieldView& view, const py::object& base) {
  std::vector<py::ssize_t> shape;
  std::vector<py::ssize_t> strides;
  if (view.layout == qc::Layout::SecTime) {
    shape = {static_cast<py::ssize_t>(view.n_sec), static_cast<py::ssize_t>(view.n_time)};
    strides = {static_cast<py::ssize_t>(view.n_time * sizeof(double)), sizeof(double)};
  } else {
    shape = {static_cast<py::ssize_t>(view.n_time), static_cast<py::ssize_t>(view.n_sec)};
    strides = {static_cast<py::ssize_t>(view.n_sec * sizeof(double)), sizeof(double)};
  }
  py::array_t<double> array(shape, strides, view.data, base);
  array.attr("setflags")(py::arg("write") = false);
  return array;
}

// Panel open/validate hash or map the whole file; run them without the GIL.
qc::Panel open_panel(const std::string& path, bool verify_content) {
  py::gil_scoped_release release;
  return qc::Panel::open(path, verify_content);
}

void validate_panel(const std::string& path) {
  py::gil_scoped_release release;
  qc::Panel::validate(path);
}

// Honest readiness probe: write, reopen and read back a tiny panel in the temp directory.
bool panel_ready_probe() {
  static std::atomic<std::uint64_t> counter{0};
  try {
    const auto stamp =
        static_cast<std::uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count());
    const std::filesystem::path path =
        std::filesystem::temp_directory_path() /
        ("qcore_panel_ready_" + std::to_string(stamp) + "_" +
         std::to_string(counter.fetch_add(1, std::memory_order_relaxed)) + ".qpanel");
    qc::Security sec;
    sec.sec_id = "PROBE";
    sec.code = "000001";
    sec.name = "probe";
    sec.board = 0;
    sec.list_date = 20200102;
    std::vector<qc::Date> dates{20200102, 20200103};
    const std::vector<double> data{1.0, 2.0, 3.0, 4.0};
    {
      qc::PanelWriter writer(1, 2, dates, {sec});
      writer.add_field("v", qc::Layout::SecTime, data.data());
      writer.set_metadata("{\"probe\":true}");
      writer.write(path.string());
    }
    qc::Panel panel = qc::Panel::open(path.string(), /*verify_content=*/true);
    const bool ok = panel.n_sec() == 1 && panel.n_time() == 2 && panel.has_field("v") &&
                    panel.field("v").at(0, 1) == 2.0;
    std::error_code ignored;
    std::filesystem::remove(path, ignored);
    return ok;
  } catch (...) {
    return false;
  }
}

}  // namespace

void bind_panel(py::module_& m) {
  py::enum_<qc::Layout>(m, "Layout", "Memory layout of a panel field column.")
      .value("SecTime", qc::Layout::SecTime, "row-major [security][time]")
      .value("TimeSec", qc::Layout::TimeSec, "row-major [time][security]")
      .export_values();

  py::class_<qc::Security>(m, "Security", "Security master row stored in a .qpanel file.")
      .def(py::init<>())
      .def(py::init([](std::string sec_id, std::string code, std::string name, int32_t board,
                       int32_t list_date, int32_t delist_date) {
             qc::Security sec;
             sec.sec_id = std::move(sec_id);
             sec.code = std::move(code);
             sec.name = std::move(name);
             sec.board = board;
             sec.list_date = list_date;
             sec.delist_date = delist_date;
             return sec;
           }),
           py::arg("sec_id"), py::arg("code"), py::arg("name") = "", py::arg("board") = 0,
           py::arg("list_date") = qc::kInvalidDate, py::arg("delist_date") = qc::kInvalidDate)
      .def_readwrite("sec_id", &qc::Security::sec_id)
      .def_readwrite("code", &qc::Security::code)
      .def_readwrite("name", &qc::Security::name)
      .def_readwrite("board", &qc::Security::board)
      .def_readwrite("list_date", &qc::Security::list_date)
      .def_readwrite("delist_date", &qc::Security::delist_date);

  py::class_<qc::FieldView>(m, "FieldView",
                            "Non-owning view of one panel field; keep the Panel alive.")
      .def_readonly("layout", &qc::FieldView::layout)
      .def_readonly("n_sec", &qc::FieldView::n_sec)
      .def_readonly("n_time", &qc::FieldView::n_time)
      .def(
          "at",
          [](const qc::FieldView& view, std::size_t sec, std::size_t time) {
            if (sec >= view.n_sec || time >= view.n_time) {
              throw py::index_error("FieldView.at: index out of range");
            }
            return view.at(sec, time);
          },
          py::arg("sec"), py::arg("time"))
      .def(
          "numpy",
          [](const py::object& self) {
            const qc::FieldView& view = py::cast<const qc::FieldView&>(self);
            return make_view(view, self);
          },
          "Zero-copy read-only NumPy view (storage-order shape).");

  py::class_<qc::PanelWriter>(m, "PanelWriter",
                              "Builds an immutable .qpanel file; data is copied on write.")
      .def(py::init([](std::size_t n_sec, std::size_t n_time, const py::object& dates,
                       const py::object& securities) {
             return qc::PanelWriter(n_sec, n_time, parse_dates(dates),
                                    parse_securities(securities));
           }),
           py::arg("n_sec"), py::arg("n_time"), py::arg("dates"), py::arg("securities"))
      .def(
          "add_field",
          [](qc::PanelWriter& self, const std::string& name, const py::object& layout,
             const py::array_t<double, py::array::c_style | py::array::forcecast>& data) {
            const qc::Layout parsed = parse_layout(layout);
            const std::size_t count = self.n_sec() * self.n_time();
            if (static_cast<std::size_t>(data.size()) != count) {
              throw py::value_error("add_field: data.size() (" + std::to_string(data.size()) +
                                    ") must equal n_sec*n_time (" + std::to_string(count) + ")");
            }
            const auto info = data.request();
            const auto* values = static_cast<const double*>(info.ptr);
            py::gil_scoped_release release;
            self.add_field(name, parsed, values);
          },
          py::arg("name"), py::arg("layout"), py::arg("data"),
          "Add a field; data is flattened in C order and copied into the file.")
      .def("set_metadata", &qc::PanelWriter::set_metadata, py::arg("json"),
           "Opaque JSON text stored in the panel and returned by Panel.metadata_json.")
      .def(
          "write",
          [](qc::PanelWriter& self, const std::string& path) {
            py::gil_scoped_release release;
            self.write(path);
          },
          py::arg("path"), "Write atomically; on Windows an existing target is refused.")
      .def_property_readonly("n_sec", &qc::PanelWriter::n_sec)
      .def_property_readonly("n_time", &qc::PanelWriter::n_time);

  py::class_<qc::Panel>(m, "Panel", "Immutable memory-mapped .qpanel snapshot (read-only).")
      .def_static("open", &open_panel, py::arg("path"), py::arg("verify_content") = false,
                  "Memory-map a .qpanel file read-only. Fast path validates magic/version/"
                  "size/section bounds/alignment/dates/security directory/field table; "
                  "verify_content=True additionally checks the whole-payload content hash. "
                  "Runs without the GIL.")
      .def_static("validate", &validate_panel, py::arg("path"),
                  "Full validation including the content hash; raises RuntimeError when "
                  "the file is not valid. Runs without the GIL.")
      .def_property_readonly("n_sec", &qc::Panel::n_sec)
      .def_property_readonly("n_time", &qc::Panel::n_time)
      .def_property_readonly("dates", &qc::Panel::dates, "Trading dates as YYYYMMDD ints.")
      .def_property_readonly("securities",
                             [](const qc::Panel& panel) {
                               py::list items;
                               for (const qc::Security& sec : panel.securities())
                                 items.append(security_to_dict(sec));
                               return items;
                             })
      .def_property_readonly("metadata_json", &qc::Panel::metadata_json)
      .def_property_readonly("content_hash", &qc::Panel::content_hash)
      .def("field_names", &qc::Panel::field_names, "Sorted field names.")
      .def("has_field", &qc::Panel::has_field, py::arg("name"))
      .def(
          "field",
          [](const py::object& self, const std::string& name) {
            const qc::Panel& panel = py::cast<const qc::Panel&>(self);
            const qc::FieldView view = panel.field(name);
            return make_view(view, self);
          },
          py::arg("name"),
          "Zero-copy read-only view: SecTime -> (n_sec, n_time), TimeSec -> (n_time, n_sec).")
      .def(
          "field_view",
          [](const qc::Panel& panel, const std::string& name) { return panel.field(name); },
          py::arg("name"), py::keep_alive<0, 1>())
      .def(
          "field_layout",
          [](const qc::Panel& panel, const std::string& name) {
            return layout_name(panel.field(name).layout);
          },
          py::arg("name"));

  py::class_<qc::TradingCalendar>(m, "TradingCalendar", "Sorted unique A-share trading dates.")
      .def(py::init<std::vector<qc::Date>>(), py::arg("dates"))
      .def_static("weekdays", &qc::TradingCalendar::weekdays, py::arg("start"), py::arg("end"),
                  py::arg("holidays") = std::vector<qc::Date>{})
      .def_static("from_file", &qc::TradingCalendar::from_file, py::arg("path"))
      .def("save", &qc::TradingCalendar::save, py::arg("path"))
      .def("__len__", &qc::TradingCalendar::size)
      .def_property_readonly("dates", &qc::TradingCalendar::dates)
      .def("at", &qc::TradingCalendar::at, py::arg("index"))
      .def("index_of", &qc::TradingCalendar::index_of, py::arg("date"), "Row index or -1.")
      .def("is_trading_day", &qc::TradingCalendar::is_trading_day, py::arg("date"))
      .def("next_index", &qc::TradingCalendar::next_index, py::arg("index"))
      .def("prev_index", &qc::TradingCalendar::prev_index, py::arg("index"))
      .def("next", &qc::TradingCalendar::next, py::arg("date"), "Next date or 0 when absent.")
      .def("prev", &qc::TradingCalendar::prev, py::arg("date"));

  m.def("securities_to_json", &qc::securities_to_json, py::arg("securities"));
  m.def("securities_from_json", &qc::securities_from_json, py::arg("json"));
  m.def("date_to_string", &qc::date_to_string, py::arg("date"));
  m.def("string_to_date", &qc::string_to_date, py::arg("text"));
  m.def("valid_date", &qc::valid_date, py::arg("date"));
  m.def("make_date", &qc::make_date, py::arg("year"), py::arg("month"), py::arg("day"));
  m.def("panel_ready", &panel_ready_probe,
        "True when the .qpanel writer/reader bindings pass an end-to-end probe.");
}
