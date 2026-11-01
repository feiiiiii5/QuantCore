#include "ledger.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace qc {
namespace {

[[noreturn]] void fail(const std::string& msg) {
  throw std::runtime_error("[ledger] " + msg);
}

}  // namespace

Money notional(Px px, Qty qty) {
  const int128 v = static_cast<int128>(px) * static_cast<int128>(qty);
  if (v > static_cast<int128>(std::numeric_limits<Money>::max()) ||
      v < static_cast<int128>(std::numeric_limits<Money>::min())) {
    fail("notional overflow: px=" + std::to_string(px) + " qty=" + std::to_string(qty));
  }
  return static_cast<Money>(v);
}

Qty LedgerPosition::sellable(Date date, bool t_plus_one) const {
  qc::Qty out = 0;
  for (const auto& lot : lots) {
    if (!t_plus_one || lot.buy_date < date)
      out += lot.qty;
  }
  return out;
}

Ledger::Ledger(Money initial_cash, bool t_plus_one, size_t n_sec)
    : initial_cash_(initial_cash), cash_(initial_cash), t_plus_one_(t_plus_one), positions_(n_sec) {
  if (initial_cash < 0)
    fail("initial cash must be >= 0");
}

LedgerPosition& Ledger::ensure(int32_t sec) {
  if (sec < 0)
    fail("negative security index");
  if (static_cast<size_t>(sec) >= positions_.size()) {
    positions_.resize(static_cast<size_t>(sec) + 1);
  }
  return positions_[static_cast<size_t>(sec)];
}

const LedgerPosition* Ledger::find(int32_t sec) const {
  if (sec < 0 || static_cast<size_t>(sec) >= positions_.size())
    return nullptr;
  return &positions_[static_cast<size_t>(sec)];
}

Qty Ledger::position_qty(int32_t sec) const {
  const LedgerPosition* p = find(sec);
  return p == nullptr ? 0 : p->qty;
}

const LedgerPosition& Ledger::position(int32_t sec) const {
  const LedgerPosition* p = find(sec);
  if (p == nullptr)
    fail("position index out of range: " + std::to_string(sec));
  return *p;
}

void Ledger::add_buy(int32_t sec, Date date, Qty qty, Money amount, Money fees) {
  if (qty <= 0)
    fail("buy qty must be positive");
  if (amount < 0 || fees < 0)
    fail("buy amount/fees must be non-negative");
  const Money total = amount + fees;
  if (cash_ < total)
    fail("buy exceeds cash: cash=" + std::to_string(cash_) + " required=" + std::to_string(total));
  LedgerPosition& pos = ensure(sec);
  pos.lots.push_back(LedgerLot{date, qty, total});
  pos.qty += qty;
  pos.cost += total;
  cash_ -= total;
  fees_ += fees;
}

Money Ledger::add_sell(int32_t sec, Date date, Qty qty, Money amount, Money fees) {
  if (qty <= 0)
    fail("sell qty must be positive");
  if (amount < 0 || fees < 0)
    fail("sell amount/fees must be non-negative");
  LedgerPosition& pos = ensure(sec);
  if (qty > pos.qty) {
    fail("sell exceeds position: sec=" + std::to_string(sec) + " qty=" + std::to_string(qty) +
         " held=" + std::to_string(pos.qty));
  }
  const Qty avail = pos.sellable(date, t_plus_one_);
  if (qty > avail) {
    fail("T+1 violation: sec=" + std::to_string(sec) + " date=" + std::to_string(date) +
         " sell=" + std::to_string(qty) + " sellable=" + std::to_string(avail));
  }
  Qty remaining = qty;
  Money removed = 0;
  while (remaining > 0 && !pos.lots.empty()) {
    LedgerLot& lot = pos.lots.front();
    if (lot.qty <= remaining) {
      removed += lot.cost;
      remaining -= lot.qty;
      pos.cost -= lot.cost;
      pos.lots.erase(pos.lots.begin());
    } else {
      const double ratio = static_cast<double>(remaining) / static_cast<double>(lot.qty);
      Money part = static_cast<Money>(std::llround(static_cast<double>(lot.cost) * ratio));
      if (part < 0)
        part = 0;
      if (part > lot.cost)
        part = lot.cost;
      removed += part;
      lot.cost -= part;
      lot.qty -= remaining;
      pos.cost -= part;
      remaining = 0;
    }
  }
  if (remaining != 0)
    fail("FIFO lot accounting inconsistent");
  const Money proceeds = amount - fees;
  const Money pnl = proceeds - removed;
  pos.qty -= qty;
  cash_ += proceeds;
  realized_ += pnl;
  fees_ += fees;
  if (cash_ < 0)
    fail("cash went negative after sell: " + std::to_string(cash_));
  return pnl;
}

void Ledger::add_dividend(int32_t sec, Date /*date*/, Money amount) {
  if (amount < 0)
    fail("dividend must be non-negative");
  if (sec < 0)
    fail("negative security index");
  ensure(sec);
  cash_ += amount;
  dividends_ += amount;
}

void Ledger::apply_split(int32_t sec, double ratio) {
  if (!(ratio > 0.0))
    fail("split ratio must be positive");
  LedgerPosition& pos = ensure(sec);
  if (pos.lots.empty())
    return;
  Qty total_qty = 0;
  Money total_cost = 0;
  for (auto& lot : pos.lots) {
    const Qty new_qty = static_cast<Qty>(std::llround(static_cast<double>(lot.qty) * ratio));
    if (new_qty < 0)
      fail("split produced negative shares");
    // Fractional shares are truncated by rounding; cash-in-lieu is not modeled.
    // TODO(verify) real 送转 fractional-share handling.
    lot.qty = new_qty;
    total_qty += new_qty;
    total_cost += lot.cost;
  }
  pos.qty = total_qty;
  pos.cost = total_cost;
}

void Ledger::mark(int32_t sec, Px px) {
  if (px <= 0)
    return;
  LedgerPosition& pos = ensure(sec);
  pos.last_px = px;
}

Money Ledger::market_value() const {
  int128 sum = 0;
  for (const auto& pos : positions_) {
    if (pos.qty == 0)
      continue;
    sum += static_cast<int128>(pos.qty) * static_cast<int128>(pos.last_px);
  }
  if (sum > static_cast<int128>(std::numeric_limits<Money>::max())) {
    fail("market value overflow");
  }
  return static_cast<Money>(sum);
}

Money Ledger::unrealized() const {
  int128 sum = 0;
  for (const auto& pos : positions_) {
    sum += static_cast<int128>(pos.qty) * static_cast<int128>(pos.last_px);
    sum -= static_cast<int128>(pos.cost);
  }
  if (sum > static_cast<int128>(std::numeric_limits<Money>::max()) ||
      sum < static_cast<int128>(std::numeric_limits<Money>::min())) {
    fail("unrealized overflow");
  }
  return static_cast<Money>(sum);
}

void Ledger::assert_invariants(Date date) const {
  if (cash_ < 0)
    fail("cash < 0: " + std::to_string(cash_));
  if (realized_ < std::numeric_limits<Money>::min() / 2)
    fail("realized overflow");
  for (size_t i = 0; i < positions_.size(); ++i) {
    const LedgerPosition& pos = positions_[i];
    int128 sum_qty = 0;
    int128 sum_cost = 0;
    for (const auto& lot : pos.lots) {
      if (lot.qty < 0)
        fail("negative lot qty at sec " + std::to_string(i));
      if (lot.cost < 0)
        fail("negative lot cost at sec " + std::to_string(i));
      if (lot.buy_date != kInvalidDate && date != kInvalidDate && lot.buy_date > date) {
        fail("lot bought in the future at sec " + std::to_string(i));
      }
      sum_qty += lot.qty;
      sum_cost += lot.cost;
    }
    if (sum_qty != static_cast<int128>(pos.qty)) {
      fail("position qty != sum(lots) at sec " + std::to_string(i));
    }
    if (sum_cost != static_cast<int128>(pos.cost)) {
      fail("position cost != sum(lots) at sec " + std::to_string(i));
    }
    if (pos.last_px < 0)
      fail("negative mark price at sec " + std::to_string(i));
    if (pos.sellable(date, t_plus_one_) > pos.qty) {
      fail("sellable > position at sec " + std::to_string(i));
    }
  }
  const int128 lhs = static_cast<int128>(cash_) + static_cast<int128>(market_value());
  const int128 rhs = static_cast<int128>(initial_cash_) + static_cast<int128>(realized_) +
                     static_cast<int128>(unrealized()) + static_cast<int128>(dividends_);
  if (lhs != rhs) {
    fail("net value conservation failed on " + std::to_string(date) + ": cash+mv=" +
         std::to_string(cash_ + market_value()) + " initial+realized+unrealized+div=" +
         std::to_string(initial_cash_ + realized_ + unrealized() + dividends_));
  }
}

}  // namespace qc
