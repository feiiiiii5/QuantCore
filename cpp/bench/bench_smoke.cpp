#include <benchmark/benchmark.h>
static void BM_Noop(benchmark::State& state) {
  for (auto _ : state) { benchmark::DoNotOptimize(_); }
}
BENCHMARK(BM_Noop);
