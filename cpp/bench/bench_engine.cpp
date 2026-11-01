// Engine benchmark: 500 securities x 1250 trading days of synthetic daily bars with a
// monthly (21-trading-day) rebalance. Panel construction happens once, outside timing.
#include <benchmark/benchmark.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "qcore/engine.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

constexpr size_t kSec = 500;
constexpr size_t kTime = 1250;  // ~5 years of trading days

struct BenchEnv {
  std::optional<qc::Panel> panel;
  std::optional<qc::MatrixTargetSource> source;
  qc::BacktestConfig cfg;

  BenchEnv() {
    build_dates();
    build_prices();
    build_weights();
    const std::string path = write_panel();
    panel.emplace(qc::Panel::open(path));
    std::error_code ec;
    std::filesystem::remove(path, ec);       // unlink after mmap (POSIX)
    cfg.initial_cash = qc::to_money(1.0e8);  // 100M CNY
    cfg.annual_days = 244;
    cfg.trace = qc::TraceLevel::Summary;
    cfg.seed = 7;
  }

  std::vector<qc::Date> dates;
  std::vector<qc::Security> securities;
  std::vector<std::vector<double>> fields;  // [field][sec * kTime + time]

 private:
  void build_dates() {
    using namespace std::chrono;
    dates.reserve(kTime);
    sys_days day = sys_days{year{2021} / January / 4};
    while (dates.size() < kTime) {
      const weekday wd{day};
      if (wd != Saturday && wd != Sunday) {
        const year_month_day ymd{day};
        dates.push_back(qc::make_date(static_cast<int>(ymd.year()),
                                      static_cast<unsigned>(ymd.month()),
                                      static_cast<unsigned>(ymd.day())));
      }
      day += days{1};
    }
    securities.reserve(kSec);
    for (size_t i = 0; i < kSec; ++i) {
      qc::Security s;
      const std::string code =
          (i % 10 < 6 ? "60" : "00") + std::to_string(1000 + static_cast<int>(i)).substr(1);
      s.sec_id = code;
      s.code = code;
      s.name = "SYNTH";
      s.board = 0;
      s.list_date = 20100104;
      securities.push_back(std::move(s));
    }
  }

  void build_prices() {
    fields.assign(6, std::vector<double>(kSec * kTime, qc::kNaN));
    uint64_t state = 0x9e3779b97f4a7c15ULL;
    auto next01 = [&state]() {
      state = state * 6364136223846793005ULL + 1442695040888963407ULL;
      const double v = static_cast<double>((state >> 11) & ((1ULL << 53) - 1));
      return v / 9007199254740992.0;  // 2^53
    };
    auto to_yuan_tick = [](double p) { return std::round(p * 100.0) / 100.0; };
    const size_t stride = kTime;
    for (size_t sec = 0; sec < kSec; ++sec) {
      double prev_close = to_yuan_tick(5.0 + 45.0 * next01());
      for (size_t t = 0; t < kTime; ++t) {
        const double drift = 0.02 * (next01() - 0.5);  // +/-1% daily
        const double open = to_yuan_tick(prev_close * (1.0 + drift));
        const double close = to_yuan_tick(prev_close * (1.0 + 0.02 * (next01() - 0.5)));
        const double high = to_yuan_tick(std::max(open, close) * (1.0 + 0.005 * next01()));
        const double low =
            to_yuan_tick(std::max(0.01, std::min(open, close) * (1.0 - 0.005 * next01())));
        const double volume = 1000000.0 + 1000000.0 * next01();
        const size_t idx = sec * stride + t;
        fields[0][idx] = open;
        fields[1][idx] = high;
        fields[2][idx] = low;
        fields[3][idx] = close;
        fields[4][idx] = volume;
        fields[5][idx] = close * volume;
        prev_close = close;
      }
    }
  }

  void build_weights() {
    std::vector<std::vector<double>> rows(kTime, std::vector<double>(kSec, qc::kNaN));
    size_t rebalances = 0;
    for (size_t t = 0; t + 1 < kTime; t += 21) {
      const size_t first = (rebalances * 37) % kSec;
      for (size_t k = 0; k < 50; ++k) {
        rows[t][(first + k) % kSec] = 0.9 / 50.0;
      }
      ++rebalances;
    }
    source.emplace(qc::MatrixTargetSource(std::move(rows), kSec));
  }

  std::string write_panel() const {
    static std::atomic<int> counter{0};
    const auto stamp =
        static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
    const std::string path =
        (std::filesystem::temp_directory_path() /
         ("qcore_bench_" + std::to_string(stamp) + "_" + std::to_string(counter++) + ".qpanel"))
            .string();
    qc::PanelWriter writer(kSec, kTime, dates, securities);
    writer.add_field("open", qc::Layout::SecTime, fields[0].data());
    writer.add_field("high", qc::Layout::SecTime, fields[1].data());
    writer.add_field("low", qc::Layout::SecTime, fields[2].data());
    writer.add_field("close", qc::Layout::SecTime, fields[3].data());
    writer.add_field("volume", qc::Layout::SecTime, fields[4].data());
    writer.add_field("amount", qc::Layout::SecTime, fields[5].data());
    writer.write(path);
    return path;
  }
};

BenchEnv& env() {
  static BenchEnv instance;
  return instance;
}

void BM_EngineMonthlyRebalance(benchmark::State& state) {
  BenchEnv& e = env();
  int64_t trades = 0;
  for (auto _ : state) {
    qc::CancelToken token;
    qc::Engine engine(*e.panel, e.cfg);
    qc::BacktestResult result = engine.run(*e.source, token);
    benchmark::DoNotOptimize(result.metrics.total_return);
    benchmark::DoNotOptimize(result.equity.size());
    trades = static_cast<int64_t>(result.trades.size());
  }
  state.counters["n_sec"] = static_cast<double>(kSec);
  state.counters["n_time"] = static_cast<double>(kTime);
  state.counters["rebalances"] = static_cast<double>((kTime - 1) / 21 + 1);
  state.counters["trades"] = static_cast<double>(trades);
}

BENCHMARK(BM_EngineMonthlyRebalance)->Unit(benchmark::kMillisecond)->Iterations(3);

}  // namespace
