// pybind11 bindings for the backtest engine: flat-kwargs BacktestConfig (money values in
// CNY), a NumPy (n_time, n_sec) target matrix -> Engine.run, cancellation/progress with
// the GIL released for the run, and the BacktestResult surface used by the Python
// control plane. Errors use pybind11's default mapping: std::invalid_argument ->
// ValueError, std::runtime_error -> RuntimeError.
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "qcore/engine.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace py = pybind11;

namespace {

using DoubleMatrix = py::array_t<double, py::array::c_style | py::array::forcecast>;

qc::Date cast_date(py::handle value) {
  const int64_t raw = py::cast<int64_t>(value);
  if (raw < 0 || raw > static_cast<int64_t>(INT32_MAX))
    throw py::value_error("date out of range");
  return static_cast<qc::Date>(raw);
}

// Python-facing money values are CNY (float or int); the engine stays fixed-point.
qc::Money cast_money_yuan(py::handle value) {
  const double yuan = py::cast<double>(value);
  const double scaled = yuan * static_cast<double>(qc::kMoneyScale);
  if (!std::isfinite(scaled) || std::fabs(scaled) > 9.0e18) {
    throw py::value_error("money value is out of range");
  }
  return static_cast<qc::Money>(std::llround(scaled));
}

template <typename E>
E cast_enum(py::handle value, int max_value, const char* what) {
  if (PyLong_Check(value.ptr())) {
    const int64_t raw = py::cast<int64_t>(value);
    if (raw < 0 || raw > max_value) {
      throw py::value_error(std::string(what) + " must be in [0, " + std::to_string(max_value) +
                            "]");
    }
    return static_cast<E>(static_cast<int>(raw));
  }
  return py::cast<E>(value);
}

qc::CorporateAction action_from_object(py::handle value) {
  if (py::isinstance<qc::CorporateAction>(value))
    return py::cast<qc::CorporateAction>(value);
  if (!py::isinstance<py::dict>(value)) {
    throw py::type_error("corporate_actions entries must be dicts or CorporateAction");
  }
  const py::dict dict = py::reinterpret_borrow<py::dict>(value);
  qc::CorporateAction action;
  if (dict.contains("ex_date"))
    action.ex_date = cast_date(dict["ex_date"]);
  if (dict.contains("sec"))
    action.sec = py::cast<int32_t>(dict["sec"]);
  if (dict.contains("cash_per_share")) {
    action.cash_per_share = py::cast<double>(dict["cash_per_share"]);
  }
  if (dict.contains("split_ratio"))
    action.split_ratio = py::cast<double>(dict["split_ratio"]);
  return action;
}

std::vector<qc::CorporateAction> actions_from_object(py::handle value) {
  std::vector<qc::CorporateAction> out;
  if (py::isinstance<py::dict>(value) || py::isinstance<qc::CorporateAction>(value)) {
    out.push_back(action_from_object(value));
    return out;
  }
  for (const py::handle& item : py::cast<py::sequence>(value)) {
    out.push_back(action_from_object(item));
  }
  return out;
}

// Flat kwargs -> BacktestConfig. One macro line per accepted keyword keeps the mapping
// auditable against py_platform's contract.
void apply_config_kwargs(qc::BacktestConfig& cfg, const py::kwargs& kwargs) {
  for (const auto& item : kwargs) {
    const std::string key = py::cast<std::string>(item.first);
    py::handle v = item.second;
#define QC_KW_F64(name, field)       \
  if (key == name) {                 \
    cfg.field = py::cast<double>(v); \
    continue;                        \
  }
#define QC_KW_I64(name, field)        \
  if (key == name) {                  \
    cfg.field = py::cast<int64_t>(v); \
    continue;                         \
  }
#define QC_KW_BOOL(name, field)    \
  if (key == name) {               \
    cfg.field = py::cast<bool>(v); \
    continue;                      \
  }
#define QC_KW_DATE(name, field) \
  if (key == name) {            \
    cfg.field = cast_date(v);   \
    continue;                   \
  }
#define QC_KW_MONEY(name, field)    \
  if (key == name) {                \
    cfg.field = cast_money_yuan(v); \
    continue;                       \
  }
    QC_KW_DATE("start", start)
    QC_KW_DATE("end", end)
    QC_KW_MONEY("initial_cash", initial_cash)
    QC_KW_DATE("st_limit_change_date", rules.st_limit_change_date)
    QC_KW_DATE("after_hours_extension_date", rules.after_hours_extension_date)
    QC_KW_I64("seed", seed)
    QC_KW_I64("main_lot", rules.main_lot)
    QC_KW_I64("star_lot", rules.star_lot)
    QC_KW_I64("bse_lot", rules.bse_lot)
    QC_KW_MONEY("min_commission", costs.min_commission)
    QC_KW_MONEY("min_rebalance_value", exec.min_rebalance_value)
    QC_KW_F64("main_limit_pct", rules.main_limit_pct)
    QC_KW_F64("gem_limit_pct", rules.gem_limit_pct)
    QC_KW_F64("star_limit_pct", rules.star_limit_pct)
    QC_KW_F64("bse_limit_pct", rules.bse_limit_pct)
    QC_KW_F64("st_limit_pct", rules.st_limit_pct)
    QC_KW_F64("st_limit_pct_after", rules.st_limit_pct_after)
    QC_KW_F64("min_price_tick", rules.min_price_tick)
    QC_KW_F64("commission_rate", costs.commission_rate)
    QC_KW_F64("stamp_duty_rate", costs.stamp_duty_rate)
    QC_KW_F64("transfer_fee_rate", costs.transfer_fee_rate)
    QC_KW_F64("exchange_fee_rate", costs.exchange_fee_rate)
    QC_KW_F64("reg_fee_rate", costs.reg_fee_rate)
    QC_KW_F64("slippage_bps", exec.slippage_bps)
    QC_KW_F64("max_participation", exec.max_participation)
    QC_KW_BOOL("t_plus_one", rules.t_plus_one)
    QC_KW_BOOL("after_hours", rules.after_hours)
    QC_KW_BOOL("transfer_fee_shanghai_only", costs.transfer_fee_shanghai_only)
    QC_KW_BOOL("enable_dividend_tax", costs.enable_dividend_tax)
#undef QC_KW_F64
#undef QC_KW_I64
#undef QC_KW_BOOL
#undef QC_KW_DATE
#undef QC_KW_MONEY
    if (key == "annual_days") {
      cfg.annual_days = py::cast<int>(v);
      continue;
    }
    if (key == "exec_type") {
      cfg.exec.type = cast_enum<qc::ExecType>(v, 3, "exec_type");
      continue;
    }
    if (key == "trace_level") {
      cfg.trace = cast_enum<qc::TraceLevel>(v, 2, "trace_level");
      continue;
    }
    if (key == "corporate_actions") {
      cfg.corporate_actions = actions_from_object(v);
      continue;
    }
    if (key == "rules") {
      cfg.rules = py::cast<qc::RuleSet>(v);
      continue;
    }
    if (key == "costs") {
      cfg.costs = py::cast<qc::CostModel>(v);
      continue;
    }
    if (key == "exec") {
      cfg.exec = py::cast<qc::ExecModel>(v);
      continue;
    }
    throw py::type_error("BacktestConfig: unknown keyword argument '" + key + "'");
  }
}

// ------------------------------------------------------------- progress / GIL release
struct ProgressState {
  std::atomic<uint64_t> dates_done{0};
  uint64_t total_dates = 0;
  std::atomic<bool> finished{false};
};

class BacktestProgress {
 public:
  BacktestProgress() : state_(std::make_shared<ProgressState>()) {}
  uint64_t processed_dates() const {
    return state_->dates_done.load(std::memory_order_relaxed);
  }
  uint64_t total_dates() const {
    return state_->total_dates;
  }
  double fraction() const {
    if (state_->total_dates == 0)
      return 0.0;
    const double value =
        static_cast<double>(processed_dates()) / static_cast<double>(state_->total_dates);
    return value > 1.0 ? 1.0 : value;
  }
  bool finished() const {
    return state_->finished.load(std::memory_order_relaxed);
  }
  std::shared_ptr<ProgressState> state() const {
    return state_;
  }

 private:
  std::shared_ptr<ProgressState> state_;
};

// Target source decorator: one Engine call to weights() == one processed panel date.
class CountingSource : public qc::TargetSource {
 public:
  CountingSource(qc::TargetSource& inner, std::shared_ptr<ProgressState> state)
      : inner_(inner), state_(std::move(state)) {}
  const std::vector<double>& weights(size_t date_index) override {
    if (state_)
      state_->dates_done.fetch_add(1, std::memory_order_relaxed);
    return inner_.weights(date_index);
  }

 private:
  qc::TargetSource& inner_;
  std::shared_ptr<ProgressState> state_;
};

class PyEngine {
 public:
  PyEngine(const qc::Panel& panel, qc::BacktestConfig config)
      : panel_(&panel), config_(std::move(config)), engine_(panel, config_) {}
  size_t n_sec() const {
    return panel_->n_sec();
  }
  size_t n_time() const {
    return panel_->n_time();
  }

  // weights: (n_time, n_sec) float64; an all-NaN row means "no rebalance that day".
  qc::BacktestResult run_weights(const DoubleMatrix& matrix, qc::CancelToken& cancel,
                                 BacktestProgress* progress) {
    const auto info = matrix.request();
    if (info.ndim != 2)
      throw py::value_error("weights must be a 2-D (n_time, n_sec) array");
    const size_t n_time = static_cast<size_t>(info.shape[0]);
    const size_t n_sec = static_cast<size_t>(info.shape[1]);
    if (n_time != panel_->n_time() || n_sec != panel_->n_sec()) {
      throw py::value_error("weights shape must be (n_time=" + std::to_string(panel_->n_time()) +
                            ", n_sec=" + std::to_string(panel_->n_sec()) + "), got (" +
                            std::to_string(n_time) + ", " + std::to_string(n_sec) + ")");
    }
    std::vector<std::vector<double>> rows(n_time);
    const auto* data = static_cast<const double*>(info.ptr);
    for (size_t i = 0; i < n_time; ++i) {
      rows[i].assign(data + i * n_sec, data + (i + 1) * n_sec);
    }
    qc::MatrixTargetSource source(std::move(rows), n_sec);
    std::shared_ptr<ProgressState> state = progress ? progress->state() : nullptr;
    if (state)
      state->total_dates = n_time;
    qc::BacktestResult result;
    {
      py::gil_scoped_release release;  // long-running C++ work without the GIL
      if (state) {
        CountingSource counting(source, state);
        result = engine_.run(counting, cancel);
        state->finished.store(true, std::memory_order_relaxed);
      } else {
        result = engine_.run(source, cancel);
      }
    }
    return result;
  }

 private:
  const qc::Panel* panel_;
  qc::BacktestConfig config_;
  qc::Engine engine_;
};

// ---------------------------------------------------------------- result conversions
py::array_t<int64_t> to_money_array(const std::vector<qc::Money>& values) {
  py::array_t<int64_t> out(static_cast<py::ssize_t>(values.size()));
  if (!values.empty()) {
    std::memcpy(out.mutable_data(), values.data(), values.size() * sizeof(int64_t));
  }
  return out;
}

py::dict trade_to_dict(const qc::Trade& trade) {
  py::dict out;
  out["date"] = trade.date;
  out["sec"] = trade.sec;
  out["side"] = static_cast<int>(trade.side);
  out["px"] = trade.px;
  out["qty"] = trade.qty;
  out["amount"] = trade.amount;
  out["commission"] = trade.commission;
  out["stamp_duty"] = trade.stamp_duty;
  out["transfer_fee"] = trade.transfer_fee;
  out["other_fee"] = trade.other_fee;
  out["fee_total"] = trade.fee_total;
  out["reason"] = static_cast<int>(trade.reason);
  return out;
}

py::dict metrics_to_dict(const qc::Metrics& metrics) {
  py::dict out;
  out["total_return"] = metrics.total_return;
  out["annualized_return"] = metrics.annualized_return;
  out["volatility"] = metrics.volatility;
  out["sharpe"] = metrics.sharpe;
  out["sortino"] = metrics.sortino;
  out["max_drawdown"] = metrics.max_drawdown;
  out["calmar"] = metrics.calmar;
  out["win_rate"] = metrics.win_rate;
  out["profit_factor"] = metrics.profit_factor;
  out["turnover"] = metrics.turnover;
  out["total_fees"] = metrics.total_fees;
  out["trade_count"] = metrics.trade_count;
  out["trading_days"] = metrics.trading_days;
  return out;
}

}  // namespace

void bind_engine(py::module_& m) {
  py::enum_<qc::ExecType>(m, "ExecType", "Next-day execution price model.")
      .value("NextOpen", qc::ExecType::NextOpen)
      .value("NextClose", qc::ExecType::NextClose)
      .value("NextVwap", qc::ExecType::NextVwap)
      .value("AfterHoursFixed", qc::ExecType::AfterHoursFixed);
  py::enum_<qc::TraceLevel>(m, "TraceLevel", "How much per-order detail to keep.")
      .value("Off", qc::TraceLevel::Off)
      .value("Summary", qc::TraceLevel::Summary)
      .value("Full", qc::TraceLevel::Full);

  py::class_<qc::RuleSet>(m, "RuleSet", "Trading rules (limits, lots, T+1, after-hours).")
      .def(py::init<>())
      .def_readwrite("main_limit_pct", &qc::RuleSet::main_limit_pct)
      .def_readwrite("gem_limit_pct", &qc::RuleSet::gem_limit_pct)
      .def_readwrite("star_limit_pct", &qc::RuleSet::star_limit_pct)
      .def_readwrite("bse_limit_pct", &qc::RuleSet::bse_limit_pct)
      .def_readwrite("st_limit_pct", &qc::RuleSet::st_limit_pct)
      .def_readwrite("st_limit_change_date", &qc::RuleSet::st_limit_change_date)
      .def_readwrite("st_limit_pct_after", &qc::RuleSet::st_limit_pct_after)
      .def_readwrite("main_lot", &qc::RuleSet::main_lot)
      .def_readwrite("star_lot", &qc::RuleSet::star_lot)
      .def_readwrite("bse_lot", &qc::RuleSet::bse_lot)
      .def_readwrite("t_plus_one", &qc::RuleSet::t_plus_one)
      .def_readwrite("after_hours", &qc::RuleSet::after_hours)
      .def_readwrite("after_hours_extension_date", &qc::RuleSet::after_hours_extension_date)
      .def_readwrite("min_price_tick", &qc::RuleSet::min_price_tick);

  py::class_<qc::CostModel>(m, "CostModel", "Transaction cost model.")
      .def(py::init<>())
      .def_readwrite("commission_rate", &qc::CostModel::commission_rate)
      .def_readwrite("min_commission", &qc::CostModel::min_commission)
      .def_readwrite("stamp_duty_rate", &qc::CostModel::stamp_duty_rate)
      .def_readwrite("transfer_fee_rate", &qc::CostModel::transfer_fee_rate)
      .def_readwrite("exchange_fee_rate", &qc::CostModel::exchange_fee_rate)
      .def_readwrite("reg_fee_rate", &qc::CostModel::reg_fee_rate)
      .def_readwrite("transfer_fee_shanghai_only", &qc::CostModel::transfer_fee_shanghai_only)
      .def_readwrite("enable_dividend_tax", &qc::CostModel::enable_dividend_tax);

  py::class_<qc::ExecModel>(m, "ExecModel", "Execution model (price type, slippage, caps).")
      .def(py::init<>())
      .def_readwrite("type", &qc::ExecModel::type)
      .def_readwrite("slippage_bps", &qc::ExecModel::slippage_bps)
      .def_readwrite("max_participation", &qc::ExecModel::max_participation)
      .def_readwrite("min_rebalance_value", &qc::ExecModel::min_rebalance_value);

  py::class_<qc::CorporateAction>(m, "CorporateAction", "Cash dividend / split event.")
      .def(py::init<>())
      .def_readwrite("ex_date", &qc::CorporateAction::ex_date)
      .def_readwrite("sec", &qc::CorporateAction::sec)
      .def_readwrite("cash_per_share", &qc::CorporateAction::cash_per_share)
      .def_readwrite("split_ratio", &qc::CorporateAction::split_ratio);

  py::class_<qc::BacktestConfig> config_cls(
      m, "BacktestConfig", "Backtest config; build from flat kwargs (money in CNY).");
  config_cls
      .def(py::init([](py::kwargs kwargs) {
        qc::BacktestConfig config;
        apply_config_kwargs(config, kwargs);
        return config;
      }))
      .def_readwrite("rules", &qc::BacktestConfig::rules)
      .def_readwrite("costs", &qc::BacktestConfig::costs)
      .def_readwrite("exec", &qc::BacktestConfig::exec)
      .def_readwrite("corporate_actions", &qc::BacktestConfig::corporate_actions);
#define QC_PROP(pyname, type, getter, setter)                                    \
  config_cls.def_property(                                                       \
      pyname, [](const qc::BacktestConfig& config) -> type { return (getter); }, \
      [](qc::BacktestConfig& config, type value) { (setter); })
#define QC_MONEY_PROP(pyname, field)                                                     \
  config_cls.def_property(                                                               \
      pyname,                                                                            \
      [](const qc::BacktestConfig& config) -> double {                                   \
        return static_cast<double>(config.field) / static_cast<double>(qc::kMoneyScale); \
      },                                                                                 \
      [](qc::BacktestConfig& config, double value) {                                     \
        config.field = static_cast<qc::Money>(std::llround(value * qc::kMoneyScale));    \
      })
  QC_PROP("start", qc::Date, config.start, config.start = value);
  QC_PROP("end", qc::Date, config.end, config.end = value);
  QC_PROP("trace_level", int, static_cast<int>(config.trace),
          config.trace = static_cast<qc::TraceLevel>(value));
  QC_PROP("exec_type", int, static_cast<int>(config.exec.type),
          config.exec.type = static_cast<qc::ExecType>(value));
  QC_MONEY_PROP("initial_cash", initial_cash);
  QC_MONEY_PROP("min_commission", costs.min_commission);
  QC_MONEY_PROP("min_rebalance_value", exec.min_rebalance_value);
#undef QC_PROP
#undef QC_MONEY_PROP

  py::class_<qc::CancelToken>(m, "CancelToken", "Thread-safe cooperative cancellation flag.")
      .def(py::init<>())
      .def("cancel", &qc::CancelToken::cancel)
      .def("cancelled", &qc::CancelToken::cancelled);

  py::class_<BacktestProgress>(m, "BacktestProgress",
                               "Pollable per-run progress; other threads can poll it while "
                               "Engine.run holds no GIL.")
      .def(py::init<>())
      .def_property_readonly("processed_dates", &BacktestProgress::processed_dates)
      .def_property_readonly("total_dates", &BacktestProgress::total_dates)
      .def_property_readonly("fraction", &BacktestProgress::fraction)
      .def_property_readonly("finished", &BacktestProgress::finished);

  py::class_<PyEngine>(m, "Engine",
                       "Backtest engine over an immutable Panel; run() releases the GIL.")
      .def(py::init<const qc::Panel&, qc::BacktestConfig>(), py::arg("panel"), py::arg("config"),
           py::keep_alive<1, 2>())
      .def_property_readonly("n_sec", &PyEngine::n_sec)
      .def_property_readonly("n_time", &PyEngine::n_time)
      .def(
          "run",
          [](PyEngine& engine, const DoubleMatrix& weights) {
            qc::CancelToken cancel;
            return engine.run_weights(weights, cancel, nullptr);
          },
          py::arg("weights"))
      .def(
          "run",
          [](PyEngine& engine, const DoubleMatrix& weights, qc::CancelToken& cancel) {
            return engine.run_weights(weights, cancel, nullptr);
          },
          py::arg("weights"), py::arg("cancel"))
      .def(
          "run",
          [](PyEngine& engine, const DoubleMatrix& weights, qc::CancelToken& cancel,
             BacktestProgress& progress) { return engine.run_weights(weights, cancel, &progress); },
          py::arg("weights"), py::arg("cancel"), py::arg("progress"));

  py::class_<qc::BacktestResult>(m, "BacktestResult",
                                 "Equity curve, trades, metrics and rejection reasons.")
      .def_property_readonly("dates", [](const qc::BacktestResult& r) { return py::cast(r.dates); })
      .def_property_readonly("equity",
                             [](const qc::BacktestResult& r) { return to_money_array(r.equity); })
      .def_property_readonly("cash",
                             [](const qc::BacktestResult& r) { return to_money_array(r.cash); })
      .def_property_readonly(
          "market_value",
          [](const qc::BacktestResult& r) { return to_money_array(r.market_value); })
      .def_property_readonly("trades",
                             [](const qc::BacktestResult& r) {
                               py::list out;
                               for (const qc::Trade& trade : r.trades)
                                 out.append(trade_to_dict(trade));
                               return out;
                             })
      .def_property_readonly("metrics",
                             [](const qc::BacktestResult& r) { return metrics_to_dict(r.metrics); })
      .def_property_readonly("reasons",
                             [](const qc::BacktestResult& r) {
                               py::dict out;
                               for (const qc::ReasonCount& reason : r.reasons) {
                                 out[py::int_(static_cast<int>(reason.reason))] = reason.count;
                               }
                               return out;
                             })
      .def_property_readonly(
          "final_position_secs",
          [](const qc::BacktestResult& r) { return py::cast(r.final_position_secs); })
      .def_property_readonly(
          "final_position_qty",
          [](const qc::BacktestResult& r) { return py::cast(r.final_position_qty); })
      .def_readonly("engine_version", &qc::BacktestResult::engine_version)
      .def_readonly("seed", &qc::BacktestResult::seed);

  m.def(
      "engine_ready", []() { return true; },
      "True when the real C++ engine bindings are available.");
}
