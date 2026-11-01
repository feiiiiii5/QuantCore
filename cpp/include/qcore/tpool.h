#pragma once
#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <functional>
#include <future>
#include <mutex>
#include <queue>
#include <thread>
#include <utility>
#include <vector>

namespace qc {
// Fixed-size thread pool. No OpenMP; task granularity is a backtest/factor job.
class ThreadPool {
 public:
  explicit ThreadPool(size_t threads = 0);
  ~ThreadPool();
  ThreadPool(const ThreadPool&) = delete;
  ThreadPool& operator=(const ThreadPool&) = delete;
  size_t size() const { return workers_.size(); }
  template <typename F>
  auto submit(F&& f) -> std::future<decltype(f())> {
    using R = decltype(f());
    auto task = std::make_shared<std::packaged_task<R()>>(std::forward<F>(f));
    std::future<R> fut = task->get_future();
    {
      std::lock_guard<std::mutex> lk(mu_);
      if (stop_) throw std::runtime_error("ThreadPool stopped");
      tasks_.emplace([task]() { (*task)(); });
    }
    cv_.notify_one();
    return fut;
  }
  // Deterministic parallel_for: results are written by index; caller owns out-of-order writes.
  void parallel_for(size_t n, const std::function<void(size_t)>& fn, size_t min_grain = 1);
  void wait_idle();
 private:
  void worker_loop();
  std::vector<std::thread> workers_;
  std::queue<std::function<void()>> tasks_;
  std::mutex mu_;
  std::condition_variable cv_;
  std::condition_variable idle_cv_;
  std::atomic<bool> stop_{false};
  std::atomic<size_t> active_{0};
};
}  // namespace qc
