#pragma once
// Internal proleptic-Gregorian date helpers shared by types.cpp and calendar.cpp.
// Not part of the public qcore API; keep it dependency-free and header-inline.
#include <cstdint>

#include "qcore/types.h"

namespace qc::detail {

inline bool is_leap_year(int y) { return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0); }

// Days in month m of year y; returns 0 for an out-of-range month.
inline int days_in_month(int y, int m) {
  static constexpr int kDays[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if (m < 1 || m > 12) return 0;
  return (m == 2 && is_leap_year(y)) ? 29 : kDays[m - 1];
}

// Days since 1970-01-01 for a valid Date (Howard Hinnant's days_from_civil).
inline int64_t days_from_civil(int y, int m, int d) {
  y -= (m <= 2) ? 1 : 0;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(y - era * 400);              // [0, 399]
  const unsigned doy = static_cast<unsigned>((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1);
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;             // [0, 146096]
  return era * 146097 + static_cast<int64_t>(doe) - 719468;
}

// 0 = Monday .. 6 = Sunday. Caller must pass a valid_date.
inline int weekday(Date dt) {
  const int64_t days = days_from_civil(date_year(dt), date_month(dt), date_day(dt));
  // 1970-01-01 was a Thursday, i.e. index 3 when Monday == 0.
  return static_cast<int>((days % 7 + 7 + 3) % 7);
}

// Next calendar day; caller must pass a valid_date < 99991231.
inline Date next_day(Date dt) {
  int y = date_year(dt);
  int m = date_month(dt);
  int d = date_day(dt) + 1;
  if (d > days_in_month(y, m)) {
    d = 1;
    if (++m > 12) {
      m = 1;
      ++y;
    }
  }
  return make_date(y, m, d);
}

}  // namespace qc::detail
