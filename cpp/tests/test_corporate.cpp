// Corporate actions, ST limit switch and delisting/forced liquidation cases.
#include <catch2/catch_test_macros.hpp>

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
