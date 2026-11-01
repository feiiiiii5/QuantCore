#pragma once
// T+1 order generation and matching for one rebalance date. Targets are signal-close
// weights; fills use the next trading day's ExecModel price. Sells are matched before
// buys (conservative when intraday order is unknown), then cash/participation limits.
#include <cstdint>
#include <map>
#include <vector>

#include "costs.h"
#include "ledger.h"
#include "panel_views.h"
#include "qcore/engine.h"
#include "qcore/panel.h"

namespace qc {

struct ExecRequest {
  size_t date_index = 0;                        // panel row of the execution day
  Date date = kInvalidDate;
  const std::vector<double>* weights = nullptr;  // target weights (signal date)
  Money signal_equity = 0;                       // equity at signal close
  const std::vector<Px>* prev_close = nullptr;   // CA-adjusted previous close / sec
};

struct ExecOutcome {
  Money fees = 0;
  int64_t fills = 0;
  int64_t rejects = 0;
};

// Rule primitives exposed for unit tests (deterministic, side-effect free).
Px exec_reference_price(ExecType type, Px open, Px high, Px low, Px close, double volume,
                        double amount_yuan);
// After-hours fixed-price trading: STAR is supported from the start; other boards only
// from RuleSet::after_hours_extension_date. TODO(verify) exact historical scope.
bool after_hours_available(const RuleSet& rules, int board, Date date);
Px apply_slippage(Px ref, Side side, double slippage_bps, const RuleSet& rules);
// Clamp into [low, high] and the daily limit band; caller validates the result.
Px clamp_fill_price(Px fill, Px low, Px high, Px limit_up, Px limit_down);

class Executor {
 public:
  Executor(const PanelViews& views, const BacktestConfig& cfg, Ledger& ledger);

  ExecOutcome execute(const ExecRequest& req, std::vector<Trade>& trades,
                      std::map<RejectReason, uint64_t>& reasons);

 private:
  struct Intent {
    int32_t sec = -1;
    Side side = Side::Buy;
    Qty qty = 0;
  };

  Px reference_px(size_t sec, size_t time) const;
  SecurityCtx context(size_t sec, size_t time) const;
  // Validates suspension/limit/one-word/price band and computes fill price + volume cap.
  // Returns RejectReason::None when tradable; cap < 0 means "no volume field -> unlimited".
  RejectReason prepare(size_t sec, size_t time, Side side, const std::vector<Px>& prev_close,
                       Px& fill_px, Qty& volume_cap) const;
  Qty affordable(size_t sec, Qty want, Px fill_px) const;
  void reject(size_t sec, Side side, Date date, RejectReason reason, std::vector<Trade>& trades,
              std::map<RejectReason, uint64_t>& reasons, ExecOutcome& out) const;
  void execute_one(const Intent& intent, Date date, size_t time,
                   const std::vector<Px>& prev_close, std::vector<Trade>& trades,
                   std::map<RejectReason, uint64_t>& reasons, ExecOutcome& out);

  const PanelViews& views_;
  const BacktestConfig& cfg_;
  Ledger& ledger_;
  std::vector<SecurityCtx> meta_;  // board / listing venue per security (ST is per date)
};

}  // namespace qc
