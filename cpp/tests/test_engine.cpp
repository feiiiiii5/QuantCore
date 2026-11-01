// Backtest engine golden cases: fixed-point accounting, execution models, constraints,
// cancellation and determinism. Expected numbers are computed by hand in the comments.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <stdexcept>
#include <vector>

#include "fixture.h"
#include "qcore/engine.h"
#include "qcore/types.h"

using namespace qc;
using namespace qc::tests;
using Catch::Approx;

namespace {

BacktestResult run(Panel& panel, BacktestConfig cfg, std::vector<std::vector<double>> weights) {
  MatrixTargetSource source(std::move(weights), panel.n_sec());
  Engine engine(panel, std::move(cfg));
  CancelToken token;
  return engine.run(source, token);
}

std::vector<Date> dates3() { return {20260105, 20260106, 20260107}; }
std::vector<Date> dates4() { return {20260105, 20260106, 20260107, 20260108}; }

}  // namespace

TEST_CASE("engine buys at next open with exact fixed-point accounting", "[engine]") {
  SynthPanel sp(dates3(), {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.5, 9.9, 10.2);
  sp.bar(0, 2, 10.5, 10.8, 10.3, 10.5);
  Panel panel = sp.build();
  auto weights = nan_weights(3, 1);
  weights[0] = {0.5};
  const BacktestResult r = run(panel, base_config(), weights);

  REQUIRE(r.dates == dates3());
  REQUIRE(r.equity.size() == 3);
  // Day 1: cash only. Day 2: buy 50,000 @ 10.00, fees 150+5+6 = 161.
  CHECK(r.equity[0] == to_money(1000000.0));
  CHECK(r.cash[0] == to_money(1000000.0));
  CHECK(r.market_value[0] == 0);
  CHECK(r.cash[1] == to_money(499839.0));
  CHECK(r.market_value[1] == to_money(510000.0));
  CHECK(r.equity[1] == to_money(1009839.0));
  CHECK(r.equity[2] == to_money(1024839.0));

  REQUIRE(r.trades.size() == 1);
  const Trade& t = r.trades[0];
  CHECK(t.date == 20260106);
  CHECK(t.sec == 0);
  CHECK(t.side == Side::Buy);
  CHECK(t.px == to_px(10.0));
  CHECK(t.qty == 50000);
  CHECK(t.amount == to_money(500000.0));
  CHECK(t.commission == to_money(150.0));
  CHECK(t.stamp_duty == 0);
  CHECK(t.transfer_fee == to_money(5.0));
  CHECK(t.other_fee == to_money(6.0));
  CHECK(t.fee_total == to_money(161.0));
  CHECK(t.reason == RejectReason::None);

  CHECK(r.metrics.trade_count == 1);
  CHECK(r.metrics.total_fees == to_money(161.0));
  CHECK(r.metrics.trading_days == 3);
  CHECK(r.metrics.total_return == Approx(0.024839));
  REQUIRE(r.final_position_secs.size() == 1);
  CHECK(r.final_position_secs[0] == 0);
  CHECK(r.final_position_qty[0] == 50000);
}

TEST_CASE("limit-up buy and one-word board are rejected with reason codes", "[engine][rules]") {
  SECTION("limit-up open blocks the buy") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 11.0, 11.0, 11.0, 11.0);  // +10% one-word limit-up
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    const BacktestResult r = run(panel, cfg, weights);
    CHECK(r.equity[1] == to_money(1000000.0));
    REQUIRE(r.trades.size() == 1);  // Full trace records the rejected intent
    CHECK(r.trades[0].qty == 0);
    CHECK(r.trades[0].reason == RejectReason::LimitUp);
    REQUIRE(r.reasons.size() == 1);
    CHECK(r.reasons[0].reason == RejectReason::LimitUp);
    CHECK(r.reasons[0].count == 1);
    CHECK(r.final_position_secs.empty());
  }
  SECTION("one-word flat board cannot be traded") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.0, 10.0, 10.0);  // high == low
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    const BacktestResult r = run(panel, base_config(), weights);
    CHECK(r.equity[1] == to_money(1000000.0));
    REQUIRE(r.reasons.size() == 1);
    CHECK(r.reasons[0].reason == RejectReason::NoQuote);
  }
  SECTION("Summary trace keeps reason counts but no zero-qty trade rows") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 11.0, 11.0, 11.0, 11.0);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.trace = TraceLevel::Summary;
    const BacktestResult r = run(panel, cfg, weights);
    CHECK(r.trades.empty());
    CHECK(r.reasons[0].reason == RejectReason::LimitUp);
  }
}

TEST_CASE("suspended securities cannot be traded", "[engine][rules]") {
  SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  sp.set("suspended", 0, 1, 1.0);
  Panel panel = sp.build();
  auto weights = nan_weights(2, 1);
  weights[0] = {0.5};
  const BacktestResult r = run(panel, base_config(), weights);
  CHECK(r.trades.empty());
  REQUIRE(r.reasons.size() == 1);
  CHECK(r.reasons[0].reason == RejectReason::Suspended);
}

TEST_CASE("execution models pick the right next-day price", "[engine][exec]") {
  SECTION("next_close") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.8, 9.9, 10.5);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.type = ExecType::NextClose;
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].px == to_px(10.5));
    CHECK(r.trades[0].qty == 47600);  // 500000 / 10.5 -> 100-share lots
  }
  SECTION("next_vwap uses amount / volume") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.8, 9.9, 10.5);
    sp.set("amount", 0, 1, 10400000.0);  // 10.4 CNY * 1e6 shares
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.type = ExecType::NextVwap;
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].px == to_px(10.4));
    CHECK(r.trades[0].qty == 48000);
  }
  SECTION("after-hours fixed price on STAR before the extension date") {
    SynthPanel sp({20260105, 20260106}, {synth_security("688001", 2)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.8, 9.9, 10.5);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.type = ExecType::AfterHoursFixed;
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].px == to_px(10.5));
    CHECK(r.trades[0].qty == 47619);  // STAR: >= 200 then 1-share increments
  }
  SECTION("after-hours is unavailable on MAIN before 2026-07-06") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.8, 9.9, 10.5);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.type = ExecType::AfterHoursFixed;
    const BacktestResult r = run(panel, cfg, weights);
    CHECK(r.trades.empty());
    REQUIRE(r.reasons.size() == 1);
    CHECK(r.reasons[0].reason == RejectReason::NoQuote);
  }
}

TEST_CASE("cash constraint reduces or rejects buys", "[engine]") {
  SECTION("partially affordable buy shrinks to a legal lot") {
    // 10,000 CNY cash, 100% target at 10 CNY -> 1,000 shares unaffordable with fees;
    // largest affordable 100-share multiple is 900 shares.
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {1.0};
    BacktestConfig cfg = base_config();
    cfg.initial_cash = to_money(10000.0);
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].qty == 900);
    CHECK(r.trades[0].amount == to_money(9000.0));
    CHECK(r.cash[1] == to_money(10000.0) - to_money(9000.0) - r.trades[0].fee_total);
    CHECK(r.cash[1] >= 0);
  }
  SECTION("unaffordable legal order is rejected") {
    // 10,000 CNY cash, 100% target at 100 CNY -> a 100-share lot costs > cash.
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 100.0, 100.5, 99.5, 100.0);
    sp.bar(0, 1, 100.0, 100.5, 99.5, 100.0);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {1.0};
    BacktestConfig cfg = base_config();
    cfg.initial_cash = to_money(10000.0);
    const BacktestResult r = run(panel, cfg, weights);
    CHECK(r.trades.size() == 1);
    CHECK(r.trades[0].qty == 0);
    CHECK(r.trades[0].reason == RejectReason::InsufficientCash);
    REQUIRE(r.reasons.size() == 1);
    CHECK(r.reasons[0].reason == RejectReason::InsufficientCash);
  }
}

TEST_CASE("participation limit caps the filled quantity", "[engine][exec]") {
  SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0, 1000.0);  // next-day volume = 1,000 shares
  Panel panel = sp.build();
  auto weights = nan_weights(2, 1);
  weights[0] = {0.5};
  BacktestConfig cfg = base_config();
  cfg.exec.max_participation = 0.1;  // cap = 100 shares
  const BacktestResult r = run(panel, cfg, weights);
  REQUIRE(r.trades.size() == 1);
  CHECK(r.trades[0].qty == 100);
  CHECK(r.trades[0].amount == to_money(1000.0));
}

TEST_CASE("minimum rebalance threshold skips tiny trades", "[engine]") {
  SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  Panel panel = sp.build();
  auto weights = nan_weights(2, 1);
  weights[0] = {0.001};  // 1,000 CNY target
  BacktestConfig cfg = base_config();
  cfg.exec.min_rebalance_value = to_money(100000.0);
  const BacktestResult r = run(panel, cfg, weights);
  CHECK(r.trades.size() == 1);
  CHECK(r.trades[0].qty == 0);
  CHECK(r.trades[0].reason == RejectReason::MinRebalance);
  CHECK(r.final_position_secs.empty());
}

TEST_CASE("slippage is adverse and clamped inside the bar", "[engine][exec]") {
  SECTION("10bps above the open") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.2, 9.9, 10.1);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.slippage_bps = 10.0;
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].px == to_px(10.01));
  }
  SECTION("slippage beyond the high clamps to the high") {
    SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.2, 9.9, 10.1);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    cfg.exec.slippage_bps = 500.0;  // 10.00 * 1.05 = 10.50 > high 10.20
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].px == to_px(10.2));
  }
}

TEST_CASE("NaN weights hold positions, zero weights exit, T+1 permits next-day sells",
          "[engine][t1]") {
  SynthPanel sp(dates4(), {synth_security("600000", 0)});
  for (size_t t = 0; t < 4; ++t) sp.bar(0, t, 10.0, 10.2, 9.8, 10.0);
  Panel panel = sp.build();
  auto weights = nan_weights(4, 1);
  weights[0] = {0.5};  // buy on day 2
  weights[1] = {kNaN};  // no instruction on day 2
  weights[2] = {0.0};  // exit on day 4
  const BacktestResult r = run(panel, base_config(), weights);
  REQUIRE(r.trades.size() == 2);
  CHECK(r.trades[0].side == Side::Buy);
  CHECK(r.trades[0].qty == 50000);
  CHECK(r.trades[1].side == Side::Sell);
  CHECK(r.trades[1].date == 20260108);
  CHECK(r.trades[1].qty == 50000);
  CHECK(r.final_position_secs.empty());
  // Sell fees: commission 150 + stamp 250 + transfer 5 + other 6 = 411 CNY.
  CHECK(r.trades[1].fee_total == to_money(411.0));
  CHECK(r.cash[3] == to_money(1000000.0) - to_money(161.0) - to_money(411.0));
}

TEST_CASE("cancellation returns a partial result with a Canceled reason", "[engine][cancel]") {
  SynthPanel sp(dates3(), {synth_security("600000", 0)});
  for (size_t t = 0; t < 3; ++t) sp.bar(0, t, 10.0, 10.2, 9.8, 10.0);
  Panel panel = sp.build();
  auto weights = nan_weights(3, 1);
  weights[0] = {0.5};
  MatrixTargetSource source(std::move(weights), panel.n_sec());
  BacktestConfig cfg = base_config();
  Engine engine(panel, std::move(cfg));
  CancelToken token;
  token.cancel();
  const BacktestResult r = engine.run(source, token);
  CHECK(r.dates.empty());
  CHECK(r.equity.empty());
  REQUIRE(r.reasons.size() == 1);
  CHECK(r.reasons[0].reason == RejectReason::Canceled);
  CHECK(r.reasons[0].count == 1);
  CHECK(r.metrics.trade_count == 0);
}

TEST_CASE("engine edge cases: no signals and single-day panel", "[engine][edge]") {
  SECTION("all-NaN weight matrix never rebalances") {
    SynthPanel sp(dates3(), {synth_security("600000", 0)});
    for (size_t t = 0; t < 3; ++t) sp.bar(0, t, 10.0, 10.2, 9.8, 10.0);
    Panel panel = sp.build();
    const BacktestResult r = run(panel, base_config(), nan_weights(3, 1));
    CHECK(r.trades.empty());
    CHECK(r.equity[0] == to_money(1000000.0));
    CHECK(r.equity[2] == to_money(1000000.0));
    CHECK(r.metrics.total_return == 0.0);
  }
  SECTION("empty target source rows are ignored") {
    SynthPanel sp(dates3(), {synth_security("600000", 0)});
    for (size_t t = 0; t < 3; ++t) sp.bar(0, t, 10.0, 10.2, 9.8, 10.0);
    Panel panel = sp.build();
    const BacktestResult r = run(panel, base_config(), {});
    CHECK(r.trades.empty());
    CHECK(r.equity.size() == 3);
  }
  SECTION("single-day panel has no next day to execute on") {
    SynthPanel sp({20260105}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    Panel panel = sp.build();
    auto weights = nan_weights(1, 1);
    weights[0] = {0.5};
    const BacktestResult r = run(panel, base_config(), weights);
    CHECK(r.trades.empty());
    CHECK(r.equity.size() == 1);
    CHECK(r.equity[0] == to_money(1000000.0));
  }
}

TEST_CASE("engine validates config and panel fields", "[engine][errors]") {
  SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  Panel panel = sp.build();
  auto weights = nan_weights(2, 1);
  SECTION("negative initial cash") {
    BacktestConfig cfg = base_config();
    cfg.initial_cash = -1;
    CHECK_THROWS_AS(Engine(panel, cfg), std::invalid_argument);
  }
  SECTION("zero participation") {
    BacktestConfig cfg = base_config();
    cfg.exec.max_participation = 0.0;
    CHECK_THROWS_AS(Engine(panel, cfg), std::invalid_argument);
  }
  SECTION("missing open field for next_open") {
    SynthPanel no_open({20260105, 20260106}, {synth_security("600000", 0)});
    for (size_t t = 0; t < 2; ++t) {
      no_open.set("close", 0, t, 10.0);
      no_open.set("high", 0, t, 10.2);
      no_open.set("low", 0, t, 9.8);
    }
    Panel no_open_panel = no_open.build();
    auto no_open_weights = nan_weights(2, 1);
    no_open_weights[0] = {0.5};
    MatrixTargetSource source(std::move(no_open_weights), no_open_panel.n_sec());
    BacktestConfig cfg = base_config();
    Engine engine(no_open_panel, cfg);
    CancelToken token;
    CHECK_THROWS_AS(engine.run(source, token), std::invalid_argument);
  }
}

TEST_CASE("engine is deterministic across runs", "[engine][determinism]") {
  SynthPanel sp(dates4(), {synth_security("600000", 0), synth_security("000001", 0)});
  for (size_t t = 0; t < 4; ++t) {
    sp.bar(0, t, 10.0 + 0.1 * static_cast<double>(t), 10.4, 9.9, 10.2);
    sp.bar(1, t, 20.0, 20.4 - 0.1 * static_cast<double>(t), 19.6, 20.1);
  }
  Panel panel = sp.build();
  auto weights = nan_weights(4, 2);
  weights[0] = {0.4, 0.3};
  weights[2] = {0.0, 0.5};
  const BacktestResult a = run(panel, base_config(), weights);
  const BacktestResult b = run(panel, base_config(), weights);
  CHECK(a.dates == b.dates);
  CHECK(a.equity == b.equity);
  CHECK(a.cash == b.cash);
  CHECK(a.market_value == b.market_value);
  REQUIRE(a.trades.size() == b.trades.size());
  for (size_t i = 0; i < a.trades.size(); ++i) {
    CHECK(a.trades[i].date == b.trades[i].date);
    CHECK(a.trades[i].sec == b.trades[i].sec);
    CHECK(a.trades[i].side == b.trades[i].side);
    CHECK(a.trades[i].px == b.trades[i].px);
    CHECK(a.trades[i].qty == b.trades[i].qty);
    CHECK(a.trades[i].amount == b.trades[i].amount);
    CHECK(a.trades[i].fee_total == b.trades[i].fee_total);
    CHECK(a.trades[i].reason == b.trades[i].reason);
  }
  CHECK(a.metrics.total_return == b.metrics.total_return);
  CHECK(a.metrics.sharpe == b.metrics.sharpe);
  CHECK(a.metrics.total_fees == b.metrics.total_fees);
  REQUIRE(a.reasons.size() == b.reasons.size());
  for (size_t i = 0; i < a.reasons.size(); ++i) {
    CHECK(a.reasons[i].reason == b.reasons[i].reason);
    CHECK(a.reasons[i].count == b.reasons[i].count);
  }
  CHECK(a.final_position_secs == b.final_position_secs);
  CHECK(a.final_position_qty == b.final_position_qty);
}
