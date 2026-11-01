#pragma once
// Long-only fixed-point ledger: cash, FIFO lots with T+1 availability, realized and
// unrealized PnL, dividends, splits. Every mutation is exact integer bookkeeping so the
// conservation invariant can be asserted bit-exactly after each step.
// Semantics: docs/engine-semantics.md §3.
#include <cstddef>
#include <cstdint>
#include <vector>

#include "qcore/types.h"

namespace qc {

struct LedgerLot {
  Date buy_date = kInvalidDate;
  Qty qty = 0;
  Money cost = 0;  // total cost of the remaining shares, inclusive of buy fees
};

struct LedgerPosition {
  Qty qty = 0;
  Money cost = 0;  // sum of lot cost
  Px last_px = 0;  // last valid mark price (0 when never quoted)
  std::vector<LedgerLot> lots;
  // Shares bought strictly before `date` (or all shares when T+1 is disabled).
  Qty sellable(Date date, bool t_plus_one) const;
};

// Px * Qty -> Money (1e-4 CNY * shares = 1e-4 CNY notional). Throws on overflow.
Money notional(Px px, Qty qty);

class Ledger {
 public:
  explicit Ledger(Money initial_cash, bool t_plus_one = true, size_t n_sec = 0);

  Money initial_cash() const {
    return initial_cash_;
  }
  Money cash() const {
    return cash_;
  }
  Money realized() const {
    return realized_;
  }
  Money dividends() const {
    return dividends_;
  }
  Money fees() const {
    return fees_;
  }
  Money market_value() const;
  Money equity() const {
    return cash_ + market_value();
  }
  Money unrealized() const;

  // Applies a buy fill; `amount + fees` leaves cash. Lot cost includes fees.
  void add_buy(int32_t sec, Date date, Qty qty, Money amount, Money fees);
  // Applies a sell fill FIFO; returns realized PnL of this fill. Throws when the sell
  // exceeds the position or the T+1-available quantity (never silently ignores).
  Money add_sell(int32_t sec, Date date, Qty qty, Money amount, Money fees);
  void add_dividend(int32_t sec, Date date, Money amount);
  // Share-count multiply (送转). Cost basis is preserved; fractional shares round
  // half away from zero (TODO(verify) real cash-in-lieu handling).
  void apply_split(int32_t sec, double ratio);
  // Updates the mark price; non-positive/NaN marks are ignored.
  void mark(int32_t sec, Px px);

  Qty position_qty(int32_t sec) const;
  const LedgerPosition& position(int32_t sec) const;
  const std::vector<LedgerPosition>& positions() const {
    return positions_;
  }
  size_t position_count() const {
    return positions_.size();
  }

  // Throws std::runtime_error listing the failed invariant:
  //  - cash >= 0, qty/cost/lots consistency, mark prices non-negative
  //  - sellable(qty) <= qty, lots bought on/before `date`
  //  - cash + market_value == initial + realized + unrealized + dividends
  void assert_invariants(Date date) const;

 private:
  LedgerPosition& ensure(int32_t sec);
  const LedgerPosition* find(int32_t sec) const;

  Money initial_cash_ = 0;
  Money cash_ = 0;
  Money realized_ = 0;
  Money dividends_ = 0;
  Money fees_ = 0;
  bool t_plus_one_ = true;
  std::vector<LedgerPosition> positions_;
};

}  // namespace qc
