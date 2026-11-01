// Google Benchmark: rolling / cross-sectional kernels and technical indicators.
#include <benchmark/benchmark.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

#include "qcore/kernels.h"

namespace {

std::vector<double> make_series(std::size_t n, double offset) {
  std::vector<double> values(n);
  for (std::size_t i = 0; i < n; ++i) {
    const double t = static_cast<double>(i);
    values[i] = offset + std::sin(t * 0.01) * 3.0 + std::cos(t * 0.0031) * 2.0;
  }
  return values;
}

std::vector<double> make_volume(std::size_t n) {
  std::vector<double> values(n);
  for (std::size_t i = 0; i < n; ++i) {
    values[i] = 1000.0 + static_cast<double>(i % 211) * 13.0;
  }
  return values;
}

void report_items(benchmark::State& state, std::size_t n) {
  state.SetItemsProcessed(state.iterations() * static_cast<std::int64_t>(n));
}

}  // namespace

static void BM_RollingMean(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const auto window = static_cast<std::size_t>(state.range(1));
  const std::vector<double> x = make_series(n, 100.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::rolling_mean(x.data(), n, window, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_RollingMean)->ArgsProduct({{100000, 1000000}, {20, 60}});

static void BM_RollingStd(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const auto window = static_cast<std::size_t>(state.range(1));
  const std::vector<double> x = make_series(n, 100.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::rolling_std(x.data(), n, window, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_RollingStd)->ArgsProduct({{100000, 1000000}, {20, 60}});

static void BM_RollingCorr(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const auto window = static_cast<std::size_t>(state.range(1));
  const std::vector<double> x = make_series(n, 100.0);
  const std::vector<double> y = make_series(n, 50.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::rolling_corr(x.data(), y.data(), n, window, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_RollingCorr)->ArgsProduct({{100000, 1000000}, {20}});

static void BM_CrossRank(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const std::vector<double> x = make_series(n, 100.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::cross_rank(x.data(), n, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_CrossRank)->Arg(500)->Arg(5000);

static void BM_CrossZscore(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const std::vector<double> x = make_series(n, 100.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::cross_zscore(x.data(), n, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_CrossZscore)->Arg(500)->Arg(5000);

static void BM_IndicatorBoll(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const auto window = static_cast<std::size_t>(state.range(1));
  const std::vector<double> close = make_series(n, 100.0);
  std::vector<double> mid(n, 0.0);
  std::vector<double> upper(n, 0.0);
  std::vector<double> lower(n, 0.0);
  for (auto _ : state) {
    qc::kernels::boll(close.data(), n, window, 2.0, mid.data(), upper.data(), lower.data());
    benchmark::DoNotOptimize(upper[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_IndicatorBoll)->Args({200000, 20});

static void BM_IndicatorRsi(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const std::vector<double> close = make_series(n, 100.0);
  std::vector<double> out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::rsi(close.data(), n, 14, out.data());
    benchmark::DoNotOptimize(out[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_IndicatorRsi)->Arg(200000);

static void BM_IndicatorMacd(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const std::vector<double> close = make_series(n, 100.0);
  std::vector<double> dif(n, 0.0);
  std::vector<double> dea(n, 0.0);
  std::vector<double> hist(n, 0.0);
  for (auto _ : state) {
    qc::kernels::macd(close.data(), n, 12, 26, 9, dif.data(), dea.data(), hist.data());
    benchmark::DoNotOptimize(hist[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_IndicatorMacd)->Arg(200000);

static void BM_IndicatorKdj(benchmark::State& state) {
  const auto n = static_cast<std::size_t>(state.range(0));
  const std::vector<double> close = make_series(n, 100.0);
  std::vector<double> high(n, 0.0);
  std::vector<double> low(n, 0.0);
  std::vector<double> volume = make_volume(n);
  for (std::size_t i = 0; i < n; ++i) {
    high[i] = close[i] + 1.5;
    low[i] = close[i] - 1.5;
  }
  std::vector<double> k(n, 0.0);
  std::vector<double> d(n, 0.0);
  std::vector<double> j(n, 0.0);
  std::vector<double> obv_out(n, 0.0);
  for (auto _ : state) {
    qc::kernels::kdj(high.data(), low.data(), close.data(), n, 9, 3, 3, k.data(), d.data(),
                     j.data());
    qc::kernels::obv(close.data(), volume.data(), n, obv_out.data());
    benchmark::DoNotOptimize(k[n / 2]);
    benchmark::ClobberMemory();
  }
  report_items(state, n);
}
BENCHMARK(BM_IndicatorKdj)->Arg(200000);
