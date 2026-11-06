// Corporate actions, ST limit switch and delisting/forced liquidation cases.
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <limits>
#include <vector>

#include "fixture.h"
#include "qcore/engine.h"
#include "qcore/types.h"

using namespace qc;
using namespace qc::tests;

namespace {

BacktestResult run(Panel& panel, BacktestConfig cfg, std::vector<std::vector<double>> weights) {
  MatrixTargetSource source(std::move(weights), panel.n_sec());
  Engine engine(panel, std::move(cfg));
  CancelToken token;
  return engine.run(source, token);
}

}  // namespace

TEST_CASE("corporate actions reject non-finite cash and splits", "[engine][corporate]") {
  SynthPanel sp({20260105, 20260106}, {synth_security("600000", 0)});
  Panel panel = sp.build();
  for (double invalid_value :
       {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()}) {
    BacktestConfig cfg = base_config();
    CorporateAction action;
    action.sec = 0;
    action.ex_date = 20260106;
    action.cash_per_share = invalid_value;
    cfg.corporate_actions = {action};
    REQUIRE_THROWS_AS(Engine(panel, cfg), std::invalid_argument);
    action.cash_per_share = 0;
    action.split_ratio = invalid_value;
    cfg.corporate_actions = {action};
    REQUIRE_THROWS_AS(Engine(panel, cfg), std::invalid_argument);
  }
}

TEST_CASE("corporate actions are applied on the ex-date", "[engine][corporate]") {
  SECTION("2-for-1 split doubles shares and preserves net value") {
    SynthPanel sp({20260105, 20260106, 20260107}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);  // buy 50,000 @ 10.00, fees 161
    sp.bar(0, 2, 5.0, 5.2, 4.9, 5.0);     // ex-rights price
    Panel panel = sp.build();
    auto weights = nan_weights(3, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    CorporateAction ca;
    ca.ex_date = 20260107;
    ca.sec = 0;
    ca.split_ratio = 2.0;
    cfg.corporate_actions.push_back(ca);
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.trades.size() == 1);
    REQUIRE(r.final_position_secs.size() == 1);
    CHECK(r.final_position_qty[0] == 100000);
    CHECK(r.equity[1] == to_money(999839.0));
    CHECK(r.equity[2] == to_money(999839.0));  // 100,000 * 5.00 + cash
    CHECK(r.cash[2] == r.cash[1]);
  }
  SECTION("cash dividend credits cash on the ex-date") {
    SynthPanel sp({20260105, 20260106, 20260107}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 2, 9.5, 9.6, 9.4, 9.5);  // ex-dividend reference price
    Panel panel = sp.build();
    auto weights = nan_weights(3, 1);
    weights[0] = {0.5};
    BacktestConfig cfg = base_config();
    CorporateAction ca;
    ca.ex_date = 20260107;
    ca.sec = 0;
    ca.cash_per_share = 0.5;  // 50,000 shares * 0.5 = 25,000 CNY
    cfg.corporate_actions.push_back(ca);
    const BacktestResult r = run(panel, cfg, weights);
    REQUIRE(r.final_position_qty.size() == 1);
    CHECK(r.final_position_qty[0] == 50000);
    CHECK(r.cash[1] == to_money(499839.0));
    CHECK(r.cash[2] == to_money(524839.0));
    CHECK(r.equity[2] == to_money(999839.0));  // 524,839 + 50,000 * 9.50
  }
}

TEST_CASE("ST price limit switches from 5% to 10% on 2026-07-06", "[engine][rules][st]") {
  SECTION("pre-switch ST limit-up blocks the buy") {
    SynthPanel sp({20260702, 20260703}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.5, 10.6, 10.4, 10.5);  // +5% == ST limit-up before the switch
    sp.flag_all("st", 0, 1.0);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    const BacktestResult r = run(panel, base_config(), weights);
    CHECK(r.trades.size() == 1);
    CHECK(r.trades[0].qty == 0);
    CHECK(r.trades[0].reason == RejectReason::LimitUp);
  }
  SECTION("post-switch ST limit is 10%, so +5% is tradable") {
    SynthPanel sp({20260703, 20260706}, {synth_security("600000", 0)});
    sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
    sp.bar(0, 1, 10.5, 10.6, 10.4, 10.55);  // +5% < 10% ST limit after the switch
    sp.flag_all("st", 0, 1.0);
    Panel panel = sp.build();
    auto weights = nan_weights(2, 1);
    weights[0] = {0.5};
    const BacktestResult r = run(panel, base_config(), weights);
    REQUIRE(r.trades.size() == 1);
    CHECK(r.trades[0].reason == RejectReason::None);
    CHECK(r.trades[0].px == to_px(10.5));
    CHECK(r.trades[0].qty == 47600);  // 500,000 / 10.50 -> 100-share lots
  }
}

TEST_CASE("split-adjusted closed fills use the ledger cost basis", "[engine][corporate][metrics]") {
  bool delisted = false;
  SECTION("target exits the remaining shares") {}
  SECTION("delisting liquidates the remaining shares") {
    delisted = true;
  }
  SynthPanel sp({20260105, 20260106, 20260107, 20260108},
                {synth_security("600000", 0, 20000101, delisted ? 20260108 : 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 2, 5.2, 5.4, 5.0, 5.2);
  sp.bar(0, 3, 5.2, 5.4, 5.0, 5.2);
  Panel panel = sp.build();
  auto weights = nan_weights(4, 1);
  weights[0] = {0.1};    // buy 100 @ 10
  weights[1] = {0.052};  // after 2:1 split, sell 100 @ 5.2
  weights[2] = {0.0};    // sell the remaining 100 @ 5.2
  BacktestConfig cfg = base_config();
  cfg.initial_cash = to_money(10000.0);
  cfg.costs.commission_rate = 0;
  cfg.costs.min_commission = 0;
  cfg.costs.stamp_duty_rate = 0;
  cfg.costs.transfer_fee_rate = 0;
  cfg.costs.exchange_fee_rate = 0;
  cfg.costs.reg_fee_rate = 0;
  CorporateAction ca;
  ca.sec = 0;
  ca.ex_date = 20260107;
  ca.split_ratio = 2.0;
  cfg.corporate_actions.push_back(ca);
  const BacktestResult result = run(panel, cfg, weights);
  std::vector<Money> pnls;
  for (const Trade& trade : result.trades) {
    if (trade.side == Side::Sell && trade.qty > 0) {
      REQUIRE(trade.realized_pnl.has_value());
      pnls.push_back(*trade.realized_pnl);
    }
  }
  REQUIRE((pnls == std::vector<Money>{to_money(20.0), to_money(20.0)}));
  CHECK(result.equity.back() == to_money(10040.0));
  CHECK(result.metrics.win_rate == 1.0);
  CHECK(std::isinf(result.metrics.profit_factor));
}

TEST_CASE("delisted positions are force-liquidated at the last mark", "[engine][delist]") {
  SynthPanel sp({20260105, 20260106, 20260107}, {synth_security("600000", 0, 20200101, 20260107)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);  // buy 50,000 @ 10.00 on day 2
  // day 3: no quotes at all (delisted); the engine clears at the last mark (10.00).
  Panel panel = sp.build();
  auto weights = nan_weights(3, 1);
  weights[0] = {0.5};
  const BacktestResult r = run(panel, base_config(), weights);
  REQUIRE(r.trades.size() == 2);
  CHECK(r.trades[0].side == Side::Buy);
  CHECK(r.trades[1].side == Side::Sell);
  CHECK(r.trades[1].date == 20260107);
  CHECK(r.trades[1].px == to_px(10.0));
  CHECK(r.trades[1].qty == 50000);
  CHECK(r.trades[1].fee_total == to_money(411.0));  // 150 + 250 + 5 + 6
  CHECK(r.final_position_secs.empty());
  CHECK(r.equity[2] == to_money(999428.0));  // 1,000,000 - 161 - 411
}

TEST_CASE("suspension keeps the last valid mark for valuation", "[engine][corporate]") {
  SynthPanel sp({20260105, 20260106, 20260107}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);  // buy 50,000 @ 10.00 on day 2
  sp.set("suspended", 0, 2, 1.0);       // day 3 suspended, no quotes
  Panel panel = sp.build();
  auto weights = nan_weights(3, 1);
  weights[0] = {0.5};
  weights[1] = {0.5};  // day-3 sell attempt is rejected as suspended
  const BacktestResult r = run(panel, base_config(), weights);
  REQUIRE(r.trades.size() == 2);  // one fill + one Full-trace rejection
  CHECK(r.trades[0].side == Side::Buy);
  CHECK(r.trades[1].qty == 0);
  CHECK(r.trades[1].reason == RejectReason::Suspended);
  REQUIRE(r.final_position_qty.size() == 1);
  CHECK(r.final_position_qty[0] == 50000);
  // No day-3 mark: valuation keeps the last valid close of 10.00.
  CHECK(r.equity[2] == to_money(999839.0));
}

TEST_CASE("a suspended ex-date rebases the last mark", "[engine][corporate]") {
  double cash = 0.0;
  double split = 2.0;
  SECTION("split") {}
  SECTION("cash dividend") {
    cash = 0.5;
    split = 1.0;
  }
  SECTION("cash and split") {
    cash = 0.5;
  }
  SynthPanel sp({20260105, 20260106, 20260107}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  sp.set("suspended", 0, 2, 1.0);
  Panel panel = sp.build();
  auto weights = nan_weights(3, 1);
  weights[0] = {0.5};
  BacktestConfig cfg = base_config();
  CorporateAction ca;
  ca.sec = 0;
  ca.ex_date = 20260107;
  ca.cash_per_share = cash;
  ca.split_ratio = split;
  cfg.corporate_actions.push_back(ca);
  const BacktestResult result = run(panel, cfg, weights);
  CHECK(result.equity[2] == result.equity[1]);
  CHECK(result.final_position_qty[0] == static_cast<Qty>(50000 * split));
}

TEST_CASE("consecutive suspended ex-dates compound reference adjustments", "[engine][corporate]") {
  SynthPanel sp({20260105, 20260106, 20260107, 20260108}, {synth_security("600000", 0)});
  sp.bar(0, 0, 10.0, 10.2, 9.8, 10.0);
  sp.bar(0, 1, 10.0, 10.2, 9.8, 10.0);
  sp.set("suspended", 0, 2, 1.0);
  sp.set("suspended", 0, 3, 1.0);
  Panel panel = sp.build();
  auto weights = nan_weights(4, 1);
  weights[0] = {0.5};
  BacktestConfig cfg = base_config();
  CorporateAction ca;
  ca.sec = 0;
  ca.ex_date = 20260107;
  ca.split_ratio = 2.0;
  cfg.corporate_actions.push_back(ca);
  ca.ex_date = 20260108;
  cfg.corporate_actions.push_back(ca);
  const BacktestResult result = run(panel, cfg, weights);
  CHECK(result.equity[2] == result.equity[1]);
  CHECK(result.equity[3] == result.equity[1]);
  CHECK(result.final_position_qty[0] == 200000);
}

TEST_CASE("finite suspended closes cannot overwrite carried marks", "[engine][corporate]") {
  bool split = true;
  SECTION("split adjustment survives the ex-date and following suspended day") {}
  SECTION("suspension without a corporate action preserves the last mark") {
    split = false;
  }
  SynthPanel sp({20260105, 20260106, 20260107, 20260108, 20260109}, {synth_security("600000", 0)});
  sp.bar_all(0, 10.0, 10.2, 9.8, 10.0);
  sp.set("suspended", 0, 2, 1.0);
  sp.set("suspended", 0, 3, 1.0);
  sp.set("volume", 0, 2, 0.0);
  sp.set("volume", 0, 3, 0.0);
  const double resumed = split ? 6.0 : 11.0;
  sp.bar(0, 4, resumed, resumed + 0.2, resumed - 0.2, resumed);
  Panel panel = sp.build();
  auto weights = nan_weights(5, 1);
  weights[0] = {0.5};
  BacktestConfig cfg = base_config();
  if (split) {
    CorporateAction ca;
    ca.sec = 0;
    ca.ex_date = 20260107;
    ca.split_ratio = 2.0;
    cfg.corporate_actions.push_back(ca);
  }
  const BacktestResult result = run(panel, cfg, weights);
  CHECK(result.equity[2] == result.equity[1]);
  CHECK(result.equity[3] == result.equity[1]);
  CHECK(result.equity[4] == result.equity[1] + to_money(split ? 100000.0 : 50000.0));
  CHECK(result.final_position_qty[0] == (split ? 100000 : 50000));
}
