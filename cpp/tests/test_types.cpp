// Types: date validation/formatting, fixed-point helpers and the FNV-1a content hash.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <limits>
#include <string>

#include "qcore/types.h"

namespace {

void check_roundtrip(qc::Date date) {
  const std::string text = qc::date_to_string(date);
  CHECK(text.size() == 8);
  CHECK(qc::string_to_date(text) == date);
}

}  // namespace

TEST_CASE("valid_date accepts real calendar dates", "[types][date]") {
  CHECK(qc::valid_date(20200102));
  CHECK(qc::valid_date(19991231));
  CHECK(qc::valid_date(20240229));  // leap year
  CHECK(qc::valid_date(20000229));  // divisible by 400
  CHECK(!qc::valid_date(20190229));  // not a leap year
  CHECK(!qc::valid_date(19000229));  // divisible by 100, not 400
  CHECK(!qc::valid_date(20201301));  // month 13
  CHECK(!qc::valid_date(20200001));  // month 0
  CHECK(!qc::valid_date(20200100));  // day 0
  CHECK(!qc::valid_date(20200431));  // April has 30 days
  CHECK(!qc::valid_date(20200132));
  CHECK(!qc::valid_date(qc::kInvalidDate));
  CHECK(!qc::valid_date(-20200101));
}

TEST_CASE("date_to_string produces zero padded YYYYMMDD", "[types][date]") {
  CHECK(qc::date_to_string(20200102) == "20200102");
  CHECK(qc::date_to_string(19991231) == "19991231");
  CHECK(qc::date_to_string(20000229) == "20000229");
  CHECK_THROWS_AS(qc::date_to_string(0), std::invalid_argument);
  CHECK_THROWS_AS(qc::date_to_string(20200230), std::invalid_argument);
}

TEST_CASE("string_to_date accepts YYYYMMDD and YYYY-MM-DD", "[types][date]") {
  CHECK(qc::string_to_date("20200102") == 20200102);
  CHECK(qc::string_to_date("2020-01-02") == 20200102);
  CHECK(qc::string_to_date("1999-12-31") == 19991231);
  CHECK(qc::string_to_date("2024-02-29") == 20240229);
  const char* bad[] = {"",          "2020-1-2",    "2020010",  "202001021", "2020/01/02",
                       "abcd0102",  "20201301",    "20200230", "00000101",  " 20200102",
                       "2020-01-02x"};
  for (const char* text : bad) {
    CHECK_THROWS_AS(qc::string_to_date(text), std::invalid_argument);
  }
}

TEST_CASE("date components and roundtrip", "[types][date]") {
  CHECK(qc::make_date(2026, 7, 6) == 20260706);
  CHECK(qc::date_year(20260706) == 2026);
  CHECK(qc::date_month(20260706) == 7);
  CHECK(qc::date_day(20260706) == 6);
  for (const int year : {1999, 2000, 2019, 2020, 2024}) {
    for (int month = 1; month <= 12; ++month) {
      for (int day = 1; day <= 31; ++day) {
        const qc::Date date = qc::make_date(year, month, day);
        if (qc::valid_date(date)) check_roundtrip(date);
      }
    }
  }
}

TEST_CASE("fixed point helpers round consistently", "[types][fixed]") {
  CHECK(qc::to_px(1.5) == 15000);
  CHECK(qc::to_px(-1.5) == -15000);
  CHECK(qc::to_px(0.0) == 0);
  CHECK(qc::px_to_yuan(12345) == Catch::Approx(1.2345).margin(1e-15));
  CHECK(qc::to_money(1000000.0) == 10000000000LL);
  CHECK(qc::money_to_yuan(10000000000LL) == Catch::Approx(1000000.0));
  CHECK(qc::round_money(1.23455) == 12346);  // half away from zero at the 1e-4 grid
  CHECK(qc::round_money_from_ratio(12345, 0.5) == 6173);
  CHECK(qc::is_nan(qc::kNaN));
  CHECK(!qc::is_nan(1.0));
  CHECK(qc::is_nan(qc::safe_div(1.0, 0.0)));
  CHECK(qc::is_nan(qc::safe_div(qc::kNaN, 2.0)));
  CHECK(qc::safe_div(1.0, 4.0) == 0.25);
}

TEST_CASE("fnv1a64 hash is deterministic and content sensitive", "[types][hash]") {
  const std::uint64_t seed = qc::fnv1a64(nullptr, 0);
  CHECK(seed == 1469598103934665603ULL);
  const char a[] = "qcore";
  const char b[] = "qcorf";
  CHECK(qc::fnv1a64(a, 5) == qc::fnv1a64(a, 5));
  CHECK(qc::fnv1a64(a, 5) != qc::fnv1a64(b, 5));
  // Incremental chaining equals a single pass (used by the .qpanel writer).
  std::uint64_t chained = seed;
  chained = qc::fnv1a64(a, 2, chained);
  chained = qc::fnv1a64(a + 2, 3, chained);
  CHECK(chained == qc::fnv1a64(a, 5));
}

TEST_CASE("kernel NaN constant is a real NaN", "[types]") {
  CHECK(std::numeric_limits<double>::has_quiet_NaN);
  CHECK(qc::kNaN != qc::kNaN);
  CHECK(qc::kInf > 0.0);
}
