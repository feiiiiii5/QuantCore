#include "../sim/metrics.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace qc {
namespace {

struct FifoLot {
  Qty qty = 0;
  Money cost = 0;  // total cost of remaining shares, fees included
};

Money take_cost(std::vector<FifoLot>& lots, Qty& need, Money& removed) {
  while (need > 0 && !lots.empty()) {
    FifoLot& lot = lots.front();
    if (lot.qty <= need) {
      removed += lot.cost;
      need -= lot.qty;
      lots.erase(lots.begin());
    } else {
      const double ratio = static_cast<double>(need) / static_cast<double>(lot.qty);
      Money part = static_cast<Money>(std::llround(static_cast<double>(lot.cost) * ratio));
      if (part < 0)
        part = 0;
      if (part > lot.cost)
        part = lot.cost;
      removed += part;
      lot.cost -= part;
      lot.qty -= need;
      need = 0;
    }
  }
  return removed;
}

}  // namespace

Metrics compute_metrics(const std::vector<Money>& equity, Money initial_cash,
                        const std::vector<Trade>& trades, int annual_days, double risk_free_rate) {
  Metrics m;
  const size_t n = equity.size();
  m.trading_days = static_cast<int64_t>(n);
  if (annual_days <= 0)
    annual_days = 244;
  const double rf_period = risk_free_rate / static_cast<double>(annual_days);

  double total_return = 0.0;
  if (initial_cash > 0 && n > 0) {
    total_return = static_cast<double>(equity.back()) / static_cast<double>(initial_cash) - 1.0;
  }
  m.total_return = total_return;

  std::vector<double> returns;
  returns.reserve(n);
  double prev = static_cast<double>(initial_cash);
  for (size_t i = 0; i < n; ++i) {
    const double cur = static_cast<double>(equity[i]);
    returns.push_back(prev > 0.0 ? cur / prev - 1.0 : 0.0);
    prev = cur;
  }

  double annualized;
  if (n == 0) {
    annualized = 0.0;
  } else if (total_return <= -1.0) {
    annualized = -1.0;
  } else {
    annualized =
        std::pow(1.0 + total_return, static_cast<double>(annual_days) / static_cast<double>(n)) -
        1.0;
  }
  m.annualized_return = annualized;

  double volatility = 0.0;
  double sharpe = 0.0;
  double sortino = 0.0;
  if (n >= 2) {
    double mean = 0.0;
    for (double r : returns)
      mean += r;
    mean /= static_cast<double>(n);
    double var = 0.0;
    for (double r : returns)
      var += (r - mean) * (r - mean);
    var /= static_cast<double>(n - 1);
    const double stddev = std::sqrt(var);
    volatility = stddev * std::sqrt(static_cast<double>(annual_days));
    if (stddev > 0.0) {
      sharpe = (mean - rf_period) / stddev * std::sqrt(static_cast<double>(annual_days));
    }
    double downside_sq = 0.0;
    for (double r : returns) {
      const double excess = r - rf_period;
      if (excess < 0.0)
        downside_sq += excess * excess;
    }
    const double downside = std::sqrt(downside_sq / static_cast<double>(n));
    if (downside > 0.0) {
      sortino = (mean - rf_period) / downside * std::sqrt(static_cast<double>(annual_days));
    }
  }
  m.volatility = volatility;
  m.sharpe = sharpe;
  m.sortino = sortino;

  double max_drawdown = 0.0;
  double peak = initial_cash > 0 ? static_cast<double>(initial_cash) : 0.0;
  for (Money e : equity) {
    const double v = static_cast<double>(e);
    if (v > peak)
      peak = v;
    if (peak > 0.0) {
      const double dd = 1.0 - v / peak;
      if (dd > max_drawdown)
        max_drawdown = dd;
    }
  }
  m.max_drawdown = max_drawdown;
  m.calmar = max_drawdown > 0.0 ? annualized / max_drawdown : 0.0;

  // Fees, turnover, FIFO round-trip statistics from the fill list.
  Money total_fees = 0;
  int128 traded_notional = 0;
  int64_t fills = 0;
  int128 equity_sum = static_cast<int128>(initial_cash);
  for (Money e : equity)
    equity_sum += static_cast<int128>(e);
  std::vector<std::vector<FifoLot>> lots;
  int64_t sells = 0;
  int64_t wins = 0;
  int128 gross_profit = 0;
  int128 gross_loss = 0;
  size_t max_sec = 0;
  bool needs_fifo = false;
  for (const Trade& t : trades) {
    if (t.reason != RejectReason::None || t.qty <= 0)
      continue;
    ++fills;
    total_fees += t.fee_total;
    traded_notional += static_cast<int128>(t.amount < 0 ? -t.amount : t.amount);
    if (t.sec < 0)
      continue;
    max_sec = std::max(max_sec, static_cast<size_t>(t.sec));
    if (t.side == Side::Sell && !t.realized_pnl.has_value())
      needs_fifo = true;
  }
  if (needs_fifo)
    lots.resize(max_sec + 1);
  for (const Trade& t : trades) {
    if (t.reason != RejectReason::None || t.qty <= 0 || t.sec < 0)
      continue;
    if (t.side == Side::Buy) {
      if (needs_fifo)
        lots[static_cast<size_t>(t.sec)].push_back(FifoLot{t.qty, t.amount + t.fee_total});
    } else {
      Qty need = t.qty;
      Money removed = 0;
      if (needs_fifo)
        take_cost(lots[static_cast<size_t>(t.sec)], need, removed);
      const Money proceeds = t.amount - t.fee_total;
      const Money pnl = t.realized_pnl.value_or(proceeds - removed);
      ++sells;
      if (pnl > 0) {
        ++wins;
        gross_profit += static_cast<int128>(pnl);
      } else if (pnl < 0) {
        gross_loss += static_cast<int128>(-pnl);
      }
    }
  }
  m.total_fees = total_fees;
  m.trade_count = fills;
  m.win_rate = sells > 0 ? static_cast<double>(wins) / static_cast<double>(sells) : 0.0;
  if (sells == 0) {
    m.profit_factor = 0.0;
  } else if (gross_loss > 0) {
    m.profit_factor = static_cast<double>(gross_profit) / static_cast<double>(gross_loss);
  } else if (gross_profit > 0) {
    m.profit_factor = std::numeric_limits<double>::infinity();
  } else {
    m.profit_factor = 0.0;
  }
  const double mean_equity = static_cast<double>(equity_sum) / static_cast<double>(n + 1);
  m.turnover = mean_equity > 0.0 ? static_cast<double>(traded_notional) / mean_equity : 0.0;
  return m;
}

}  // namespace qc
