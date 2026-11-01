// Google Benchmark: .qpanel write / fast mmap open / verified open (full content hash) / field scan.
#include <benchmark/benchmark.h>

#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

std::string bench_panel_path(const char* tag) {
  static std::atomic<int> counter{0};
  const auto stamp =
      static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
  return (std::filesystem::temp_directory_path() /
          (std::string("qcore_bench_") + tag + "_" + std::to_string(stamp) + "_" +
           std::to_string(counter.fetch_add(1)) + ".qpanel"))
      .string();
}

struct Fixture {
  std::size_t n_sec;
  std::size_t n_time;
  std::vector<qc::Date> dates;
  std::vector<qc::Security> securities;
  std::vector<std::vector<double>> fields;

  Fixture(std::size_t ns, std::size_t nt, std::size_t n_fields) : n_sec(ns), n_time(nt) {
    dates.reserve(nt);
    qc::Date date = 20100104;
    for (std::size_t t = 0; t < nt; ++t) {
      dates.push_back(date);
      // advance by one calendar day and skip weekends (close enough for a benchmark)
      int day = qc::date_day(date) + 1;
      int month = qc::date_month(date);
      int year = qc::date_year(date);
      if (day > 28) {
        day = 1;
        if (++month > 12) {
          month = 1;
          ++year;
        }
      }
      date = qc::make_date(year, month, day);
      while (date % 100 == 4 || date % 100 == 5) {  // crude weekday skip for synthetic dates
        day += 1;
        if (day > 28) {
          day = 1;
          month += 1;
          if (month > 12) {
            month = 1;
            year += 1;
          }
        }
        date = qc::make_date(year, month, day);
      }
    }
    securities.reserve(ns);
    for (std::size_t s = 0; s < ns; ++s) {
      qc::Security sec;
      sec.sec_id = "SEC" + std::to_string(s);
      sec.code = "600000";
      sec.name = "synthetic";
      sec.board = 0;
      sec.list_date = 20000104;
      securities.push_back(sec);
    }
    fields.resize(n_fields);
    for (std::size_t f = 0; f < n_fields; ++f) {
      auto& data = fields[f];
      data.resize(ns * nt);
      for (std::size_t i = 0; i < data.size(); ++i) {
        data[i] = static_cast<double>(i % 977) * 0.01 + static_cast<double>(f);
      }
    }
  }
};

Fixture& fixture(std::size_t n_sec, std::size_t n_time, std::size_t n_fields) {
  static Fixture small(200, 250, 4);
  static Fixture medium(1000, 500, 4);
  if (n_sec == 200) return small;
  return medium;
}

}  // namespace

static void BM_PanelWrite(benchmark::State& state) {
  const auto n_sec = static_cast<std::size_t>(state.range(0));
  const auto n_time = static_cast<std::size_t>(state.range(1));
  Fixture& data = fixture(n_sec, n_time, 4);
  const std::string path = bench_panel_path("write");
  for (auto _ : state) {
    qc::PanelWriter writer(data.n_sec, data.n_time, data.dates, data.securities);
    for (std::size_t f = 0; f < data.fields.size(); ++f) {
      writer.add_field("f" + std::to_string(f), qc::Layout::SecTime, data.fields[f].data());
    }
    writer.set_metadata("{\"bench\":\"panel_write\"}");
    writer.write(path);
    benchmark::DoNotOptimize(path.size());
  }
  std::error_code ec;
  std::filesystem::remove(path, ec);
  state.SetItemsProcessed(state.iterations() * static_cast<std::int64_t>(data.n_sec * data.n_time));
}
BENCHMARK(BM_PanelWrite)->ArgsProduct({{200, 1000}, {250, 500}})->Unit(benchmark::kMillisecond);

static void BM_PanelOpenFast(benchmark::State& state) {
  const auto n_sec = static_cast<std::size_t>(state.range(0));
  const auto n_time = static_cast<std::size_t>(state.range(1));
  Fixture& data = fixture(n_sec, n_time, 4);
  const std::string path = bench_panel_path("open");
  {
    qc::PanelWriter writer(data.n_sec, data.n_time, data.dates, data.securities);
    for (std::size_t f = 0; f < data.fields.size(); ++f) {
      writer.add_field("f" + std::to_string(f), qc::Layout::SecTime, data.fields[f].data());
    }
    writer.write(path);
  }
  std::error_code ec;
  const auto bytes = std::filesystem::file_size(path, ec);
  for (auto _ : state) {
    qc::Panel panel = qc::Panel::open(path);
    benchmark::DoNotOptimize(panel.content_hash());
    benchmark::DoNotOptimize(panel.field("f0").at(0, 0));
  }
  std::filesystem::remove(path, ec);
  if (!ec) state.SetBytesProcessed(state.iterations() * static_cast<std::int64_t>(bytes));
}
BENCHMARK(BM_PanelOpenFast)->ArgsProduct({{200, 1000}, {250, 500}})->Unit(benchmark::kMillisecond);

static void BM_PanelOpenVerified(benchmark::State& state) {
  const auto n_sec = static_cast<std::size_t>(state.range(0));
  const auto n_time = static_cast<std::size_t>(state.range(1));
  Fixture& data = fixture(n_sec, n_time, 4);
  const std::string path = bench_panel_path("open_verified");
  {
    qc::PanelWriter writer(data.n_sec, data.n_time, data.dates, data.securities);
    for (std::size_t f = 0; f < data.fields.size(); ++f) {
      writer.add_field("f" + std::to_string(f), qc::Layout::SecTime, data.fields[f].data());
    }
    writer.write(path);
  }
  std::error_code ec;
  const auto bytes = std::filesystem::file_size(path, ec);
  for (auto _ : state) {
    qc::Panel panel = qc::Panel::open(path, /*verify_content=*/true);
    benchmark::DoNotOptimize(panel.content_hash());
  }
  std::filesystem::remove(path, ec);
  if (!ec) state.SetBytesProcessed(state.iterations() * static_cast<std::int64_t>(bytes));
}
BENCHMARK(BM_PanelOpenVerified)->ArgsProduct({{200, 1000}, {250, 500}})->Unit(benchmark::kMillisecond);

static void BM_PanelFieldScan(benchmark::State& state) {
  Fixture& data = fixture(1000, 500, 4);
  const std::string path = bench_panel_path("scan");
  {
    qc::PanelWriter writer(data.n_sec, data.n_time, data.dates, data.securities);
    for (std::size_t f = 0; f < data.fields.size(); ++f) {
      writer.add_field("f" + std::to_string(f), qc::Layout::SecTime, data.fields[f].data());
    }
    writer.write(path);
  }
  const qc::Panel panel = qc::Panel::open(path);
  const qc::FieldView field = panel.field("f0");
  for (auto _ : state) {
    double sum = 0.0;
    for (std::size_t s = 0; s < panel.n_sec(); ++s) {
      for (std::size_t t = 0; t < panel.n_time(); ++t) sum += field.at(s, t);
    }
    benchmark::DoNotOptimize(sum);
    benchmark::ClobberMemory();
  }
  std::error_code ec;
  std::filesystem::remove(path, ec);
  state.SetItemsProcessed(state.iterations() *
                          static_cast<std::int64_t>(panel.n_sec() * panel.n_time()));
}
BENCHMARK(BM_PanelFieldScan)->Unit(benchmark::kMillisecond);
