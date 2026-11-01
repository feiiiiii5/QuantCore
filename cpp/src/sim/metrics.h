#pragma once
// Performance metrics over a fixed-point equity curve and the fill list.
// Returns are computed in double (ratios are scale-free); fees stay fixed-point.
#include <vector>

#include "qcore/engine.h"
#include "qcore/types.h"

namespace qc {

// Convention (documented here because the header Metrics has no field docs):
//  - returns: r[0] = equity[0]/initial_cash - 1, r[t] = equity[t]/equity[t-1] - 1.
//  - annualization: annual_days (default 244) periods per year.
//  - volatility: sample std (ddof=1) of returns * sqrt(annual_days).
//  - sharpe: mean excess / std * sqrt(annual_days); risk_free_rate is a constant
//    annual simple rate converted to per-period (risk_free_rate / annual_days).
//  - sortino: mean excess / downside deviation * sqrt(annual_days), downside deviation
//    is the population root-mean-square of negative excess returns.
//  - max_drawdown: max(1 - equity/peak) as a positive fraction, peak starts at
//    initial_cash and only uses the recorded equity.
//  - calmar: annualized_return / max_drawdown (0 when max_drawdown is 0).
//  - win_rate / profit_factor: per closed sell fill, FIFO cost reconstruction from the
//    trade list (fees included). profit_factor is +inf when there are profits and no
//    losses, 0 when there are no closed trades.
//  - turnover: sum(|fill amount|) / mean equity (mean across initial + recorded equity).
Metrics compute_metrics(const std::vector<Money>& equity, Money initial_cash,
                        const std::vector<Trade>& trades, int annual_days,
                        double risk_free_rate = 0.0);

}  // namespace qc
