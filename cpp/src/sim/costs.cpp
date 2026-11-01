#include "costs.h"

#include <cmath>

namespace qc {
namespace {

Money rate_fee(Money amount, double rate) {
  if (amount <= 0 || rate <= 0.0) return 0;
  return static_cast<Money>(std::llround(static_cast<double>(amount) * rate));
}

}  // namespace

CostBreakdown compute_costs(const CostModel& model, Side side, Money amount,
                            const SecurityCtx& sec) {
  CostBreakdown out;
  if (amount < 0) amount = 0;
  out.commission = rate_fee(amount, model.commission_rate);
  if (out.commission < model.min_commission) out.commission = model.min_commission;
  if (side == Side::Sell) out.stamp_duty = rate_fee(amount, model.stamp_duty_rate);
  if (!model.transfer_fee_shanghai_only || sec.is_shanghai) {
    out.transfer_fee = rate_fee(amount, model.transfer_fee_rate);
  }
  out.other_fee =
      rate_fee(amount, model.exchange_fee_rate) + rate_fee(amount, model.reg_fee_rate);
  out.total = out.commission + out.stamp_duty + out.transfer_fee + out.other_fee;
  return out;
}

}  // namespace qc
