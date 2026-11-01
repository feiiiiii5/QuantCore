#pragma once
// Cached read-only views over the Panel fields used by the backtest engine.
#include <cmath>
#include <string>

#include "qcore/engine.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace qc {

struct PanelViews {
  const Panel* panel = nullptr;
  FieldView open;
  FieldView high;
  FieldView low;
  FieldView close;
  FieldView volume;
  FieldView amount;
  FieldView limit_up;
  FieldView limit_down;
  FieldView suspended;
  FieldView st;

  static PanelViews load(const Panel& p, const BacktestConfig& cfg) {
    PanelViews v;
    v.panel = &p;
    auto get = [&p](const std::string& name) {
      return p.has_field(name) ? p.field(name) : FieldView{};
    };
    v.open = get(cfg.f_open);
    v.high = get(cfg.f_high);
    v.low = get(cfg.f_low);
    v.close = get(cfg.f_close);
    v.volume = get(cfg.f_volume);
    v.amount = get(cfg.f_amount);
    v.limit_up = get(cfg.f_limit_up);
    v.limit_down = get(cfg.f_limit_down);
    v.suspended = get(cfg.f_suspended);
    v.st = get(cfg.f_st);
    return v;
  }

  static bool has(const FieldView& f) {
    return f.data != nullptr;
  }

  static double value(const FieldView& f, size_t sec, size_t time) {
    return f.data == nullptr ? kNaN : f.at(sec, time);
  }

  // Fixed-point price; returns 0 for NaN / non-positive / non-finite values.
  static Px px(const FieldView& f, size_t sec, size_t time) {
    const double v = value(f, sec, time);
    if (!std::isfinite(v) || v <= 0.0)
      return 0;
    return to_px(v);
  }

  static bool flag(const FieldView& f, size_t sec, size_t time) {
    const double v = value(f, sec, time);
    return std::isfinite(v) && v > 0.5;
  }

  size_t n_sec() const {
    return panel->n_sec();
  }
  size_t n_time() const {
    return panel->n_time();
  }
};

}  // namespace qc
