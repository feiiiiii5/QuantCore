#pragma once
// Rolling / cross-sectional / technical kernels. NaN means missing; outputs use NaN for
// windows without enough valid observations. Reductions use a fixed left-to-right order.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include "qcore/panel.h"

namespace qc::kernels {
void rolling_sum(const double* x, size_t n, size_t window, double* out);
void rolling_mean(const double* x, size_t n, size_t window, double* out);
void rolling_std(const double* x, size_t n, size_t window, double* out);  // sample std (ddof=1)
void rolling_min(const double* x, size_t n, size_t window, double* out);
void rolling_max(const double* x, size_t n, size_t window, double* out);
void rolling_argmax(const double* x, size_t n, size_t window,
                    double* out);  // index offset in window
void rolling_rank(const double* x, size_t n, size_t window,
                  double* out);  // pct rank of last value in window
void rolling_corr(const double* x, const double* y, size_t n, size_t window, double* out);
void rolling_cov(const double* x, const double* y, size_t n, size_t window, double* out);
void rolling_decay_linear(const double* x, size_t n, size_t window, double* out);

void cross_rank(const double* x, size_t n, double* out);  // 0..1, NaN stays NaN
void cross_zscore(const double* x, size_t n, double* out);
void cross_neutralize(const double* x, size_t n, double* out);  // x - cross-sectional mean
void cross_mad_winsor(const double* x, size_t n, double n_mad, double* out);
void cross_quantile(const double* x, size_t n, int q, int nq,
                    double* out);  // out[i] = 0..nq-1 bucket; q reserved/unused (validated)

// Panel-wide convenience: input field, output same shape as field layout.
void rolling_panel(const Panel& panel, const std::string& field, size_t window,
                   const std::string& op, std::vector<double>& out, Layout out_layout);
void cross_panel(const Panel& panel, const std::string& field, const std::string& op,
                 std::vector<double>& out, Layout out_layout);

// Technical indicators. Inputs/outputs are single series; callers slice panel columns.
void ma(const double* close, size_t n, size_t window, double* out);
void ema(const double* close, size_t n, size_t window, double* out);
void macd(const double* close, size_t n, int fast, int slow, int signal, double* dif, double* dea,
          double* hist);
void rsi(const double* close, size_t n, size_t window, double* out);
void kdj(const double* high, const double* low, const double* close, size_t n, int k_period,
         int d_period, int j_period, double* k, double* d, double* j);
void boll(const double* close, size_t n, size_t window, double n_std, double* mid, double* upper,
          double* lower);
void atr(const double* high, const double* low, const double* close, size_t n, size_t window,
         double* out);
void obv(const double* close, const double* volume, size_t n, double* out);
void cci(const double* high, const double* low, const double* close, size_t n, size_t window,
         double* out);
}  // namespace qc::kernels
