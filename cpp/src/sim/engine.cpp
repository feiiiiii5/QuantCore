#include "qcore/engine.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "costs.h"
#include "execution.h"
#include "ledger.h"
#include "metrics.h"
#include "panel_views.h"
#include "rules.h"

namespace qc {
namespace {

[[noreturn]] void invalid(const std::string& msg) {
  throw std::invalid_argument("[engine] " + msg);
}

void validate_config(const BacktestConfig& cfg) {
  if (cfg.initial_cash <= 0)
    invalid("initial_cash must be positive");
  if (cfg.annual_days <= 0)
    invalid("annual_days must be positive");
  const RuleSet& rules = cfg.rules;
  if (rules.main_lot <= 0 || rules.star_lot <= 0 || rules.bse_lot <= 0) {
    invalid("lot sizes must be positive");
  }
  if (!(rules.min_price_tick > 0.0))
    invalid("min_price_tick must be positive");
  const double pcts[] = {rules.main_limit_pct, rules.gem_limit_pct, rules.star_limit_pct,
                         rules.bse_limit_pct,  rules.st_limit_pct,  rules.st_limit_pct_after};
  for (double p : pcts) {
    if (!(p >= 0.0) || p >= 1.0)
      invalid("price limit pct must be in [0, 1)");
  }
  const CostModel& costs = cfg.costs;
  if (costs.commission_rate < 0.0 || costs.stamp_duty_rate < 0.0 || costs.transfer_fee_rate < 0.0 ||
      costs.exchange_fee_rate < 0.0 || costs.reg_fee_rate < 0.0 || costs.min_commission < 0) {
    invalid("cost model rates must be non-negative");
  }
  if (!(cfg.exec.max_participation > 0.0))
    invalid("max_participation must be positive");
  if (!std::isfinite(cfg.exec.slippage_bps) || cfg.exec.slippage_bps < -10000.0) {
    invalid("slippage_bps must be finite and >= -10000");
  }
  if (cfg.exec.min_rebalance_value < 0)
    invalid("min_rebalance_value must be non-negative");
  const int exec_type = static_cast<int>(cfg.exec.type);
  if (exec_type < 0 || exec_type > 3)
    invalid("unknown exec type");
}

bool any_finite(const std::vector<double>& row) {
  for (double v : row) {
    if (!std::isnan(v))
      return true;
  }
  return false;
}

void set_trade_pnl_fields(Trade& tr, const CostBreakdown& costs) {
  tr.commission = costs.commission;
  tr.stamp_duty = costs.stamp_duty;
  tr.transfer_fee = costs.transfer_fee;
  tr.other_fee = costs.other_fee;
  tr.fee_total = costs.total;
}

}  // namespace

MatrixTargetSource::MatrixTargetSource(std::vector<std::vector<double>> rows, size_t n_sec)
    : rows_(std::move(rows)) {
  // Rows shorter than the panel are padded with NaN ("hold"), never with 0 ("exit").
  for (auto& row : rows_) {
    if (!row.empty() && row.size() < n_sec)
      row.resize(n_sec, kNaN);
  }
}

const std::vector<double>& MatrixTargetSource::weights(size_t date_index) {
  if (date_index >= rows_.size())
    return empty_;
  return rows_[date_index];
}

Engine::Engine(const Panel& panel, BacktestConfig config) : panel_(panel), cfg_(std::move(config)) {
  validate_config(cfg_);
  for (const CorporateAction& ca : cfg_.corporate_actions) {
    if (ca.sec < 0 || static_cast<size_t>(ca.sec) >= panel_.n_sec() || ca.ex_date == kInvalidDate) {
      invalid("corporate action has invalid security/ex_date");
    }
    if (!std::isfinite(ca.cash_per_share) || !std::isfinite(ca.split_ratio) ||
        ca.cash_per_share < 0.0 || !(ca.split_ratio > 0.0)) {
      invalid("corporate action cash/split_ratio invalid");
    }
    const bool in_window = (cfg_.start == kInvalidDate || ca.ex_date >= cfg_.start) &&
                           (cfg_.end == kInvalidDate || ca.ex_date <= cfg_.end);
    if (in_window && cfg_.costs.enable_dividend_tax && ca.cash_per_share > 0.0) {
      invalid("dividend tax is not implemented; use pre-tax dividends");
    }
  }
}

BacktestResult Engine::run(TargetSource& targets, CancelToken& cancel) {
  const Panel& panel = panel_;
  const size_t ns = panel.n_sec();
  const size_t nt = panel.n_time();
  BacktestResult result;
  result.seed = cfg_.seed;

  Ledger ledger(cfg_.initial_cash, cfg_.rules.t_plus_one, ns);
  std::map<RejectReason, uint64_t> reasons;

  auto finalize = [&]() {
    result.metrics =
        compute_metrics(result.equity, cfg_.initial_cash, result.trades, cfg_.annual_days, 0.0);
    for (const auto& kv : reasons) {
      if (kv.second > 0)
        result.reasons.push_back(ReasonCount{kv.first, kv.second});
    }
    const std::vector<LedgerPosition>& positions = ledger.positions();
    for (size_t sec = 0; sec < positions.size(); ++sec) {
      if (positions[sec].qty > 0) {
        result.final_position_secs.push_back(static_cast<int32_t>(sec));
        result.final_position_qty.push_back(positions[sec].qty);
      }
    }
  };

  if (nt == 0 || ns == 0) {
    finalize();
    return result;
  }

  PanelViews views = PanelViews::load(panel, cfg_);
  if (!PanelViews::has(views.close)) {
    invalid("panel has no close field '" + cfg_.f_close + "'");
  }
  if (!PanelViews::has(views.high) || !PanelViews::has(views.low)) {
    invalid("panel needs '" + cfg_.f_high + "'/'" + cfg_.f_low + "' fields");
  }
  if (cfg_.exec.type == ExecType::NextOpen && !PanelViews::has(views.open)) {
    invalid("next_open requires open field '" + cfg_.f_open + "'");
  }
  if (cfg_.exec.type == ExecType::NextVwap &&
      (!PanelViews::has(views.volume) || !PanelViews::has(views.amount))) {
    invalid("next_vwap requires volume/amount fields");
  }

  size_t begin = 0;
  size_t end = nt;
  const std::vector<Date>& all_dates = panel.dates();
  if (cfg_.start != kInvalidDate) {
    begin = static_cast<size_t>(std::lower_bound(all_dates.begin(), all_dates.end(), cfg_.start) -
                                all_dates.begin());
  }
  if (cfg_.end != kInvalidDate) {
    end = static_cast<size_t>(std::upper_bound(all_dates.begin(), all_dates.end(), cfg_.end) -
                              all_dates.begin());
  }
  if (begin >= end) {
    finalize();
    return result;
  }

  std::map<Date, std::vector<CorporateAction>> ca_by_date;
  for (const CorporateAction& ca : cfg_.corporate_actions) {
    ca_by_date[ca.ex_date].push_back(ca);
  }

  Executor executor(views, cfg_, ledger);
  std::vector<Px> prev_close(ns, 0);
  if (begin > 0) {
    for (size_t sec = 0; sec < ns; ++sec) {
      prev_close[sec] = PanelViews::px(views.close, sec, begin - 1);
    }
  }

  bool have_pending = false;
  std::vector<double> pending_weights;
  Money pending_equity = 0;

  for (size_t i = begin; i < end; ++i) {
    if (cancel.cancelled()) {
      reasons[RejectReason::Canceled] += 1;
      break;
    }
    const Date date = all_dates[i];

    // 1) Corporate actions with ex_date == today: adjust lots, prev close and cash.
    std::map<int32_t, Px> adjusted_prev;
    const auto ca_it = ca_by_date.find(date);
    if (ca_it != ca_by_date.end()) {
      for (const CorporateAction& ca : ca_it->second) {
        const size_t sec = static_cast<size_t>(ca.sec);
        const Qty qty_before = ledger.position_qty(ca.sec);
        const Money cash_per_share = to_money(ca.cash_per_share);
        if (qty_before > 0 && cash_per_share > 0) {
          ledger.add_dividend(ca.sec, date, notional(cash_per_share, qty_before));
        }
        if (ca.split_ratio != 1.0)
          ledger.apply_split(ca.sec, ca.split_ratio);
        const Px base = prev_close[sec];
        if (base > 0 && (cash_per_share > 0 || ca.split_ratio != 1.0)) {
          // 除权除息参考价 = (前收盘 - 每股现金红利) / 送转比例 (TODO(verify) 配股等).
          const double raw =
              (static_cast<double>(base) - static_cast<double>(cash_per_share)) / ca.split_ratio;
          adjusted_prev[ca.sec] = raw > 0.0 ? static_cast<Px>(std::llround(raw)) : 0;
          // A suspended ex-date has no new close. Rebase its stale mark with the
          // share/cash adjustment so valuation and forced liquidation stay coherent.
          ledger.mark(ca.sec, adjusted_prev[ca.sec]);
          prev_close[sec] = adjusted_prev[ca.sec];
        }
      }
    }

    // 2) Execute the previous close's target weights at today's price.
    if (have_pending) {
      std::vector<Px> exec_prev_close = prev_close;
      for (const auto& kv : adjusted_prev)
        exec_prev_close[static_cast<size_t>(kv.first)] = kv.second;
      ExecRequest req;
      req.date_index = i;
      req.date = date;
      req.weights = &pending_weights;
      req.signal_equity = pending_equity;
      req.prev_close = &exec_prev_close;
      executor.execute(req, result.trades, reasons);
      have_pending = false;
    }

    // 3) Delisted positions: force liquidation at the last valid mark price.
    // TODO(verify) real delisting-period rules and clearing price; long suspensions are
    // simply not tradable and keep their last mark.
    for (size_t sec = 0; sec < ns; ++sec) {
      const Security& security = panel.securities()[sec];
      if (security.delist_date == kInvalidDate || date < security.delist_date)
        continue;
      const Qty qty = ledger.position_qty(static_cast<int32_t>(sec));
      if (qty <= 0)
        continue;
      const LedgerPosition& position = ledger.position(static_cast<int32_t>(sec));
      if (qty > position.sellable(date, cfg_.rules.t_plus_one))
        continue;  // bought today
      const Px px = position.last_px;
      const Money amount = notional(px, qty);
      CostBreakdown costs;
      if (px > 0) {
        costs = compute_costs(cfg_.costs, Side::Sell, amount, security_ctx(security));
      }
      const Money realized_pnl =
          ledger.add_sell(static_cast<int32_t>(sec), date, qty, amount, costs.total);
      Trade tr;
      tr.date = date;
      tr.sec = static_cast<int32_t>(sec);
      tr.side = Side::Sell;
      tr.px = px;
      tr.qty = qty;
      tr.amount = amount;
      tr.realized_pnl = realized_pnl;
      set_trade_pnl_fields(tr, costs);
      result.trades.push_back(tr);
    }

    // 4) Mark to market at today's close (stale marks kept on missing/suspended data).
    for (size_t sec = 0; sec < ns; ++sec) {
      const Px close_px = PanelViews::px(views.close, sec, i);
      if (close_px > 0) {
        ledger.mark(static_cast<int32_t>(sec), close_px);
        prev_close[sec] = close_px;
      }
    }
    // 5) Assert ledger invariants after every step (throws on any violation).
    ledger.assert_invariants(date);
    result.dates.push_back(date);
    result.cash.push_back(ledger.cash());
    result.market_value.push_back(ledger.market_value());
    result.equity.push_back(ledger.equity());

    // 6) Signal at today's close; execution happens on the next trading day.
    const std::vector<double>& weights = targets.weights(i);
    if (i + 1 < end && any_finite(weights)) {
      pending_weights.assign(weights.begin(), weights.end());
      pending_equity = ledger.equity();
      have_pending = true;
    }
  }

  finalize();
  return result;
}

}  // namespace qc
