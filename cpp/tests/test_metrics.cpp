// Metrics: hand-computed return/risk statistics and fee/round-trip aggregation.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <limits>
#include <vector>

#include "../src/sim/ledger.h"
#include "../src/sim/metrics.h"
#include "qcore/types.h"

using namespace qc;
using Catch::Approx;

namespace {

Trade fill(Date date, int32_t sec, Side side, double price, Qty qty, double fee_yuan) {
  Trade t;
  t.date = date;
  t.sec = sec;
  t.side = side;
  t.px = to_px(price);
  t.qty = qty;
  t.amount = notional(t.px, qty);
  t.fee_total = to_money(fee_yuan);
  return t;
}

}  // namespace

TEST_CASE("metrics on a two-step equity curve", "[metrics]") {
  const std::vector<Money> equity = {to_money(110.0), to_money(99.0)};
  const Metrics m = compute_metrics(equity, to_money(100.0), {}, 244);
  CHECK(m.trading_days == 2);
  CHECK(m.total_return == Approx(-0.01));
  CHECK(m.annualized_return == Approx(std::pow(0.99, 122.0) - 1.0));
  // Returns are +10% then -10%: sample std = sqrt(0.02).
  const double stddev = std::sqrt(0.02);
  CHECK(m.volatility == Approx(stddev * std::sqrt(244.0)));
  CHECK(m.sharpe == Approx(0.0).margin(1e-12));
  CHECK(m.sortino == Approx(0.0).margin(1e-12));
  CHECK(m.max_drawdown == Approx(0.1));  // 110 -> 99
  CHECK(m.calmar == Approx(m.annualized_return / 0.1));
  CHECK(m.trade_count == 0);
  CHECK(m.win_rate == 0.0);
  CHECK(m.profit_factor == 0.0);
  CHECK(m.turnover == 0.0);
  CHECK(m.total_fees == 0);
}

TEST_CASE("metrics risk-free rate changes Sharpe only", "[metrics]") {
  const std::vector<Money> equity = {to_money(110.0), to_money(99.0)};
  const double rf = 0.05;
  const Metrics m = compute_metrics(equity, to_money(100.0), {}, 244, rf);
  const double rf_period = rf / 244.0;
  const double expected = (0.0 - rf_period) / std::sqrt(0.02) * std::sqrt(244.0);
  CHECK(m.sharpe == Approx(expected).margin(1e-12));
  CHECK(m.total_return == Approx(-0.01));
}

TEST_CASE("metrics annual_days is configurable", "[metrics]") {
  const std::vector<Money> equity = {to_money(110.0), to_money(99.0)};
  const Metrics m252 = compute_metrics(equity, to_money(100.0), {}, 252);
  const Metrics m244 = compute_metrics(equity, to_money(100.0), {}, 244);
  CHECK(m252.volatility / m244.volatility == Approx(std::sqrt(252.0 / 244.0)));
  CHECK(m252.annualized_return == Approx(std::pow(0.99, 126.0) - 1.0));
}

TEST_CASE("metrics round trips drive win rate, profit factor and turnover", "[metrics]") {
  std::vector<Trade> trades;
  trades.push_back(fill(20260106, 0, Side::Buy, 10.0, 100, 5.0));
  trades.push_back(fill(20260107, 0, Side::Sell, 12.0, 100, 10.0));  // +185
  trades.push_back(fill(20260108, 0, Side::Buy, 10.0, 100, 5.0));
  trades.push_back(fill(20260109, 0, Side::Sell, 9.0, 100, 10.0));  // -115
  const std::vector<Money> equity = {to_money(1000.0)};
  const Metrics m = compute_metrics(equity, to_money(1000.0), trades, 244);
  CHECK(m.trade_count == 4);
  CHECK(m.total_fees == to_money(30.0));
  CHECK(m.win_rate == Approx(0.5));
  CHECK(m.profit_factor == Approx(185.0 / 115.0));
  // (1000 + 1200 + 1000 + 900) / mean_equity(1000).
  CHECK(m.turnover == Approx(4.1));
}

TEST_CASE("metrics profit factor is infinite with no losing round trips", "[metrics]") {
  std::vector<Trade> trades;
  trades.push_back(fill(20260106, 0, Side::Buy, 10.0, 100, 5.0));
  trades.push_back(fill(20260107, 0, Side::Sell, 11.0, 100, 5.0));
  const Metrics m = compute_metrics({to_money(500.0)}, to_money(1000.0), trades, 244);
  CHECK(std::isinf(m.profit_factor));
  CHECK(m.win_rate == Approx(1.0));
}

TEST_CASE("metrics flat equity has no risk", "[metrics]") {
  const std::vector<Money> equity = {to_money(100.0), to_money(100.0), to_money(100.0)};
  const Metrics m = compute_metrics(equity, to_money(100.0), {}, 244);
  CHECK(m.total_return == 0.0);
  CHECK(m.annualized_return == 0.0);
  CHECK(m.volatility == 0.0);
  CHECK(m.sharpe == 0.0);
  CHECK(m.sortino == 0.0);
  CHECK(m.max_drawdown == 0.0);
  CHECK(m.calmar == 0.0);
}

TEST_CASE("metrics handle empty input", "[metrics]") {
  const Metrics m = compute_metrics({}, to_money(100.0), {}, 244);
  CHECK(m.trading_days == 0);
  CHECK(m.total_return == 0.0);
  CHECK(m.annualized_return == 0.0);
  CHECK(m.trade_count == 0);
}

TEST_CASE("metrics total loss saturates at -100% annualized", "[metrics]") {
  const std::vector<Money> equity = {to_money(0.0)};
  const Metrics m = compute_metrics(equity, to_money(100.0), {}, 244);
  CHECK(m.total_return == Approx(-1.0));
  CHECK(m.annualized_return == Approx(-1.0));
}
