#pragma once
// A-share trading rule primitives: board limits, lot sizes, tick rounding.
// Board codes match Security::board (0 MAIN, 1 GEM, 2 STAR, 3 BSE).
// All rules carry TODO(verify) until official sources are linked in docs/rules-sources.md.
#include "costs.h"
#include "qcore/engine.h"
#include "qcore/types.h"

namespace qc {

// Minimum buy size for a board: 100 (main/GEM), 200 (STAR), 100 (BSE).
int64_t board_lot(const RuleSet& rules, int board);

// Canonicalize a raw buy share count to a legal order:
//   MAIN/GEM: multiple of main_lot; STAR: >= star_lot then 1-share steps;
//   BSE: >= bse_lot then 1-share steps. Returns 0 when below the minimum.
Qty canon_buy_qty(const RuleSet& rules, int board, Qty raw_qty);

// Daily price limit fraction by board/ST/date. ST switch applies to MAIN only
// (TODO(verify) GEM/STAR/BSE ST limits and new-listing special cases).
double limit_pct(const RuleSet& rules, int board, bool is_st, Date date);

// Round a fixed-point price to the configured minimum tick (0.01 CNY default).
// Positive values round half up; prices are non-negative in this engine.
Px round_to_tick(Px raw, const RuleSet& rules);

// Limit-up / limit-down price from the (corporate-action adjusted) previous close.
// Returns 0 when the reference close is unknown, meaning "no limit information".
Px limit_up_px(const RuleSet& rules, Px prev_close, int board, bool is_st, Date date);
Px limit_down_px(const RuleSet& rules, Px prev_close, int board, bool is_st, Date date);

}  // namespace qc
