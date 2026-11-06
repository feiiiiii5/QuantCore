#pragma once
// Event-driven backtest engine. All prices/amounts are fixed-point 1e-4 CNY internally.
// Semantics: docs/engine-semantics.md; rule sources: docs/rules-sources.md.
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>
#include "qcore/panel.h"
#include "qcore/types.h"
#include "qcore/version.h"

namespace qc {
enum class ExecType : uint32_t { NextOpen = 0, NextClose = 1, NextVwap = 2, AfterHoursFixed = 3 };
enum class TraceLevel : uint32_t { Off = 0, Summary = 1, Full = 2 };
enum class Side : uint32_t { Buy = 0, Sell = 1 };

enum class RejectReason : uint16_t {
  None = 0,
  Suspended = 1,
  LimitUp = 2,
  LimitDown = 3,
  LotSize = 4,
  TPlusOne = 5,
  InsufficientCash = 6,
  NoQuote = 7,
  PriceOutOfRange = 8,
  MinRebalance = 9,
  Canceled = 10,
  MaxPositions = 11,
  MaxWeight = 12,
  IndustryLimit = 13,
  StopLoss = 14,
  StopTakeProfit = 15,
  CorporateAction = 16,
  Unknown = 255
};

struct RuleSet {
  double main_limit_pct = 0.10;
  double gem_limit_pct = 0.20;
  double star_limit_pct = 0.20;
  double bse_limit_pct = 0.30;
  double st_limit_pct = 0.05;
  Date st_limit_change_date = 20260706;  // TODO(verify)
  double st_limit_pct_after = 0.10;      // TODO(verify)
  int64_t main_lot = 100;
  int64_t star_lot = 200;
  int64_t bse_lot = 100;
  bool t_plus_one = true;
  bool after_hours = true;
  Date after_hours_extension_date = 20260706;  // TODO(verify)
  double min_price_tick = 0.01;
};

struct CostModel {
  double commission_rate = 0.0003;
  Money min_commission = 50000;        // 5 CNY in 1e-4
  double stamp_duty_rate = 0.0005;     // sell only; TODO(verify)
  double transfer_fee_rate = 0.00001;  // TODO(verify)
  double exchange_fee_rate = 0.00001;  // TODO(verify)
  double reg_fee_rate = 0.000002;      // TODO(verify)
  bool transfer_fee_shanghai_only = true;
  bool enable_dividend_tax = false;
};

struct ExecModel {
  ExecType type = ExecType::NextOpen;
  double slippage_bps = 0.0;
  double max_participation = 1.0;  // fraction of next-day volume
  Money min_rebalance_value = 0;   // skip rebalance if abs(delta) below this value
};

struct CorporateAction {
  Date ex_date = kInvalidDate;
  int32_t sec = -1;
  double cash_per_share = 0.0;  // CNY per share
  double split_ratio = 1.0;     // shares multiply by this
};

struct BacktestConfig {
  Date start = kInvalidDate;
  Date end = kInvalidDate;
  Money initial_cash = 10000000000LL;  // 1,000,000 CNY
  RuleSet rules;
  CostModel costs;
  ExecModel exec;
  TraceLevel trace = TraceLevel::Summary;
  uint64_t seed = 42;
  int annual_days = 244;
  std::vector<CorporateAction> corporate_actions;
  std::string f_open = "open";
  std::string f_high = "high";
  std::string f_low = "low";
  std::string f_close = "close";
  std::string f_volume = "volume";
  std::string f_amount = "amount";
  std::string f_limit_up = "limit_up";
  std::string f_limit_down = "limit_down";
  std::string f_suspended = "suspended";
  std::string f_st = "st";
};

class CancelToken {
 public:
  void cancel() {
    flag_.store(true, std::memory_order_relaxed);
  }
  bool cancelled() const {
    return flag_.load(std::memory_order_relaxed);
  }

 private:
  std::atomic<bool> flag_{false};
};

// Returns n_sec target weights for a given panel date index. NaN row means "no rebalance".
class TargetSource {
 public:
  virtual ~TargetSource() = default;
  virtual const std::vector<double>& weights(size_t date_index) = 0;
};

class MatrixTargetSource : public TargetSource {
 public:
  MatrixTargetSource(std::vector<std::vector<double>> rows, size_t n_sec);
  const std::vector<double>& weights(size_t date_index) override;

 private:
  std::vector<std::vector<double>> rows_;
  std::vector<double> empty_;
};

struct Trade {
  Date date = kInvalidDate;
  int32_t sec = -1;
  Side side = Side::Buy;
  Px px = 0;
  Qty qty = 0;
  Money amount = 0;
  Money commission = 0;
  Money stamp_duty = 0;
  Money transfer_fee = 0;
  Money other_fee = 0;
  Money fee_total = 0;
  RejectReason reason = RejectReason::None;
  // Engine sell fills carry the ledger's fee-inclusive FIFO P&L. Keeping this
  // optional also supports metrics over caller-constructed trade histories.
  std::optional<Money> realized_pnl;
};

struct Metrics {
  double total_return = 0.0;
  double annualized_return = 0.0;
  double volatility = 0.0;
  double sharpe = 0.0;
  double sortino = 0.0;
  double max_drawdown = 0.0;
  double calmar = 0.0;
  double win_rate = 0.0;
  double profit_factor = 0.0;
  double turnover = 0.0;
  Money total_fees = 0;
  int64_t trade_count = 0;
  int64_t trading_days = 0;
};

struct ReasonCount {
  RejectReason reason = RejectReason::None;
  uint64_t count = 0;
};

struct BacktestResult {
  std::vector<Date> dates;
  std::vector<Money> equity;
  std::vector<Money> cash;
  std::vector<Money> market_value;
  std::vector<Trade> trades;
  Metrics metrics;
  std::vector<ReasonCount> reasons;
  std::vector<int32_t> final_position_secs;
  std::vector<Qty> final_position_qty;
  std::string engine_version = version();
  uint64_t seed = 0;
};

class Engine {
 public:
  Engine(const Panel& panel, BacktestConfig config);
  BacktestResult run(TargetSource& targets, CancelToken& cancel);

 private:
  const Panel& panel_;
  BacktestConfig cfg_;
};
}  // namespace qc
