// Date string <-> Date (YYYYMMDD int32) conversion and validation.
//
// Accepted text forms for string_to_date: exactly "YYYYMMDD" (8 digits) or
// "YYYY-MM-DD" (zero padded). Invalid or impossible dates throw std::invalid_argument;
// date_to_string does the same for an invalid Date. kInvalidDate (0) is not printable
// and is never returned from string_to_date.
#include <cstdio>
#include <stdexcept>
#include <string>

#include "date_util.h"
#include "qcore/types.h"

namespace qc {
namespace {

[[noreturn]] void throw_parse_error(const std::string& s, const char* why) {
  throw std::invalid_argument("string_to_date: invalid date '" + s + "' (" + why + ")");
}

bool is_digit(char c) { return c >= '0' && c <= '9'; }

// Reads `count` ASCII digits starting at pos; returns false on non-digit input.
bool read_digits(const std::string& s, std::size_t pos, std::size_t count, int& out) {
  int v = 0;
  for (std::size_t i = 0; i < count; ++i) {
    const char c = s[pos + i];
    if (!is_digit(c)) return false;
    v = v * 10 + (c - '0');
  }
  out = v;
  return true;
}

}  // namespace

bool valid_date(Date d) {
  if (d <= 0) return false;
  const int y = date_year(d);
  const int m = date_month(d);
  const int dd = date_day(d);
  if (y < 1 || y > 9999 || m < 1 || m > 12) return false;
  return dd >= 1 && dd <= detail::days_in_month(y, m);
}

std::string date_to_string(Date d) {
  if (!valid_date(d)) {
    throw std::invalid_argument("date_to_string: invalid date " + std::to_string(d));
  }
  char buf[16];
  // Zero padded, 8 characters for years >= 1 (the internal representation is YYYYMMDD).
  const int n = std::snprintf(buf, sizeof(buf), "%04d%02d%02d", date_year(d), date_month(d),
                              date_day(d));
  if (n != 8) {
    throw std::invalid_argument("date_to_string: date out of representable range " +
                                std::to_string(d));
  }
  return std::string(buf, static_cast<std::size_t>(n));
}

Date string_to_date(const std::string& s) {
  int y = 0;
  int m = 0;
  int d = 0;
  if (s.size() == 8) {
    if (!read_digits(s, 0, 4, y) || !read_digits(s, 4, 2, m) || !read_digits(s, 6, 2, d)) {
      throw_parse_error(s, "expected YYYYMMDD");
    }
  } else if (s.size() == 10) {
    if (s[4] != '-' || s[7] != '-') throw_parse_error(s, "expected YYYY-MM-DD");
    if (!read_digits(s, 0, 4, y) || !read_digits(s, 5, 2, m) || !read_digits(s, 8, 2, d)) {
      throw_parse_error(s, "expected YYYY-MM-DD");
    }
  } else {
    throw_parse_error(s, "expected 8 or 10 characters");
  }
  if (y < 1 || y > 9999) throw_parse_error(s, "year out of range");
  if (m < 1 || m > 12) throw_parse_error(s, "month out of range");
  if (d < 1 || d > detail::days_in_month(y, m)) throw_parse_error(s, "day out of range");
  return make_date(y, m, d);
}

}  // namespace qc
