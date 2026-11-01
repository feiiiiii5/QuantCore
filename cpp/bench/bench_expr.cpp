// Benchmarks for the factor-expression DSL: parse/explain cost and pointwise evaluation
// on a synthetic .qpanel. Run with `./build/.../qcore_bench --benchmark_min_time=0.2s`.
#include <benchmark/benchmark.h>

#include <chrono>
#include <cmath>
#include <cstddef>
#include <filesystem>
#include <string>
#include <utility>
#include <vector>

#include "qcore/expr.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

constexpr std::size_t kNsec = 128;
constexpr std::size_t kNtime = 256;

struct TempFileGuard {
  explicit TempFileGuard(std::string value) : path(std::move(value)) {}
  ~TempFileGuard() {
    std::error_code error;
    std::filesystem::remove(path, error);
  }
  TempFileGuard(const TempFileGuard&) = delete;
  TempFileGuard& operator=(const TempFileGuard&) = delete;
  std::string path;
};

std::string write_bench_panel() {
  std::vector<qc::Date> dates;
  dates.reserve(kNtime);
  for (std::size_t t = 0; t < kNtime; ++t) {
    const int year = 2020 + static_cast<int>(t / 240);
    const int month = static_cast<int>((t / 20) % 12) + 1;
    const int day = static_cast<int>(t % 20) + 1;
    dates.push_back(qc::make_date(year, month, day));
  }
  std::vector<qc::Security> securities;
  securities.reserve(kNsec);
  for (std::size_t s = 0; s < kNsec; ++s) {
    qc::Security security;
    security.sec_id = "S" + std::to_string(s);
    security.code = "000000";
    security.name = "Synthetic" + std::to_string(s);
    security.board = 0;
    security.list_date = qc::make_date(2020, 1, 1);
    securities.push_back(std::move(security));
  }
  std::vector<double> close(kNsec * kNtime);
  for (std::size_t s = 0; s < kNsec; ++s) {
    for (std::size_t t = 0; t < kNtime; ++t) {
      const double level = 10.0 + static_cast<double>(s % 50) * 0.5;
      const double wave = std::sin(static_cast<double>(s * 7 + t * 3) * 0.01);
      close[s * kNtime + t] = level + wave + 0.001 * static_cast<double>(t);
    }
  }
  std::vector<double> open(kNsec * kNtime);
  for (std::size_t i = 0; i < open.size(); ++i) open[i] = close[i] - 0.01;

  const auto stamp = static_cast<unsigned long long>(
      std::chrono::steady_clock::now().time_since_epoch().count());
  const std::filesystem::path path =
      std::filesystem::temp_directory_path() /
      ("qcore_bench_expr_" + std::to_string(stamp) + ".qpanel");
  qc::PanelWriter writer(kNsec, kNtime, std::move(dates), std::move(securities));
  writer.add_field("close", qc::Layout::SecTime, close.data());
  writer.add_field("open", qc::Layout::SecTime, open.data());
  writer.write(path.string());
  return path.string();
}

const qc::Panel& bench_panel() {
  static const std::string file_path = write_bench_panel();
  static const TempFileGuard guard(file_path);  // destroyed after the panel
  static const qc::Panel panel = qc::Panel::open(file_path);
  return panel;
}

constexpr const char* kTimeSeriesSource =
    "ts_mean(close, 5) / ts_mean(close, 20) + ts_std(returns, 10) + delay(open, 1)";
constexpr const char* kCrossSource = "rank(ts_mean(close, 5) / ts_mean(close, 20))";

void BM_Parse(benchmark::State& state) {
  for (auto _ : state) {
    const qc::Expression expression = qc::Expression::parse(kTimeSeriesSource);
    benchmark::DoNotOptimize(expression.source().size());
  }
}
BENCHMARK(BM_Parse);

void BM_Explain(benchmark::State& state) {
  const qc::Expression expression = qc::Expression::parse(kTimeSeriesSource);
  for (auto _ : state) {
    benchmark::DoNotOptimize(expression.explain().size());
  }
}
BENCHMARK(BM_Explain);

void BM_EvalTimeSeries(benchmark::State& state) {
  const qc::Panel& panel = bench_panel();
  const qc::Expression expression = qc::Expression::parse(kTimeSeriesSource);
  std::size_t index = 0;
  for (auto _ : state) {
    const std::size_t sec = index % panel.n_sec();
    const std::size_t time = index % panel.n_time();
    benchmark::DoNotOptimize(expression.eval(panel, sec, time));
    ++index;
  }
  state.SetItemsProcessed(static_cast<benchmark::IterationCount>(index));
}
BENCHMARK(BM_EvalTimeSeries);

void BM_EvalCross(benchmark::State& state) {
  const qc::Panel& panel = bench_panel();
  const qc::Expression expression = qc::Expression::parse(kCrossSource);
  std::size_t index = 0;
  for (auto _ : state) {
    const std::size_t sec = index % panel.n_sec();
    const std::size_t time = index % panel.n_time();
    benchmark::DoNotOptimize(expression.eval_cross(panel, sec, time));
    ++index;
  }
  state.SetItemsProcessed(static_cast<benchmark::IterationCount>(index));
}
BENCHMARK(BM_EvalCross);

}  // namespace
