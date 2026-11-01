// Fixed-size thread pool (ADR-006: no OpenMP). ThreadPool::parallel_for is deterministic:
// static, disjoint index chunks are assigned once, so callers that write distinct output
// slots get bit-identical results for any worker count. parallel_for blocks until done and
// is not re-entrant (do not call it from inside a pooled task).
#include "qcore/tpool.h"

#include <algorithm>
#include <exception>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

namespace qc {
namespace {

std::size_t resolve_threads(std::size_t threads) {
  if (threads != 0) return threads;
  const unsigned hw = std::thread::hardware_concurrency();
  return hw == 0 ? std::size_t{1} : static_cast<std::size_t>(hw);
}

}  // namespace

ThreadPool::ThreadPool(size_t threads) {
  const std::size_t n = resolve_threads(threads);
  workers_.reserve(n);
  try {
    for (std::size_t i = 0; i < n; ++i) {
      workers_.emplace_back([this]() { worker_loop(); });
    }
  } catch (...) {
    {
      std::lock_guard<std::mutex> lk(mu_);
      stop_.store(true);
    }
    cv_.notify_all();
    for (auto& t : workers_) {
      if (t.joinable()) t.join();
    }
    throw;
  }
}

ThreadPool::~ThreadPool() {
  {
    std::lock_guard<std::mutex> lk(mu_);
    stop_.store(true);
  }
  cv_.notify_all();
  for (auto& t : workers_) {
    if (t.joinable()) t.join();
  }
}

void ThreadPool::worker_loop() {
  for (;;) {
    std::function<void()> task;
    {
      std::unique_lock<std::mutex> lk(mu_);
      cv_.wait(lk, [this]() { return stop_.load() || !tasks_.empty(); });
      if (tasks_.empty()) {
        if (stop_.load()) return;
        continue;
      }
      task = std::move(tasks_.front());
      tasks_.pop();
      // Busy count is maintained under mu_ so wait_idle() observes a consistent state.
      active_.fetch_add(1, std::memory_order_relaxed);
    }
    try {
      task();
    } catch (...) {
      // Submitted tasks are packaged_tasks and never throw here; guard regardless so a
      // worker can never terminate the process.
    }
    {
      std::lock_guard<std::mutex> lk(mu_);
      active_.fetch_sub(1, std::memory_order_relaxed);
    }
    idle_cv_.notify_all();
  }
}

void ThreadPool::parallel_for(size_t n, const std::function<void(size_t)>& fn,
                              size_t min_grain) {
  if (n == 0) return;
  if (!fn) throw std::invalid_argument("ThreadPool::parallel_for: empty function");
  static constexpr std::size_t kChunksPerWorker = 4;

  struct ErrorSlot {
    std::mutex mu;
    std::vector<std::exception_ptr> errors;
  };

  const std::size_t workers = std::max<std::size_t>(workers_.size(), 1);
  const std::size_t grain = std::max<std::size_t>(min_grain, 1);
  std::size_t chunk = (n + workers * kChunksPerWorker - 1) / (workers * kChunksPerWorker);
  if (chunk < grain) chunk = grain;
  const std::size_t chunks = (n + chunk - 1) / chunk;

  auto errors = std::make_shared<ErrorSlot>();
  errors->errors.assign(chunks, std::exception_ptr());
  {
    std::lock_guard<std::mutex> lk(mu_);
    if (stop_.load()) throw std::runtime_error("ThreadPool stopped");
    for (std::size_t c = 0; c < chunks; ++c) {
      const std::size_t begin = c * chunk;
      const std::size_t end = std::min(n, begin + chunk);
      // fn is captured by reference: parallel_for blocks until every chunk has finished.
      tasks_.emplace([&fn, errors, c, begin, end]() {
        try {
          for (std::size_t i = begin; i < end; ++i) fn(i);
        } catch (...) {
          std::lock_guard<std::mutex> elk(errors->mu);
          errors->errors[c] = std::current_exception();
        }
      });
    }
  }
  cv_.notify_all();
  wait_idle();
  // Deterministic error reporting: lowest failing chunk wins.
  for (const std::exception_ptr& e : errors->errors) {
    if (e) std::rethrow_exception(e);
  }
}

void ThreadPool::wait_idle() {
  std::unique_lock<std::mutex> lk(mu_);
  idle_cv_.wait(lk, [this]() { return tasks_.empty() && active_.load() == 0; });
}

}  // namespace qc
