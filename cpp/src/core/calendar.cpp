// Trading calendar: sorted unique trading dates with an O(1) date -> row index map.
//
// File format for save()/from_file() is human-readable text:
//   # qcore-calendar v1
//   20200102
//   20200103
//   ...
// Blank lines and lines starting with '#' are ignored; dates may be written as
// YYYYMMDD or YYYY-MM-DD. The constructor rejects unsorted / duplicate / invalid dates.
#include "qcore/calendar.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>

#include "date_util.h"
#include "qcore/types.h"

namespace qc {
namespace {

std::vector<Date> validate_dates(std::vector<Date> dates) {
  for (const Date d : dates) {
    if (!valid_date(d)) {
      throw std::invalid_argument("TradingCalendar: invalid date " + std::to_string(d));
    }
  }
  if (!std::is_sorted(dates.begin(), dates.end())) {
    throw std::invalid_argument("TradingCalendar: dates must be sorted ascending");
  }
  if (std::adjacent_find(dates.begin(), dates.end()) != dates.end()) {
    throw std::invalid_argument("TradingCalendar: duplicate dates are not allowed");
  }
  return dates;
}

std::string trim(const std::string& s) {
  const auto first = s.find_first_not_of(" \t\r\n");
  if (first == std::string::npos)
    return std::string();
  const auto last = s.find_last_not_of(" \t\r\n");
  return s.substr(first, last - first + 1);
}

}  // namespace

TradingCalendar::TradingCalendar(std::vector<Date> dates)
    : dates_(validate_dates(std::move(dates))) {
  index_.reserve(dates_.size() * 2 + 8);
  for (std::size_t i = 0; i < dates_.size(); ++i) {
    index_.emplace(dates_[i], static_cast<int>(i));
  }
}

TradingCalendar TradingCalendar::weekdays(Date start, Date end, const std::vector<Date>& holidays) {
  if (!valid_date(start) || !valid_date(end)) {
    throw std::invalid_argument("TradingCalendar::weekdays: start/end must be valid dates");
  }
  if (start > end) {
    throw std::invalid_argument("TradingCalendar::weekdays: start must be <= end");
  }
  std::unordered_set<Date> holiday_set;
  holiday_set.reserve(holidays.size() * 2 + 8);
  for (const Date h : holidays) {
    if (!valid_date(h)) {
      throw std::invalid_argument("TradingCalendar::weekdays: invalid holiday " +
                                  std::to_string(h));
    }
    holiday_set.insert(h);
  }
  std::vector<Date> out;
  out.reserve(static_cast<std::size_t>(end / 10000 - start / 10000 + 1) * 250 + 8);
  for (Date d = start;;) {
    if (detail::weekday(d) < 5 && holiday_set.find(d) == holiday_set.end()) {
      out.push_back(d);
    }
    if (d == end)
      break;  // also guards against overflow past 99991231
    d = detail::next_day(d);
  }
  return TradingCalendar(std::move(out));
}

TradingCalendar TradingCalendar::from_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("TradingCalendar::from_file: cannot open '" + path + "'");
  }
  std::vector<Date> dates;
  std::string raw;
  std::size_t line_no = 0;
  while (std::getline(in, raw)) {
    ++line_no;
    const std::string line = trim(raw);
    if (line.empty() || line[0] == '#')
      continue;
    try {
      dates.push_back(string_to_date(line));
    } catch (const std::invalid_argument& e) {
      throw std::runtime_error("TradingCalendar::from_file: " + path + ":" +
                               std::to_string(line_no) + ": " + e.what());
    }
  }
  if (in.bad()) {
    throw std::runtime_error("TradingCalendar::from_file: read error on '" + path + "'");
  }
  try {
    return TradingCalendar(std::move(dates));
  } catch (const std::invalid_argument& e) {
    throw std::runtime_error("TradingCalendar::from_file: " + path + ": " + e.what());
  }
}

Date TradingCalendar::at(std::size_t i) const {
  if (i >= dates_.size()) {
    throw std::out_of_range("TradingCalendar::at: index " + std::to_string(i) +
                            " out of range (size " + std::to_string(dates_.size()) + ")");
  }
  return dates_[i];
}

int TradingCalendar::index_of(Date d) const {
  const auto it = index_.find(d);
  return it == index_.end() ? -1 : it->second;
}

bool TradingCalendar::is_trading_day(Date d) const {
  return index_.find(d) != index_.end();
}

std::size_t TradingCalendar::next_index(std::size_t i) const {
  // No successor for the last row (or for an index at/after the end): returns size().
  if (i >= dates_.size())
    return dates_.size();
  if (i + 1 >= dates_.size())
    return dates_.size();
  return i + 1;
}

std::size_t TradingCalendar::prev_index(std::size_t i) const {
  // No predecessor for row 0: returns size(). i == size() maps to the last row.
  if (i == 0)
    return dates_.size();
  if (i > dates_.size())
    return dates_.size();
  return i - 1;
}

Date TradingCalendar::next(Date d) const {
  const int i = index_of(d);
  if (i < 0)
    return kInvalidDate;
  const std::size_t n = next_index(static_cast<std::size_t>(i));
  return n == dates_.size() ? kInvalidDate : dates_[n];
}

Date TradingCalendar::prev(Date d) const {
  const int i = index_of(d);
  if (i < 0)
    return kInvalidDate;
  const std::size_t p = prev_index(static_cast<std::size_t>(i));
  return p == dates_.size() ? kInvalidDate : dates_[p];
}

void TradingCalendar::save(const std::string& path) const {
  namespace fs = std::filesystem;
  const fs::path target(path);
  fs::path temp = target;
  temp += ".tmp";
  {
    std::ofstream out(temp, std::ios::binary | std::ios::trunc);
    if (!out) {
      throw std::runtime_error("TradingCalendar::save: cannot write '" + temp.string() + "'");
    }
    out << "# qcore-calendar v1\n";
    for (const Date d : dates_)
      out << date_to_string(d) << '\n';
    out.flush();
    if (!out) {
      std::error_code ignored;
      fs::remove(temp, ignored);
      throw std::runtime_error("TradingCalendar::save: write failed for '" + temp.string() + "'");
    }
  }
  std::error_code ec;
  fs::rename(temp, target, ec);
  if (ec) {
    // Windows / portable fallback: replace by explicit remove + rename.
    std::error_code ignored;
    fs::remove(target, ignored);
    fs::rename(temp, target, ec);
    if (ec) {
      fs::remove(temp, ignored);
      throw std::runtime_error("TradingCalendar::save: cannot replace '" + target.string() +
                               "': " + ec.message());
    }
  }
}

}  // namespace qc
