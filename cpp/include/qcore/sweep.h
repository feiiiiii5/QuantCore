#pragma once
#include <atomic>
#include <cstddef>
#include <functional>
#include <vector>
#include "qcore/tpool.h"

namespace qc {
// Deterministic parallel parameter sweep. Tasks write to distinct output slots.
template <typename F>
void parallel_sweep(size_t n, size_t threads, F&& task) {
  if (n == 0)
    return;
  ThreadPool pool(threads);
  std::vector<std::future<void>> futures;
  futures.reserve(n);
  for (size_t i = 0; i < n; ++i)
    futures.emplace_back(pool.submit([&task, i]() { task(i); }));
  for (auto& f : futures)
    f.get();
}
}  // namespace qc
