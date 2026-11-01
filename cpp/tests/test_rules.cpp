// Rules and costs: board limits, lot sizes, tick rounding, fee recomputation and the
// execution-price primitives (slippage, clamping, after-hours availability).
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>

#include "../src/sim/costs.h"
#include "../src/sim/execution.h"
#include "../src/sim/rules.h"
#include "qcore/types.h"

using namespace qc;
using Catch::Approx;

namespace {
constexpr int kMain = 0;
constexpr int kGem = 1;
constexpr int kStar = 2;
constexpr int kBse = 3;

SecurityCtx ctx(int board, bool shanghai) {
  SecurityCtx c;
  c.board = board;
  c.is_shanghai = shanghai;
  return c;
}
}  // namespace

TEST_CASE("limit percentages by board and ST switch date", "[rules]") {
  RuleSet rules;
  CHECK(limit_pct(rules, kMain, false, 20260703) == Approx(0.10));
  // TODO(verify) flag: ST 5% -> 10% switch on 2026-07-06.
  CHECK(limit_pct(rules, kMain, true, 20260703) == Approx(0.05));
  CHECK(limit_pct(rules, kMain, true, 20260706) == Approx(0.10));
  CHECK(limit_pct(rules, kGem, false, 20260703) == Approx(0.20));
  CHECK(limit_pct(rules, kStar, false, 20260703) == Approx(0.20));
  CHECK(limit_pct(rules, kBse, false, 20260703) == Approx(0.30));
}

TEST_CASE("price limits round to the 0.01 tick", "[rules]") {
  RuleSet rules;
  CHECK(limit_up_px(rules, to_px(10.00), kMain, false, 20260105) == to_px(11.00));
  CHECK(limit_down_px(rules, to_px(10.00), kMain, false, 20260105) == to_px(9.00));
  CHECK(limit_up_px(rules, to_px(10.00), kMain, true, 20260703) == to_px(10.50));
  CHECK(limit_up_px(rules, to_px(10.00), kMain, true, 20260706) == to_px(11.00));
  CHECK(limit_up_px(rules, to_px(10.00), kGem, false, 20260105) == to_px(12.00));
  CHECK(limit_up_px(rules, to_px(10.00), kBse, false, 20260105) == to_px(13.00));
  // 3.33 * 1.1 = 3.663 -> 3.66; 3.33 * 0.9 = 2.997 -> 3.00 (round half up to cent).
  CHECK(limit_up_px(rules, to_px(3.33), kMain, false, 20260105) == to_px(3.66));
  CHECK(limit_down_px(rules, to_px(3.33), kMain, false, 20260105) == to_px(3.00));
  CHECK(limit_up_px(rules, 0, kMain, false, 20260105) == 0);
  CHECK(round_to_tick(to_px(10.005), rules) == to_px(10.01));
  CHECK(round_to_tick(to_px(10.004), rules) == to_px(10.00));
}

TEST_CASE("buy lot canonicalization by board", "[rules]") {
  RuleSet rules;
  CHECK(canon_buy_qty(rules, kMain, 50) == 0);
  CHECK(canon_buy_qty(rules, kMain, 150) == 100);
  CHECK(canon_buy_qty(rules, kMain, 199) == 100);
  CHECK(canon_buy_qty(rules, kMain, 200) == 200);
  CHECK(canon_buy_qty(rules, kGem, 99) == 0);
  CHECK(canon_buy_qty(rules, kStar, 199) == 0);
  CHECK(canon_buy_qty(rules, kStar, 200) == 200);
  CHECK(canon_buy_qty(rules, kStar, 250) == 250);
  CHECK(canon_buy_qty(rules, kBse, 99) == 0);
  CHECK(canon_buy_qty(rules, kBse, 100) == 100);
  CHECK(canon_buy_qty(rules, kBse, 101) == 101);
  CHECK(canon_buy_qty(rules, kMain, -5) == 0);
}

TEST_CASE("fees are recomputable per component", "[rules][costs]") {
  CostModel model;
  const Money amount = to_money(500000.0);
  const CostBreakdown buy = compute_costs(model, Side::Buy, amount, ctx(kMain, true));
  CHECK(buy.commission == to_money(150.0));  // 500000 * 0.0003
  CHECK(buy.stamp_duty == 0);
  CHECK(buy.transfer_fee == to_money(5.0));  // 500000 * 0.00001
  CHECK(buy.other_fee == to_money(6.0));     // 5 + 1 (exchange + reg)
  CHECK(buy.total == to_money(161.0));

  const CostBreakdown sell = compute_costs(model, Side::Sell, amount, ctx(kMain, true));
  CHECK(sell.stamp_duty == to_money(250.0));  // sell only
  CHECK(sell.total == to_money(411.0));

  // 5 CNY minimum commission: 1000 * 0.0003 = 0.3 -> 5; transfer 0.01, exchange 0.01,
  // reg 0.002 (dedicated 1e-4 rounding per component).
  const CostBreakdown small = compute_costs(model, Side::Buy, to_money(1000.0), ctx(kMain, true));
  CHECK(small.commission == to_money(5.0));
  CHECK(small.total == to_money(5.022));

  // Shenzhen has no transfer fee by default; the flag can force it on.
  const CostBreakdown sz = compute_costs(model, Side::Buy, amount, ctx(kMain, false));
  CHECK(sz.transfer_fee == 0);
  CHECK(sz.total == to_money(156.0));
  CostModel all_markets = model;
  all_markets.transfer_fee_shanghai_only = false;
  const CostBreakdown sz2 = compute_costs(all_markets, Side::Buy, amount, ctx(kMain, false));
  CHECK(sz2.transfer_fee == to_money(5.0));
}

TEST_CASE("execution reference prices by model", "[rules][exec]") {
  CHECK(exec_reference_price(ExecType::NextOpen, to_px(9.5), to_px(10.0), to_px(9.0), to_px(9.8),
                             1e6, 9.9e6) == to_px(9.5));
  CHECK(exec_reference_price(ExecType::NextClose, to_px(9.5), to_px(10.0), to_px(9.0), to_px(9.8),
                             1e6, 9.9e6) == to_px(9.8));
  CHECK(exec_reference_price(ExecType::AfterHoursFixed, to_px(9.5), to_px(10.0), to_px(9.0),
                             to_px(9.8), 1e6, 9.9e6) == to_px(9.8));
  CHECK(exec_reference_price(ExecType::NextVwap, to_px(9.5), to_px(10.0), to_px(9.0), to_px(9.8),
                             1000000.0, 10400000.0) == to_px(10.4));
  CHECK(exec_reference_price(ExecType::NextVwap, to_px(9.5), to_px(10.0), to_px(9.0), to_px(9.8),
                             0.0, 10400000.0) == 0);
  CHECK(exec_reference_price(ExecType::NextOpen, 0, to_px(10.0), to_px(9.0), to_px(9.8), 1e6,
                             9.9e6) == 0);
}

TEST_CASE("after-hours availability follows board and extension date", "[rules][exec]") {
  RuleSet rules;
  CHECK(after_hours_available(rules, kStar, 20260105));
  CHECK_FALSE(after_hours_available(rules, kMain, 20260105));
  CHECK(after_hours_available(rules, kMain, 20260706));
  CHECK(after_hours_available(rules, kGem, 20260706));
  rules.after_hours = false;
  CHECK_FALSE(after_hours_available(rules, kStar, 20260105));
}

TEST_CASE("slippage is adverse and tick rounded, fills clamp into the bar", "[rules][exec]") {
  RuleSet rules;
  CHECK(apply_slippage(to_px(10.0), Side::Buy, 10.0, rules) == to_px(10.01));
  CHECK(apply_slippage(to_px(10.0), Side::Sell, 10.0, rules) == to_px(9.99));
  CHECK(apply_slippage(to_px(10.0), Side::Buy, 0.0, rules) == to_px(10.0));
  CHECK(clamp_fill_price(to_px(10.5), to_px(9.8), to_px(10.2), 0, 0) == to_px(10.2));
  CHECK(clamp_fill_price(to_px(9.0), to_px(9.8), to_px(10.2), 0, 0) == to_px(9.8));
  CHECK(clamp_fill_price(to_px(10.6), to_px(10.0), to_px(11.0), to_px(10.5), to_px(9.5)) ==
        to_px(10.5));
  CHECK(clamp_fill_price(to_px(9.0), to_px(9.5), to_px(11.0), to_px(10.5), to_px(9.5)) ==
        to_px(9.5));
}
