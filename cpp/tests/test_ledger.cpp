// Ledger: fixed-point cash/lot bookkeeping, T+1 availability, FIFO realized PnL,
// dividends/splits and the per-step conservation invariant.
#include <catch2/catch_test_macros.hpp>

#include <limits>
#include <stdexcept>

#include "../src/sim/ledger.h"
#include "qcore/types.h"

using namespace qc;

namespace {
constexpr Date kD1 = 20260105;
constexpr Date kD2 = 20260106;
constexpr Date kD3 = 20260107;
}  // namespace

TEST_CASE("ledger buy moves cash and includes fees in cost", "[ledger]") {
  Ledger ledger(to_money(100000.0));
  ledger.add_buy(0, kD2, 1000, to_money(10000.0), to_money(5.0));
  CHECK(ledger.cash() == to_money(89995.0));
  CHECK(ledger.position_qty(0) == 1000);
  CHECK(ledger.position(0).cost == to_money(10005.0));
  CHECK(ledger.fees() == to_money(5.0));
  ledger.mark(0, to_px(10.5));
  CHECK(ledger.market_value() == to_money(10500.0));
  CHECK(ledger.unrealized() == to_money(495.0));
  CHECK(ledger.realized() == 0);
  ledger.assert_invariants(kD2);
}

TEST_CASE("ledger rejects buys beyond cash", "[ledger]") {
  Ledger ledger(to_money(1000.0));
  CHECK_THROWS_AS(ledger.add_buy(0, kD2, 200, to_money(1000.0), to_money(5.0)), std::runtime_error);
  CHECK(ledger.cash() == to_money(1000.0));
  CHECK(ledger.position_qty(0) == 0);
}

TEST_CASE("ledger enforces T+1 and position bounds", "[ledger]") {
  Ledger ledger(to_money(100000.0));
  ledger.add_buy(0, kD2, 1000, to_money(10000.0), 0);
  CHECK(ledger.position(0).sellable(kD2, true) == 0);
  CHECK(ledger.position(0).sellable(kD3, true) == 1000);
  CHECK_THROWS_AS(ledger.add_sell(0, kD2, 100, to_money(1000.0), 0), std::runtime_error);
  CHECK(ledger.add_sell(0, kD3, 400, to_money(4400.0), 0) == to_money(400.0));
  CHECK(ledger.position_qty(0) == 600);
  CHECK(ledger.realized() == to_money(400.0));
  CHECK_THROWS_AS(ledger.add_sell(0, kD3, 1000, to_money(1000.0), 0), std::runtime_error);
  ledger.mark(0, to_px(11.0));
  ledger.assert_invariants(kD3);
}

TEST_CASE("ledger FIFO consumes oldest lots with exact rounding", "[ledger]") {
  Ledger ledger(to_money(1000000.0));
  ledger.add_buy(0, kD1, 100, to_money(1000.0), to_money(1.0));  // cost 1001
  ledger.add_buy(0, kD2, 200, to_money(2400.0), to_money(1.0));  // cost 2401
  CHECK(ledger.position(0).sellable(kD3, true) == 300);
  // 100 sh from lot 1 (cost 1001) + 50 sh from lot 2 (2401*50/200 = 600.25).
  const Money pnl = ledger.add_sell(0, kD3, 150, to_money(1800.0), to_money(2.0));
  CHECK(pnl == to_money(196.75));
  CHECK(ledger.position_qty(0) == 150);
  CHECK(ledger.position(0).cost == to_money(1800.75));
  CHECK(ledger.realized() == to_money(196.75));
  CHECK(ledger.fees() == to_money(4.0));
  ledger.mark(0, to_px(12.0));
  CHECK(ledger.market_value() == to_money(1800.0));
  CHECK(ledger.unrealized() == to_money(-0.75));
  ledger.assert_invariants(kD3);
}

TEST_CASE("ledger split preserves cost and net value", "[ledger]") {
  Ledger ledger(to_money(100000.0));
  ledger.add_buy(0, kD2, 1000, to_money(10000.0), to_money(5.0));
  ledger.mark(0, to_px(10.0));
  const Money before = ledger.equity();
  ledger.apply_split(0, 2.0);
  CHECK(ledger.position_qty(0) == 2000);
  CHECK(ledger.position(0).cost == to_money(10005.0));
  ledger.mark(0, to_px(5.0));
  CHECK(ledger.equity() == before);
  ledger.assert_invariants(kD3);
}

TEST_CASE("ledger dividend credits cash and keeps the conservation identity", "[ledger]") {
  Ledger ledger(to_money(100000.0));
  ledger.add_buy(0, kD2, 1000, to_money(10000.0), to_money(5.0));
  ledger.mark(0, to_px(10.0));
  const Money before = ledger.equity();
  ledger.add_dividend(0, kD3, to_money(500.0));
  CHECK(ledger.dividends() == to_money(500.0));
  CHECK(ledger.equity() == before + to_money(500.0));
  ledger.assert_invariants(kD3);
}

TEST_CASE("ledger marks ignore missing quotes and keep the last valid price", "[ledger]") {
  Ledger ledger(to_money(100000.0));
  ledger.add_buy(0, kD1, 100, to_money(1000.0), 0);
  ledger.mark(0, to_px(10.0));
  ledger.mark(0, 0);   // missing quote
  ledger.mark(0, -1);  // invalid
  CHECK(ledger.market_value() == to_money(1000.0));
  ledger.assert_invariants(kD2);
}

TEST_CASE("ledger can disable T+1 for simulation", "[ledger]") {
  Ledger ledger(to_money(100000.0), /*t_plus_one=*/false);
  ledger.add_buy(0, kD2, 1000, to_money(10000.0), 0);
  CHECK(ledger.position(0).sellable(kD2, false) == 1000);
  CHECK(ledger.add_sell(0, kD2, 1000, to_money(10000.0), 0) == 0);
  CHECK(ledger.position_qty(0) == 0);
  ledger.assert_invariants(kD2);
}

TEST_CASE("notional multiplies fixed-point price by shares", "[ledger]") {
  CHECK(notional(to_px(10.0), 100) == to_money(1000.0));
  CHECK(notional(0, 100) == 0);
  CHECK_THROWS_AS(notional(std::numeric_limits<Px>::max(), std::numeric_limits<Qty>::max()),
                  std::runtime_error);
}
