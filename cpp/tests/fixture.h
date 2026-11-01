#pragma once
// Shared synthetic-panel fixture for backtest engine tests and benchmarks.
// Builds a valid .qpanel in the temp directory, maps it, and unlinks the file.
#include <atomic>
#include <chrono>
#include <filesystem>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qcore/engine.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace qc::tests {

inline std::string temp_panel_path() {
  static std::atomic<int> counter{0};
  const auto stamp =
      static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
  return (std::filesystem::temp_directory_path() /
          ("qcore_sim_" + std::to_string(stamp) + "_" +
           std::to_string(counter.fetch_add(1)) + ".qpanel"))
      .string();
}

inline Security synth_security(std::string code, int board = 0, Date list_date = 20200101,
                               Date delist_date = kInvalidDate) {
  Security s;
  s.sec_id = code;
  s.code = code;
  s.name = "SYNTH " + code;
  s.board = board;
  s.list_date = list_date;
  s.delist_date = delist_date;
  return s;
}

// Row-major [sec][time] synthetic panel with lazily created NaN-filled fields.
class SynthPanel {
 public:
  SynthPanel(std::vector<Date> dates, std::vector<Security> securities)
      : dates_(std::move(dates)),
        securities_(std::move(securities)),
        n_time_(dates_.size()),
        n_sec_(securities_.size()) {
    if (dates_.empty() || securities_.empty()) {
      throw std::invalid_argument("SynthPanel needs at least one date and one security");
    }
  }

  size_t n_sec() const { return n_sec_; }
  size_t n_time() const { return n_time_; }

  std::vector<double>& field(const std::string& name) {
    auto it = fields_.find(name);
    if (it != fields_.end()) return it->second;
    return fields_.emplace(name, std::vector<double>(n_sec_ * n_time_, kNaN)).first->second;
  }

  void set(const std::string& name, size_t sec, size_t time, double value) {
    if (sec >= n_sec_ || time >= n_time_) throw std::out_of_range("SynthPanel::set");
    field(name)[sec * n_time_ + time] = value;
  }

  void bar(size_t sec, size_t time, double open, double high, double low, double close,
           double volume = 1000000.0) {
    set("open", sec, time, open);
    set("high", sec, time, high);
    set("low", sec, time, low);
    set("close", sec, time, close);
    set("volume", sec, time, volume);
    set("amount", sec, time, close * volume);
  }

  void bar_all(size_t sec, double open, double high, double low, double close,
               double volume = 1000000.0) {
    for (size_t t = 0; t < n_time_; ++t) bar(sec, t, open, high, low, close, volume);
  }

  void flag_all(const std::string& name, size_t sec, double value) {
    for (size_t t = 0; t < n_time_; ++t) set(name, sec, t, value);
  }

  // Writes + maps the panel; the backing file is unlinked immediately after mmap.
  Panel build() {
    const std::string path = temp_panel_path();
    PanelWriter writer(n_sec_, n_time_, dates_, securities_);
    for (auto& kv : fields_) {
      writer.add_field(kv.first, Layout::SecTime, kv.second.data());
    }
    writer.write(path);
    Panel panel = Panel::open(path);
    std::error_code ec;
    std::filesystem::remove(path, ec);  // POSIX: unlink after mmap is safe
    return panel;
  }

 private:
  std::vector<Date> dates_;
  std::vector<Security> securities_;
  size_t n_time_ = 0;
  size_t n_sec_ = 0;
  std::map<std::string, std::vector<double>> fields_;
};

// (n_time x n_sec) target-weight matrix; rows default to NaN = "no rebalance".
inline std::vector<std::vector<double>> nan_weights(size_t n_time, size_t n_sec) {
  return std::vector<std::vector<double>>(n_time, std::vector<double>(n_sec, kNaN));
}

inline BacktestConfig base_config() {
  BacktestConfig cfg;
  cfg.initial_cash = to_money(1000000.0);
  cfg.trace = TraceLevel::Full;
  return cfg;
}

inline Px px(double yuan) { return to_px(yuan); }
inline Money money(double yuan) { return to_money(yuan); }

}  // namespace qc::tests
