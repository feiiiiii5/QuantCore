#include "rules.h"

#include <cmath>

namespace qc {

int64_t board_lot(const RuleSet& rules, int board) {
  switch (board) {
    case 2:
      return rules.star_lot;  // STAR: >= 200 shares then 1-share increments
    case 3:
      return rules.bse_lot;  // BSE: >= 100 shares then 1-share increments
    case 1:
      return rules.main_lot;  // GEM: 100-share multiples (TODO(verify))
    default:
      return rules.main_lot;
  }
}

Qty canon_buy_qty(const RuleSet& rules, int board, Qty raw_qty) {
  if (raw_qty <= 0)
    return 0;
  if (board == 2)
    return raw_qty >= rules.star_lot ? raw_qty : 0;  // TODO(verify)
  if (board == 3)
    return raw_qty >= rules.bse_lot ? raw_qty : 0;  // TODO(verify)
  const int64_t lot = rules.main_lot > 0 ? rules.main_lot : 100;
  return (raw_qty / lot) * lot;
}

double limit_pct(const RuleSet& rules, int board, bool is_st, Date date) {
  switch (board) {
    case 0:
      if (is_st) {
        // TODO(verify) ST switch: <= 2026-07-05 5%, >= 2026-07-06 10%.
        return date < rules.st_limit_change_date ? rules.st_limit_pct : rules.st_limit_pct_after;
      }
      return rules.main_limit_pct;
    case 1:
      return rules.gem_limit_pct;  // TODO(verify) GEM ST / new listing
    case 2:
      return rules.star_limit_pct;  // TODO(verify) STAR ST / new listing
    case 3:
      return rules.bse_limit_pct;  // TODO(verify) BSE first-day special case
    default:
      return rules.main_limit_pct;
  }
}

Px round_to_tick(Px raw, const RuleSet& rules) {
  const int64_t tick =
      static_cast<int64_t>(std::llround(rules.min_price_tick * static_cast<double>(kPriceScale)));
  if (tick <= 1)
    return raw;
  if (raw >= 0)
    return ((raw + tick / 2) / tick) * tick;
  return -(((-raw + tick / 2) / tick) * tick);
}

Px limit_up_px(const RuleSet& rules, Px prev_close, int board, bool is_st, Date date) {
  if (prev_close <= 0)
    return 0;
  const double pct = limit_pct(rules, board, is_st, date);
  const Px raw = static_cast<Px>(std::llround(static_cast<double>(prev_close) * (1.0 + pct)));
  return round_to_tick(raw, rules);
}

Px limit_down_px(const RuleSet& rules, Px prev_close, int board, bool is_st, Date date) {
  if (prev_close <= 0)
    return 0;
  const double pct = limit_pct(rules, board, is_st, date);
  Px raw = static_cast<Px>(std::llround(static_cast<double>(prev_close) * (1.0 - pct)));
  if (raw < 0)
    raw = 0;
  return round_to_tick(raw, rules);
}

}  // namespace qc
