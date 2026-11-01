#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <filesystem>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qcore/expr.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

void require_value(double actual, double expected) {
  if (std::isnan(expected)) {
    REQUIRE(std::isnan(actual));
  } else {
    REQUIRE(actual == Catch::Approx(expected).margin(1e-12));
  }
}

// ---------------------------------------------------------------------------
// Small synthetic panels written to a temporary directory: the DSL tests hand-check
// expected numbers against a fixed grid rather than re-implementing the DSL.
// ---------------------------------------------------------------------------

struct TemporaryFile {
  explicit TemporaryFile(std::string value) : path(std::move(value)) {}
  ~TemporaryFile() {
    if (path.empty())
      return;
    std::error_code error;
    std::filesystem::remove(path, error);
  }
  TemporaryFile(const TemporaryFile&) = delete;
  TemporaryFile& operator=(const TemporaryFile&) = delete;
  TemporaryFile(TemporaryFile&& other) noexcept : path(std::move(other.path)) {
    other.path.clear();
  }
  TemporaryFile& operator=(TemporaryFile&&) = delete;

  std::string path;
};

struct PanelData {
  size_t n_sec = 0;
  size_t n_time = 0;
  std::vector<std::pair<std::string, std::vector<double>>> fields;  // security-major
};

std::string unique_panel_path() {
  static std::atomic<unsigned long long> counter{0};
  const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
  std::ostringstream name;
  name << "qcore_expr_eval_" << stamp << "_" << counter.fetch_add(1) << ".qpanel";
  return (std::filesystem::temp_directory_path() / name.str()).string();
}

qc::Date sequential_date(size_t index) {
  static constexpr int kDaysPerMonth[] = {31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  int year = 2024;
  size_t month = 0;
  size_t day = index + 1;
  while (day > static_cast<size_t>(kDaysPerMonth[month])) {
    day -= static_cast<size_t>(kDaysPerMonth[month]);
    ++month;
    if (month == 12) {
      month = 0;
      ++year;
    }
  }
  return qc::make_date(year, static_cast<int>(month) + 1, static_cast<int>(day));
}

std::vector<qc::Date> sequential_dates(size_t n_time) {
  std::vector<qc::Date> dates;
  dates.reserve(n_time);
  for (size_t t = 0; t < n_time; ++t)
    dates.push_back(sequential_date(t));
  return dates;
}

std::vector<qc::Security> synthetic_securities(size_t n_sec) {
  std::vector<qc::Security> securities;
  securities.reserve(n_sec);
  for (size_t s = 0; s < n_sec; ++s) {
    qc::Security security;
    security.sec_id = "S" + std::to_string(s);
    security.code = "00000" + std::to_string(s);
    security.name = "Synthetic" + std::to_string(s);
    security.board = 0;
    security.list_date = qc::make_date(2020, 1, 1);
    security.delist_date = qc::kInvalidDate;
    securities.push_back(std::move(security));
  }
  return securities;
}

TemporaryFile write_panel(const PanelData& data) {
  TemporaryFile file(unique_panel_path());
  qc::PanelWriter writer(data.n_sec, data.n_time, sequential_dates(data.n_time),
                         synthetic_securities(data.n_sec));
  for (const auto& field : data.fields) {
    REQUIRE(field.second.size() == data.n_sec * data.n_time);
    writer.add_field(field.first, qc::Layout::SecTime, field.second.data());
  }
  writer.write(file.path);
  return file;
}

class TestPanel {
 public:
  explicit TestPanel(PanelData data)
      : file_(write_panel(data)), panel_(qc::Panel::open(file_.path)) {}

  const qc::Panel& panel() const {
    return panel_;
  }

 private:
  TemporaryFile file_;
  qc::Panel panel_;
};

std::vector<double> column(const std::vector<std::vector<double>>& rows,
                           double (*transform)(double)) {
  std::vector<double> values;
  for (const auto& row : rows) {
    values.reserve(values.size() + row.size());
    for (const double value : row) {
      values.push_back(std::isnan(value) ? kNaN : transform(value));
    }
  }
  return values;
}

PanelData panel_from_rows(const std::vector<std::vector<double>>& rows) {
  PanelData data;
  data.n_sec = rows.size();
  data.n_time = rows.empty() ? 0 : rows.front().size();
  data.fields.emplace_back("close", column(rows, [](double value) { return value; }));
  return data;
}

// close grid shared by most eval tests: security 1 deliberately has a NaN at t=2.
PanelData main_panel_data() {
  const std::vector<std::vector<double>> close = {
      {1.0, 2.0, 3.0, 4.0, 5.0, 6.0},
      {2.0, 3.0, kNaN, 5.0, 6.0, 7.0},
      {3.0, 4.0, 5.0, 6.0, 7.0, 8.0},
  };
  PanelData data;
  data.n_sec = close.size();
  data.n_time = close.front().size();
  data.fields.emplace_back("close", column(close, [](double value) { return value; }));
  data.fields.emplace_back("open", column(close, [](double value) { return value - 0.5; }));
  data.fields.emplace_back("high", column(close, [](double value) { return value + 1.0; }));
  data.fields.emplace_back("low", column(close, [](double value) { return value - 1.0; }));
  data.fields.emplace_back("volume", column(close, [](double value) { return value * 100.0; }));
  data.fields.emplace_back("amount", column(close, [](double value) { return value * 1000.0; }));
  return data;
}

qc::Expression parse(const std::string& source) {
  return qc::Expression::parse(source);
}

}  // namespace

TEST_CASE("arithmetic precedence and unary operators", "[expr][eval]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  require_value(parse("1 + 2 * 3").eval(panel, 0, 0), 7.0);
  require_value(parse("(1 + 2) * 3").eval(panel, 0, 0), 9.0);
  require_value(parse("2 * 3 + 4 * 5").eval(panel, 0, 0), 26.0);
  require_value(parse("10 - 2 - 3").eval(panel, 0, 0), 5.0);
  require_value(parse("8 / 2 / 2").eval(panel, 0, 0), 2.0);
  require_value(parse("-2 * 3").eval(panel, 0, 0), -6.0);
  require_value(parse("2 * -3").eval(panel, 0, 0), -6.0);
  require_value(parse("2 * (3 - -4)").eval(panel, 0, 0), 14.0);
  require_value(parse("close").eval(panel, 0, 2), 3.0);
  require_value(parse("close + open").eval(panel, 0, 2), 5.5);
  require_value(parse("high - low").eval(panel, 0, 2), 2.0);
  require_value(parse("volume / close").eval(panel, 0, 2), 100.0);

  // Division by zero and overflow yield NaN, never infinity.
  require_value(parse("1 / 0").eval(panel, 0, 0), kNaN);
  require_value(parse("close / (close - close)").eval(panel, 0, 0), kNaN);
  require_value(parse("pow(10, 400)").eval(panel, 0, 0), kNaN);
}

TEST_CASE("comparison and logic return 1/0 with NaN propagation", "[expr][eval]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  require_value(parse("close > 2").eval(panel, 0, 2), 1.0);
  require_value(parse("close > 2").eval(panel, 0, 0), 0.0);
  require_value(parse("close >= 2").eval(panel, 0, 1), 1.0);
  require_value(parse("close < 2").eval(panel, 0, 0), 1.0);
  require_value(parse("close <= 1").eval(panel, 0, 1), 0.0);
  require_value(parse("close == 3").eval(panel, 0, 2), 1.0);
  require_value(parse("close != 3").eval(panel, 0, 2), 0.0);

  require_value(parse("close > 2 and volume > 0").eval(panel, 0, 2), 1.0);
  require_value(parse("close > 10 and volume > 0").eval(panel, 0, 2), 0.0);
  require_value(parse("close > 10 or volume > 0").eval(panel, 0, 2), 1.0);
  require_value(parse("not (close > 2)").eval(panel, 0, 2), 0.0);
  require_value(parse("not (close > 2)").eval(panel, 0, 0), 1.0);
  // Truthiness is "non-zero"; negative values are true.
  require_value(parse("-1 and 1").eval(panel, 0, 0), 1.0);
  require_value(parse("0 or -2").eval(panel, 0, 0), 1.0);
  require_value(parse("0 and 1").eval(panel, 0, 0), 0.0);

  // NaN operands make comparisons and logic NaN, not 0/1.
  require_value(parse("close > 2").eval(panel, 1, 2), kNaN);
  require_value(parse("close == close").eval(panel, 1, 2), kNaN);
  require_value(parse("not (close > 2)").eval(panel, 1, 2), kNaN);
  require_value(parse("close and 1").eval(panel, 1, 2), kNaN);
  require_value(parse("close + 1").eval(panel, 1, 2), kNaN);
  require_value(parse("abs(close)").eval(panel, 1, 2), kNaN);
  require_value(parse("min(close, 1)").eval(panel, 1, 2), kNaN);
}

TEST_CASE("elementwise math functions", "[expr][eval]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  require_value(parse("abs(-5)").eval(panel, 0, 0), 5.0);
  require_value(parse("abs(close)").eval(panel, 0, 0), 1.0);
  require_value(parse("log(1)").eval(panel, 0, 0), 0.0);
  require_value(parse("log(close)").eval(panel, 0, 0), 0.0);
  require_value(parse("log(0)").eval(panel, 0, 0), kNaN);
  require_value(parse("log(-1)").eval(panel, 0, 0), kNaN);
  require_value(parse("sqrt(4)").eval(panel, 0, 0), 2.0);
  require_value(parse("sqrt(close)").eval(panel, 0, 3), 2.0);
  require_value(parse("sqrt(-1)").eval(panel, 0, 0), kNaN);
  require_value(parse("pow(2, 3)").eval(panel, 0, 0), 8.0);
  require_value(parse("pow(2, -1)").eval(panel, 0, 0), 0.5);
  require_value(parse("pow(-4, 0.5)").eval(panel, 0, 0), kNaN);
  require_value(parse("pow(0, -1)").eval(panel, 0, 0), kNaN);
  require_value(parse("min(close, open)").eval(panel, 0, 2), 2.5);
  require_value(parse("max(close, open)").eval(panel, 0, 2), 3.0);
  require_value(parse("min(close, open) + max(high, low)").eval(panel, 0, 2), 6.5);
}

TEST_CASE("rolling windows and insufficient-window NaN", "[expr][eval]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  require_value(parse("ts_mean(close, 3)").eval(panel, 0, 2), 2.0);
  require_value(parse("ts_mean(close, 3)").eval(panel, 0, 4), 4.0);
  require_value(parse("ts_mean(close, 3)").eval(panel, 0, 1), kNaN);
  require_value(parse("ts_mean(close, 3)").eval(panel, 0, 0), kNaN);
  require_value(parse("ts_sum(close, 3)").eval(panel, 0, 3), 9.0);
  require_value(parse("ts_min(close, 2)").eval(panel, 0, 3), 3.0);
  require_value(parse("ts_max(close, 2)").eval(panel, 0, 3), 4.0);
  require_value(parse("ts_std(close, 3)").eval(panel, 0, 2), 1.0);
  require_value(parse("ts_std(close, 1)").eval(panel, 0, 2), kNaN);
  require_value(parse("ts_std(close, 3)").eval(panel, 0, 1), kNaN);

  // ts_rank: percentile of the newest value inside the window (0..1, average ties).
  require_value(parse("ts_rank(close, 3)").eval(panel, 0, 2), 1.0);
  require_value(parse("ts_rank(close, 3)").eval(panel, 0, 1), kNaN);
  require_value(parse("ts_rank(min(close, 2), 3)").eval(panel, 0, 2), 0.75);

  // delay reads only t-window, never the future.
  require_value(parse("delay(close, 1)").eval(panel, 0, 3), 3.0);
  require_value(parse("delay(close, 2)").eval(panel, 0, 2), 1.0);
  require_value(parse("delay(close, 0)").eval(panel, 2, 0), 3.0);
  require_value(parse("delay(close, 1)").eval(panel, 0, 0), kNaN);
  require_value(parse("delay(close, 1)").eval(panel, 1, 3), kNaN);

  // A NaN inside the window poisons every rolling reduction.
  require_value(parse("ts_mean(close, 2)").eval(panel, 1, 3), kNaN);
  require_value(parse("ts_sum(close, 3)").eval(panel, 1, 4), kNaN);
  require_value(parse("ts_rank(close, 3)").eval(panel, 1, 4), kNaN);
}

TEST_CASE("rolling and delay do not read future bars", "[expr][eval][lookahead]") {
  const PanelData past_a = panel_from_rows({{1.0, 2.0, 3.0, 4.0, 5.0, 6.0}});
  const PanelData past_b = panel_from_rows({{1.0, 2.0, 3.0, 100.0, 200.0, 300.0}});
  const TestPanel fixture_a(past_a);
  const TestPanel fixture_b(past_b);

  const qc::Expression expression = parse("ts_mean(close, 3) + delay(close, 1) * 2");
  const double value_a = expression.eval(fixture_a.panel(), 0, 2);
  const double value_b = expression.eval(fixture_b.panel(), 0, 2);
  require_value(value_a, 2.0 + 2.0 * 2.0);  // mean(1,2,3)=2; delay=2
  require_value(value_b, value_a);

  // The same expression at t=1 must only depend on bars 0..1 in both panels.
  const qc::Expression window = parse("ts_max(close, 2) + ts_sum(close, 2)");
  require_value(window.eval(fixture_a.panel(), 0, 1), 2.0 + 3.0);
  require_value(window.eval(fixture_b.panel(), 0, 1), 2.0 + 3.0);

  // A later bar that changes is invisible to earlier evaluation times.
  require_value(parse("close").eval(fixture_a.panel(), 0, 2), 3.0);
  require_value(parse("close").eval(fixture_b.panel(), 0, 2), 3.0);
  require_value(parse("close").eval(fixture_b.panel(), 0, 3), 100.0);
}

TEST_CASE("cross-sectional rank and zscore via eval_cross", "[expr][eval][cross]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  // t=0 close is 1, 2, 3 => percentile ranks and exact z-scores.
  require_value(parse("rank(close)").eval_cross(panel, 0, 0), 0.0);
  require_value(parse("rank(close)").eval_cross(panel, 1, 0), 0.5);
  require_value(parse("rank(close)").eval_cross(panel, 2, 0), 1.0);
  require_value(parse("zscore(close)").eval_cross(panel, 0, 0), -1.0);
  require_value(parse("zscore(close)").eval_cross(panel, 1, 0), 0.0);
  require_value(parse("zscore(close)").eval_cross(panel, 2, 0), 1.0);

  // t=5 close is 6, 7, 8 => same relative structure.
  require_value(parse("rank(close)").eval_cross(panel, 1, 5), 0.5);
  require_value(parse("zscore(close)").eval_cross(panel, 1, 5), 0.0);

  // NaN securities are excluded from the cross-section and stay NaN themselves.
  require_value(parse("rank(close)").eval_cross(panel, 0, 2), 0.0);
  require_value(parse("rank(close)").eval_cross(panel, 1, 2), kNaN);
  require_value(parse("rank(close)").eval_cross(panel, 2, 2), 1.0);
  require_value(parse("zscore(close)").eval_cross(panel, 0, 2), -1.0 / std::sqrt(2.0));
  require_value(parse("zscore(close)").eval_cross(panel, 1, 2), kNaN);
  require_value(parse("zscore(close)").eval_cross(panel, 2, 2), 1.0 / std::sqrt(2.0));

  // Cross-sectional function nested under a time-series window.
  const qc::Expression nested = parse("rank(zscore(close))");
  require_value(nested.eval_cross(panel, 1, 0), 0.5);
  require_value(parse("rank(ts_mean(close, 2))").eval_cross(panel, 1, 4), 0.5);
  require_value(parse("ts_mean(rank(close), 2)").eval_cross(panel, 2, 5), 1.0);
  // Constant cross-section: all values tie, so every rank is 0.5.
  require_value(parse("rank(1)").eval_cross(panel, 1, 0), 0.5);
}

TEST_CASE("eval and eval_cross agree pointwise", "[expr][eval][cross]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();
  const qc::Expression expression = parse("rank(ts_mean(close, 2)) / 2 + zscore(volume)");
  REQUIRE(expression.explain().find("cross_sectional: true") != std::string::npos);
  for (size_t sec = 0; sec < panel.n_sec(); ++sec) {
    for (size_t time = 0; time < panel.n_time(); ++time) {
      require_value(expression.eval(panel, sec, time), expression.eval_cross(panel, sec, time));
    }
  }
}

TEST_CASE("out-of-range indices and empty expressions are NaN", "[expr][eval][bounds]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();
  const qc::Expression expression = parse("ts_mean(close, 2)");

  require_value(expression.eval(panel, 3, 0), kNaN);
  require_value(expression.eval(panel, 0, 6), kNaN);
  require_value(expression.eval(panel, 100, 100), kNaN);
  require_value(expression.eval_cross(panel, 3, 0), kNaN);
  require_value(expression.eval_cross(panel, 0, 6), kNaN);

  const qc::Expression empty;
  require_value(empty.eval(panel, 0, 0), kNaN);
  require_value(empty.eval_cross(panel, 0, 0), kNaN);
  require_value(parse("1 + 1").eval(panel, 3, 0), kNaN);
}

TEST_CASE("missing fields throw and returns is derived from close", "[expr][eval][fields]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  // `returns` is derived as close[t]/close[t-1]-1 when the panel has no returns column.
  require_value(parse("returns").eval(panel, 0, 2), 3.0 / 2.0 - 1.0);
  require_value(parse("returns").eval(panel, 0, 0), kNaN);
  require_value(parse("returns").eval(panel, 1, 3), kNaN);  // close[t-1] is NaN
  require_value(parse("returns + 1").eval(panel, 0, 3), (4.0 / 3.0 - 1.0) + 1.0);

  // A field the panel does not carry is a hard error, with a clear message.
  const TestPanel sparse(panel_from_rows({{1.0, 2.0, 3.0}}));
  bool threw = false;
  try {
    (void)parse("amount").eval(sparse.panel(), 0, 0);
  } catch (const std::invalid_argument& error) {
    threw = true;
    REQUIRE(std::string(error.what()).find("amount") != std::string::npos);
  }
  REQUIRE(threw);

  // An explicit returns column wins over the derived version.
  PanelData explicit_returns = panel_from_rows({{1.0, 2.0, 3.0}});
  explicit_returns.fields.emplace_back("returns", std::vector<double>{0.25, 0.25, 0.25});
  const TestPanel explicit_fixture(explicit_returns);
  require_value(parse("returns").eval(explicit_fixture.panel(), 0, 0), 0.25);
}

TEST_CASE("CSE sharing preserves values", "[expr][eval][cse]") {
  const TestPanel fixture(main_panel_data());
  const qc::Panel& panel = fixture.panel();

  require_value(parse("ts_mean(close, 3) / ts_mean(close, 3)").eval(panel, 0, 4), 1.0);
  require_value(parse("close / close").eval(panel, 0, 3), 1.0);
  require_value(parse("close - close").eval(panel, 0, 3), 0.0);
  require_value(parse("min(close, open) + min(open, close)").eval(panel, 0, 2), 5.0);
  require_value(parse("(close + open) * (close + open)").eval(panel, 0, 2), 30.25);
}

TEST_CASE("TimeSec layout fields read the same values", "[expr][eval][layout]") {
  // Row-major [time][security]: t0=(1,5), t1=(2,6), t2=(3,7), t3=(4,8).
  const std::vector<double> close = {1.0, 5.0, 2.0, 6.0, 3.0, 7.0, 4.0, 8.0};
  TemporaryFile file(unique_panel_path());
  qc::PanelWriter writer(2, 4, sequential_dates(4), synthetic_securities(2));
  writer.add_field("close", qc::Layout::TimeSec, close.data());
  writer.write(file.path);
  const qc::Panel panel = qc::Panel::open(file.path);

  require_value(parse("close").eval(panel, 1, 2), 7.0);
  require_value(parse("close").eval(panel, 0, 3), 4.0);
  require_value(parse("ts_mean(close, 2)").eval(panel, 0, 3), 3.5);
  require_value(parse("delay(close, 1)").eval(panel, 1, 3), 7.0);
  require_value(parse("rank(close)").eval_cross(panel, 0, 2), 0.0);
  require_value(parse("rank(close)").eval_cross(panel, 1, 2), 1.0);
}
