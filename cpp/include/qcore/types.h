#pragma once
// QuantCore fixed-point primitives. Prices/amounts are 1e-4 CNY; quantities are shares.
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>

namespace qc {
using Px = int64_t;     // 1e-4 CNY
using Money = int64_t;  // 1e-4 CNY
using Qty = int64_t;    // shares
using Date = int32_t;   // YYYYMMDD
constexpr int64_t kPriceScale = 10000;
constexpr int64_t kMoneyScale = 10000;
constexpr Date kInvalidDate = 0;
constexpr Qty kInvalidQty = std::numeric_limits<Qty>::min();
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kInf = std::numeric_limits<double>::infinity();

inline Px to_px(double yuan) {
  return static_cast<Px>(std::llround(yuan * kPriceScale));
}
inline Money to_money(double yuan) {
  return static_cast<Money>(std::llround(yuan * kMoneyScale));
}
inline double px_to_yuan(Px p) {
  return static_cast<double>(p) / kPriceScale;
}
inline double money_to_yuan(Money m) {
  return static_cast<double>(m) / kMoneyScale;
}
inline bool is_nan(double v) {
  return std::isnan(v);
}
inline double safe_div(double a, double b) {
  return (b == 0.0 || is_nan(b)) ? kNaN : a / b;
}

// Round a monetary amount to the nearest 1e-4 CNY; C++ llround is round-half-away-from-zero.
inline Money round_money(double yuan) {
  return static_cast<Money>(std::llround(yuan * kMoneyScale));
}
inline Money round_money_from_ratio(Money amount, double ratio) {
  return static_cast<Money>(std::llround(static_cast<double>(amount) * ratio));
}
inline Date make_date(int y, int m, int d) {
  return static_cast<Date>(y * 10000 + m * 100 + d);
}
inline int date_year(Date d) {
  return d / 10000;
}
inline int date_month(Date d) {
  return (d / 100) % 100;
}
inline int date_day(Date d) {
  return d % 100;
}
std::string date_to_string(Date d);
Date string_to_date(const std::string& s);
bool valid_date(Date d);

// Simple FNV-1a 64 used for content hashes.
inline uint64_t fnv1a64(const void* data, size_t n, uint64_t seed = 1469598103934665603ULL) {
  const auto* p = static_cast<const uint8_t*>(data);
  uint64_t h = seed;
  for (size_t i = 0; i < n; ++i) {
    h ^= p[i];
    h *= 1099511628211ULL;
  }
  return h;
}
}  // namespace qc
