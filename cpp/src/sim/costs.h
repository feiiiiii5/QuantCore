#pragma once
// Deterministic A-share transaction cost model (fixed point, 1e-4 CNY).
// Semantics: docs/engine-semantics.md §2. Rates are configurable; applicability is
// TODO(verify) against official sources (docs/rules-sources.md).
#include "qcore/engine.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace qc {

// Exchange/board context needed to decide fee applicability.
struct SecurityCtx {
  int board = 0;             // matches Security::board: 0 MAIN, 1 GEM, 2 STAR, 3 BSE
  bool is_st = false;        // ST/*ST flag on the trading date
  bool is_shanghai = false;  // SH-listed (code starts with '6'); transfer fee applicability
};

struct CostBreakdown {
  Money commission = 0;    // max(min_commission, amount * commission_rate)
  Money stamp_duty = 0;    // sell only
  Money transfer_fee = 0;  // 过户费
  Money other_fee = 0;     // 经手费 + 证管费
  Money total = 0;
};

// All components are rounded independently to the nearest 1e-4 CNY with
// std::llround (half away from zero), then summed; commission is floored at
// CostModel::min_commission. Deterministic for a fixed amount/rate.
// TODO(verify) exact rounding convention (per-component vs per-total; cent vs 1e-4).
CostBreakdown compute_costs(const CostModel& model, Side side, Money amount,
                            const SecurityCtx& sec);

inline SecurityCtx security_ctx(const Security& s, bool is_st = false) {
  SecurityCtx ctx;
  ctx.board = s.board;
  ctx.is_st = is_st;
  ctx.is_shanghai = !s.code.empty() && s.code[0] == '6';
  return ctx;
}

}  // namespace qc
