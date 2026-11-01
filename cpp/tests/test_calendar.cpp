// Trading calendar: weekday generation, holiday removal, lookups, save/load and errors.
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "qcore/calendar.h"
#include "qcore/types.h"

namespace {

std::string temp_path(const char* tag) {
  static std::atomic<int> counter{0};
  const auto stamp =
      static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
  return (std::filesystem::temp_directory_path() /
          (std::string("qcore_test_") + tag + "_" + std::to_string(stamp) + "_" +
           std::to_string(counter.fetch_add(1)) + ".txt"))
      .string();
}

struct TempFile {
  std::string path;
  ~TempFile() {
    std::error_code ec;
    std::filesystem::remove(path, ec);
  }
};

}  // namespace

TEST_CASE("weekdays excludes weekends and synthetic holidays", "[calendar]") {
  const qc::TradingCalendar cal =
      qc::TradingCalendar::weekdays(20200101, 20200131, {20200101, 20200124});
  REQUIRE(cal.size() == 21);
  CHECK(cal.at(0) == 20200102);
  CHECK(cal.at(cal.size() - 1) == 20200131);
  CHECK(cal.index_of(20200102) == 0);
  CHECK(cal.index_of(20200106) == 2);
  CHECK(cal.index_of(20200101) == -1);  // holiday
  CHECK(cal.index_of(20200104) == -1);  // Saturday
  CHECK(cal.index_of(20200105) == -1);  // Sunday
  CHECK(cal.is_trading_day(20200131));
  CHECK(!cal.is_trading_day(20200124));
  CHECK(!cal.is_trading_day(20201231));
  // Strictly increasing, all weekdays.
  for (std::size_t i = 0; i < cal.size(); ++i) {
    if (i > 0)
      CHECK(cal.at(i) > cal.at(i - 1));
  }
}

TEST_CASE("weekdays handles leap years and single day ranges", "[calendar]") {
  const qc::TradingCalendar leap = qc::TradingCalendar::weekdays(20200228, 20200302);
  REQUIRE(leap.size() == 2);  // 2020-02-29 is Saturday
  CHECK(leap.at(0) == 20200228);
  CHECK(leap.at(1) == 20200302);
  const qc::TradingCalendar one = qc::TradingCalendar::weekdays(20200102, 20200102);
  REQUIRE(one.size() == 1);
  CHECK(one.at(0) == 20200102);
  const qc::TradingCalendar holiday_only =
      qc::TradingCalendar::weekdays(20200101, 20200101, {20200101});
  CHECK(holiday_only.empty());
  CHECK_THROWS_AS(qc::TradingCalendar::weekdays(20200110, 20200101), std::invalid_argument);
  CHECK_THROWS_AS(qc::TradingCalendar::weekdays(20200230, 20200301), std::invalid_argument);
  CHECK_THROWS_AS(qc::TradingCalendar::weekdays(20200101, 20200110, {20200230}),
                  std::invalid_argument);
}

TEST_CASE("index navigation and date navigation", "[calendar]") {
  const qc::TradingCalendar cal = qc::TradingCalendar::weekdays(20200101, 20200110, {20200101});
  REQUIRE(cal.size() == 7);
  CHECK(cal.next_index(0) == 1);
  CHECK(cal.next_index(cal.size() - 1) == cal.size());
  CHECK(cal.next_index(cal.size()) == cal.size());
  CHECK(cal.next_index(cal.size() + 5) == cal.size());
  CHECK(cal.prev_index(0) == cal.size());
  CHECK(cal.prev_index(1) == 0);
  CHECK(cal.prev_index(cal.size()) == cal.size() - 1);
  CHECK(cal.next(cal.at(0)) == cal.at(1));
  CHECK(cal.next(cal.at(cal.size() - 1)) == qc::kInvalidDate);
  CHECK(cal.prev(cal.at(0)) == qc::kInvalidDate);
  CHECK(cal.prev(cal.at(cal.size() - 1)) == cal.at(cal.size() - 2));
  CHECK(cal.next(20200104) == qc::kInvalidDate);  // Saturday is not in the calendar
  CHECK(cal.prev(20200104) == qc::kInvalidDate);
  CHECK_THROWS_AS(cal.at(cal.size()), std::out_of_range);
}

TEST_CASE("constructor rejects unsorted, duplicate and invalid dates", "[calendar]") {
  const std::vector<qc::Date> sorted{20200102, 20200103};
  const std::vector<qc::Date> unsorted{20200103, 20200102};
  const std::vector<qc::Date> duplicated{20200102, 20200102};
  const std::vector<qc::Date> invalid{20200102, 20200230};
  CHECK_NOTHROW(qc::TradingCalendar(sorted));
  CHECK_THROWS_AS(qc::TradingCalendar(unsorted), std::invalid_argument);
  CHECK_THROWS_AS(qc::TradingCalendar(duplicated), std::invalid_argument);
  CHECK_THROWS_AS(qc::TradingCalendar(invalid), std::invalid_argument);
  const qc::TradingCalendar empty{std::vector<qc::Date>{}};
  CHECK(empty.empty());
  CHECK(empty.size() == 0);
  CHECK(empty.index_of(20200102) == -1);
  CHECK(empty.next(20200102) == qc::kInvalidDate);
  CHECK(empty.prev(20200102) == qc::kInvalidDate);
  CHECK(empty.next_index(0) == 0);
  CHECK(empty.prev_index(0) == 0);
  CHECK_THROWS_AS(empty.at(0), std::out_of_range);
}

TEST_CASE("save and from_file roundtrip", "[calendar][io]") {
  const qc::TradingCalendar cal =
      qc::TradingCalendar::weekdays(20200101, 20200331, {20200101, 20200124});
  const TempFile file{temp_path("calendar")};
  cal.save(file.path);
  const qc::TradingCalendar loaded = qc::TradingCalendar::from_file(file.path);
  CHECK(loaded.dates() == cal.dates());
  {
    std::ifstream in(file.path);
    std::string first;
    std::getline(in, first);
    CHECK(first.rfind("#", 0) == 0);  // human readable header comment
  }
  // Rewriting the same path replaces the file atomically (POSIX) or via fallback.
  cal.save(file.path);
  CHECK(qc::TradingCalendar::from_file(file.path).size() == cal.size());
}

TEST_CASE("from_file accepts comments, blank lines and dashed dates", "[calendar][io]") {
  const TempFile file{temp_path("calendar_text")};
  {
    std::ofstream out(file.path);
    out << "# qcore-calendar v1\n\n20200102\r\n2020-01-03\n  # trailing comment\n20200106\n";
  }
  const qc::TradingCalendar cal = qc::TradingCalendar::from_file(file.path);
  REQUIRE(cal.size() == 3);
  CHECK(cal.at(0) == 20200102);
  CHECK(cal.at(1) == 20200103);
  CHECK(cal.at(2) == 20200106);
}

TEST_CASE("from_file reports IO and format errors", "[calendar][io]") {
  CHECK_THROWS_AS(qc::TradingCalendar::from_file(temp_path("missing_calendar")),
                  std::runtime_error);
  const TempFile bad{temp_path("calendar_bad")};
  {
    std::ofstream out(bad.path);
    out << "20200102\nnot-a-date\n";
  }
  CHECK_THROWS_AS(qc::TradingCalendar::from_file(bad.path), std::runtime_error);
  const TempFile unsorted{temp_path("calendar_unsorted")};
  {
    std::ofstream out(unsorted.path);
    out << "20200103\n20200102\n";
  }
  CHECK_THROWS_AS(qc::TradingCalendar::from_file(unsorted.path), std::runtime_error);
}
