#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>
#include "qcore/types.h"

namespace qc {
class TradingCalendar {
 public:
  TradingCalendar() = default;
  explicit TradingCalendar(std::vector<Date> dates);
  // Weekdays in [start,end], minus synthetic holidays (used by synthetic data and tests).
  static TradingCalendar weekdays(Date start, Date end, const std::vector<Date>& holidays = {});
  static TradingCalendar from_file(const std::string& path);
  bool empty() const {
    return dates_.empty();
  }
  size_t size() const {
    return dates_.size();
  }
  const std::vector<Date>& dates() const {
    return dates_;
  }
  Date at(size_t i) const;
  int index_of(Date d) const;  // -1 if absent
  bool is_trading_day(Date d) const;
  size_t next_index(size_t i) const;  // size() if none
  size_t prev_index(size_t i) const;  // size() if none
  Date next(Date d) const;
  Date prev(Date d) const;
  void save(const std::string& path) const;

 private:
  std::vector<Date> dates_;
  std::unordered_map<Date, int> index_;
};
}  // namespace qc
