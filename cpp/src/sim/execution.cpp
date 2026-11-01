#include "execution.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "rules.h"

namespace qc {
namespace {

constexpr Side kBuy = Side::Buy;
constexpr Side kSell = Side::Sell;

bool finite_positive(double v) { return std::isfinite(v) && v > 0.0; }

}  // namespace

Px exec_reference_price(ExecType type, Px open, Px high, Px low, Px close, double volume,
                        double amount_yuan) {
  (void)high;
  (void)low;
  switch (type) {
    case ExecType::NextOpen: return open > 0 ? open : 0;
    case ExecType::NextClose: return close > 0 ? close : 0;
    case ExecType::NextVwap: {
      if (!finite_positive(volume) || !finite_positive(amount_yuan)) return 0;
      const double vwap_yuan = amount_yuan / volume;  // amount is CNY, volume is shares
      if (!finite_positive(vwap_yuan)) return 0;
      return to_px(vwap_yuan);
    }
    case ExecType::AfterHoursFixed: return close > 0 ? close : 0;
  }
  return 0;
}

bool after_hours_available(const RuleSet& rules, int board, Date date) {
  if (!rules.after_hours) return false;
  if (board == 2) return true;  // TODO(verify) STAR after-hours start date
  return date >= rules.after_hours_extension_date;  // TODO(verify) 2026-07-06 expansion
}

Px apply_slippage(Px ref, Side side, double slippage_bps, const RuleSet& rules) {
  if (ref <= 0) return 0;
  if (!(slippage_bps > 0.0)) return ref;
  const double factor = side == kBuy ? 1.0 + slippage_bps / 10000.0
                                     : 1.0 - slippage_bps / 10000.0;
  const double raw = static_cast<double>(ref) * factor;
  if (!finite_positive(raw)) return 0;
  return round_to_tick(static_cast<Px>(std::llround(raw)), rules);
}

Px clamp_fill_price(Px fill, Px low, Px high, Px limit_up, Px limit_down) {
  if (low > 0 && fill < low) fill = low;
  if (high > 0 && fill > high) fill = high;
  if (limit_up > 0 && fill > limit_up) fill = limit_up;
  if (limit_down > 0 && fill < limit_down) fill = limit_down;
  return fill;
}

Executor::Executor(const PanelViews& views, const BacktestConfig& cfg, Ledger& ledger)
    : views_(views), cfg_(cfg), ledger_(ledger) {
  const size_t ns = views.n_sec();
  meta_.resize(ns);
  for (size_t sec = 0; sec < ns; ++sec) {
    meta_[sec] = security_ctx(views.panel->securities()[sec]);
  }
}

SecurityCtx Executor::context(size_t sec, size_t time) const {
  SecurityCtx ctx = meta_[sec];
  ctx.is_st = PanelViews::flag(views_.st, sec, time);
  return ctx;
}

Px Executor::reference_px(size_t sec, size_t time) const {
  const Px open = PanelViews::px(views_.open, sec, time);
  const Px high = PanelViews::px(views_.high, sec, time);
  const Px low = PanelViews::px(views_.low, sec, time);
  const Px close = PanelViews::px(views_.close, sec, time);
  const double volume = PanelViews::value(views_.volume, sec, time);
  const double amount = PanelViews::value(views_.amount, sec, time);
  return exec_reference_price(cfg_.exec.type, open, high, low, close, volume, amount);
}

RejectReason Executor::prepare(size_t sec, size_t time, Side side,
                               const std::vector<Px>& prev_close, Px& fill_px,
                               Qty& volume_cap) const {
  const Panel& panel = *views_.panel;
  const Security& security = panel.securities()[sec];
  const Date date = panel.dates()[time];

  if (PanelViews::flag(views_.suspended, sec, time)) return RejectReason::Suspended;
  // TODO(verify) delisting period / long suspension handling is conservative: a
  // security at/after its delist date is not tradable (engine force-liquidates).
  if (security.delist_date != kInvalidDate && date >= security.delist_date) {
    return RejectReason::NoQuote;
  }

  const double volume = PanelViews::value(views_.volume, sec, time);
  const bool has_volume = PanelViews::has(views_.volume);
  if (has_volume) {
    if (!std::isfinite(volume)) return RejectReason::NoQuote;
    if (volume <= 0.0) return RejectReason::Suspended;  // TODO(verify) zero-volume day
  }

  const Px open = PanelViews::px(views_.open, sec, time);
  const Px high = PanelViews::px(views_.high, sec, time);
  const Px low = PanelViews::px(views_.low, sec, time);
  const Px close = PanelViews::px(views_.close, sec, time);
  if (high <= 0 || low <= 0 || close <= 0 || high < low) return RejectReason::NoQuote;
  const double amount = PanelViews::value(views_.amount, sec, time);
  const Px ref =
      exec_reference_price(cfg_.exec.type, open, high, low, close, volume, amount);
  if (ref <= 0) return RejectReason::NoQuote;

  const bool is_st = PanelViews::flag(views_.st, sec, time);
  const int board = security.board;
  Px limit_up = PanelViews::has(views_.limit_up)
                    ? PanelViews::px(views_.limit_up, sec, time)
                    : 0;
  Px limit_down = PanelViews::has(views_.limit_down)
                      ? PanelViews::px(views_.limit_down, sec, time)
                      : 0;
  const Px prev = sec < prev_close.size() ? prev_close[sec] : 0;
  if (limit_up <= 0) limit_up = limit_up_px(cfg_.rules, prev, board, is_st, date);
  if (limit_down <= 0) limit_down = limit_down_px(cfg_.rules, prev, board, is_st, date);

  if (side == kBuy && limit_up > 0 && ref >= limit_up) return RejectReason::LimitUp;
  if (side == kSell && limit_down > 0 && ref <= limit_down) return RejectReason::LimitDown;

  // One-word board (high == low): no continuous trading. Conservative: reject both
  // sides; attribute to the touching limit when the price is at a limit.
  if (high == low) {
    if (side == kBuy && limit_up > 0 && high >= limit_up) return RejectReason::LimitUp;
    if (side == kSell && limit_down > 0 && low <= limit_down) {
      return RejectReason::LimitDown;
    }
    return RejectReason::NoQuote;
  }

  if (cfg_.exec.type == ExecType::AfterHoursFixed &&
      !after_hours_available(cfg_.rules, board, date)) {
    return RejectReason::NoQuote;
  }

  fill_px = cfg_.exec.type == ExecType::AfterHoursFixed
                ? close
                : apply_slippage(ref, side, cfg_.exec.slippage_bps, cfg_.rules);
  if (fill_px <= 0) return RejectReason::PriceOutOfRange;
  fill_px = clamp_fill_price(fill_px, low, high, limit_up, limit_down);
  if (fill_px < low || fill_px > high) return RejectReason::PriceOutOfRange;
  // 盘后固定价格成交价即收盘价，不受 [low, high] 之外的滑点影响。
  if (cfg_.exec.type != ExecType::AfterHoursFixed && (fill_px <= 0)) {
    return RejectReason::PriceOutOfRange;
  }

  volume_cap = -1;
  if (has_volume) {
    const double cap = std::floor(volume * cfg_.exec.max_participation);
    if (!(cap >= 1.0)) return RejectReason::NoQuote;
    volume_cap = static_cast<Qty>(cap);
  }
  return RejectReason::None;
}

Qty Executor::affordable(size_t sec, Qty want, Px fill_px) const {
  if (want <= 0 || fill_px <= 0) return 0;
  const Money cash = ledger_.cash();
  const SecurityCtx ctx = meta_[sec];
  auto cost_of = [&](Qty qty) -> Money {
    const Money amount = notional(fill_px, qty);
    const CostBreakdown costs = compute_costs(cfg_.costs, kBuy, amount, ctx);
    return amount + costs.total;
  };
  const int board = meta_[sec].board;
  if (board == 2 || board == 3) {
    const int64_t min_qty = board == 2 ? cfg_.rules.star_lot : cfg_.rules.bse_lot;
    if (want < min_qty) return 0;
    if (cost_of(min_qty) > cash) return 0;
    Qty lo = min_qty;
    Qty hi = want;
    while (lo < hi) {
      const Qty mid = lo + (hi - lo + 1) / 2;
      if (cost_of(mid) <= cash) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }
    return lo;
  }
  const int64_t lot = cfg_.rules.main_lot > 0 ? cfg_.rules.main_lot : 100;
  const Qty units = want / lot;
  if (units <= 0) return 0;
  Qty lo = 0;
  Qty hi = units;
  while (lo < hi) {
    const Qty mid = lo + (hi - lo + 1) / 2;
    if (cost_of(mid * lot) <= cash) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo * lot;
}

void Executor::reject(size_t sec, Side side, Date date, RejectReason reason,
                      std::vector<Trade>& trades, std::map<RejectReason, uint64_t>& reasons,
                      ExecOutcome& out) const {
  reasons[reason] += 1;
  out.rejects += 1;
  if (cfg_.trace == TraceLevel::Full) {
    Trade tr;
    tr.date = date;
    tr.sec = static_cast<int32_t>(sec);
    tr.side = side;
    tr.qty = 0;
    tr.reason = reason;
    trades.push_back(tr);
  }
}

void Executor::execute_one(const Intent& intent, Date date, size_t time,
                           const std::vector<Px>& prev_close, std::vector<Trade>& trades,
                           std::map<RejectReason, uint64_t>& reasons, ExecOutcome& out) {
  const size_t sec = static_cast<size_t>(intent.sec);
  Px fill_px = 0;
  Qty volume_cap = -1;
  const RejectReason pre =
      prepare(sec, time, intent.side, prev_close, fill_px, volume_cap);
  if (pre != RejectReason::None) {
    reject(sec, intent.side, date, pre, trades, reasons, out);
    return;
  }
  Qty qty = intent.qty;
  if (volume_cap >= 0 && qty > volume_cap) qty = volume_cap;
  if (intent.side == kSell) {
    const Qty available = ledger_.position(sec).sellable(date, cfg_.rules.t_plus_one);
    if (available <= 0) {
      reject(sec, kSell, date, RejectReason::TPlusOne, trades, reasons, out);
      return;
    }
    if (qty > available) qty = available;
    if (qty <= 0) {
      reject(sec, kSell, date, RejectReason::NoQuote, trades, reasons, out);
      return;
    }
  } else {
    qty = canon_buy_qty(cfg_.rules, meta_[sec].board, qty);
    if (qty <= 0) {
      reject(sec, kBuy, date, RejectReason::NoQuote, trades, reasons, out);
      return;
    }
    qty = affordable(sec, qty, fill_px);
    if (qty <= 0) {
      reject(sec, kBuy, date, RejectReason::InsufficientCash, trades, reasons, out);
      return;
    }
  }
  const Money amount = notional(fill_px, qty);
  const CostBreakdown costs = compute_costs(cfg_.costs, intent.side, amount, context(sec, time));
  if (intent.side == kBuy) {
    ledger_.add_buy(intent.sec, date, qty, amount, costs.total);
  } else {
    ledger_.add_sell(intent.sec, date, qty, amount, costs.total);
  }
  Trade tr;
  tr.date = date;
  tr.sec = intent.sec;
  tr.side = intent.side;
  tr.px = fill_px;
  tr.qty = qty;
  tr.amount = amount;
  tr.commission = costs.commission;
  tr.stamp_duty = costs.stamp_duty;
  tr.transfer_fee = costs.transfer_fee;
  tr.other_fee = costs.other_fee;
  tr.fee_total = costs.total;
  tr.reason = RejectReason::None;
  trades.push_back(tr);
  out.fills += 1;
  out.fees += costs.total;
}

ExecOutcome Executor::execute(const ExecRequest& req, std::vector<Trade>& trades,
                              std::map<RejectReason, uint64_t>& reasons) {
  if (req.weights == nullptr) {
    throw std::invalid_argument("[execution] target weights are required");
  }
  ExecOutcome out;
  const size_t time = req.date_index;
  const Date date = req.date;
  const size_t ns = views_.n_sec();
  const std::vector<double>& weights = *req.weights;
  const std::vector<Px>& prev_close =
      req.prev_close != nullptr ? *req.prev_close : std::vector<Px>{};

  std::vector<Intent> intents;
  intents.reserve(ns);
  for (size_t sec = 0; sec < ns; ++sec) {
    const double weight = sec < weights.size() ? weights[sec] : kNaN;
    if (std::isnan(weight)) continue;  // NaN element: hold the existing position
    const Qty held = ledger_.position_qty(static_cast<int32_t>(sec));
    if (!std::isfinite(weight)) {
      reject(sec, weight > 0.0 ? kBuy : kSell, date, RejectReason::MaxWeight, trades,
             reasons, out);
      continue;
    }
    if (weight <= 0.0 && held == 0) continue;
    const Px ref = reference_px(sec, time);
    if (ref <= 0) {
      // Prefer the most specific rejection reason when the quote is unusable.
      RejectReason why = RejectReason::NoQuote;
      if (PanelViews::flag(views_.suspended, sec, time)) {
        why = RejectReason::Suspended;
      } else if (PanelViews::has(views_.volume)) {
        const double vol = PanelViews::value(views_.volume, sec, time);
        if (std::isfinite(vol) && vol <= 0.0) why = RejectReason::Suspended;
      }
      reject(sec, weight > 0.0 ? kBuy : kSell, date, why, trades, reasons, out);
      continue;
    }
    Money target_value = 0;
    Qty desired = 0;
    if (weight > 0.0) {
      target_value = static_cast<Money>(
          std::llround(weight * static_cast<double>(req.signal_equity)));
      const Qty raw = target_value / ref;
      desired = canon_buy_qty(cfg_.rules, meta_[sec].board, raw);
    }
    if (desired == held) continue;
    const Side side = desired > held ? kBuy : kSell;
    const Money current_value = notional(ref, held);
    const Money delta = target_value - current_value;
    const Money abs_delta = delta >= 0 ? delta : -delta;
    if (abs_delta < cfg_.exec.min_rebalance_value) {
      reject(sec, side, date, RejectReason::MinRebalance, trades, reasons, out);
      continue;
    }
    Intent intent;
    intent.sec = static_cast<int32_t>(sec);
    intent.side = side;
    intent.qty = side == kBuy ? desired - held : held - desired;
    intents.push_back(intent);
  }
  // Conservative when intraday ordering is unknown: all sells before all buys.
  for (const Intent& intent : intents) {
    if (intent.side == kSell) {
      execute_one(intent, date, time, prev_close, trades, reasons, out);
    }
  }
  for (const Intent& intent : intents) {
    if (intent.side == kBuy) {
      execute_one(intent, date, time, prev_close, trades, reasons, out);
    }
  }
  return out;
}

}  // namespace qc
