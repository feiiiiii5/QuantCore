// Thread pool: fixed size, deterministic parallel_for, wait_idle and destructor drain.
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <cmath>
#include <cstddef>
#include <functional>
#include <future>
#include <numeric>
#include <stdexcept>
#include <vector>

#include "qcore/tpool.h"

TEST_CASE("pool size and default resolution", "[tpool]") {
  qc::ThreadPool pool(4);
  CHECK(pool.size() == 4);
  qc::ThreadPool automatic(0);
  CHECK(automatic.size() >= 1);
  CHECK(automatic.size() <= 1024);
}

TEST_CASE("parallel_for is deterministic across thread counts and grains", "[tpool]") {
  constexpr std::size_t kCount = 1000;
  const auto compute = [](std::size_t i) {
    return static_cast<double>(i) * 0.5 - std::sqrt(static_cast<double>(i));
  };
  const auto run = [&compute](std::size_t threads, std::size_t min_grain) {
    std::vector<double> out(kCount, -1.0);
    qc::ThreadPool pool(threads);
    pool.parallel_for(kCount, [&out, &compute](std::size_t i) { out[i] = compute(i); }, min_grain);
    return out;
  };
  const std::vector<double> single = run(1, 1);
  const std::vector<double> multi = run(8, 1);
  const std::vector<double> coarse = run(4, 17);
  REQUIRE(single.size() == kCount);
  CHECK(single == multi);
  CHECK(single == coarse);
  for (std::size_t i = 0; i < kCount; ++i)
    CHECK(single[i] == compute(i));
}

TEST_CASE("parallel_for visits every index exactly once", "[tpool]") {
  constexpr std::size_t kCount = 257;
  std::vector<int> visits(kCount, 0);
  qc::ThreadPool pool(3);
  for (int round = 0; round < 5; ++round) {
    pool.parallel_for(
        kCount,
        [&visits](std::size_t i) {
          const int previous = visits[i];
          visits[i] = previous + 1;
        },
        2);
  }
  for (std::size_t i = 0; i < kCount; ++i)
    CHECK(visits[i] == 5);
  // n == 0 is a no-op.
  bool called = false;
  pool.parallel_for(0, [&called](std::size_t) { called = true; });
  CHECK(!called);
}

TEST_CASE("parallel_for propagates exceptions and keeps the pool usable", "[tpool]") {
  qc::ThreadPool pool(4);
  CHECK_THROWS_AS(pool.parallel_for(64,
                                    [](std::size_t i) {
                                      if (i == 7)
                                        throw std::runtime_error("boom");
                                    }),
                  std::runtime_error);
  std::atomic<int> done{0};
  pool.parallel_for(32, [&done](std::size_t) { done.fetch_add(1, std::memory_order_relaxed); });
  CHECK(done.load() == 32);
  const std::function<void(std::size_t)> empty_function;
  CHECK_THROWS_AS(qc::ThreadPool(2).parallel_for(4, empty_function), std::invalid_argument);
}

TEST_CASE("submit futures and wait_idle", "[tpool]") {
  qc::ThreadPool pool(4);
  std::atomic<int> counter{0};
  std::vector<std::future<int>> futures;
  for (int i = 0; i < 64; ++i) {
    futures.push_back(pool.submit([i, &counter]() {
      counter.fetch_add(1, std::memory_order_relaxed);
      return i * 2;
    }));
  }
  pool.wait_idle();
  CHECK(counter.load() == 64);
  for (int i = 0; i < 64; ++i)
    CHECK(futures[static_cast<std::size_t>(i)].get() == i * 2);
  pool.wait_idle();  // idempotent when there is nothing to do
}

TEST_CASE("destructor drains queued tasks", "[tpool]") {
  std::vector<std::future<int>> futures;
  {
    qc::ThreadPool pool(2);
    for (int i = 0; i < 50; ++i)
      futures.push_back(pool.submit([i]() { return i; }));
  }  // destructor must run every queued task before joining
  REQUIRE(futures.size() == 50);
  for (int i = 0; i < 50; ++i)
    CHECK(futures[static_cast<std::size_t>(i)].get() == i);
}
