// Kernels and technical indicators: fixed reference values (cross-checked against
// numpy/pandas at 1e-12), NaN/warm-up boundaries, parameter validation and the panel-wide
// rolling/cross wrappers. Values were generated from an independent NumPy reference pass.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <filesystem>
#include <limits>
#include <string>
#include <vector>

#include "qcore/kernels.h"
#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

std::string temp_path(const char* tag) {
  static std::atomic<int> counter{0};
  const auto stamp =
      static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
  return (std::filesystem::temp_directory_path() /
          (std::string("qcore_test_") + tag + "_" + std::to_string(stamp) + "_" +
           std::to_string(counter.fetch_add(1)) + ".qpanel"))
      .string();
}

struct TempFile {
  std::string path;
  ~TempFile() {
    std::error_code ec;
    std::filesystem::remove(path, ec);
  }
};

void expect_series(const std::vector<double>& got, const std::vector<double>& want) {
  REQUIRE(got.size() == want.size());
  for (std::size_t i = 0; i < want.size(); ++i) {
    if (std::isnan(want[i])) {
      CHECK(std::isnan(got[i]));
    } else {
      CHECK(got[i] == Catch::Approx(want[i]).margin(1e-12));
    }
  }
}

using Rolling1 = void (*)(const double*, std::size_t, std::size_t, double*);
using Rolling2 = void (*)(const double*, const double*, std::size_t, std::size_t, double*);

std::vector<double> rolling1(Rolling1 fn, const std::vector<double>& x, std::size_t window) {
  std::vector<double> out(x.size(), kNaN);
  fn(x.data(), x.size(), window, out.data());
  return out;
}

std::vector<double> rolling2(Rolling2 fn, const std::vector<double>& x,
                             const std::vector<double>& y, std::size_t window) {
  std::vector<double> out(x.size(), kNaN);
  fn(x.data(), y.data(), x.size(), window, out.data());
  return out;
}

void expect_all_nan(const std::vector<double>& values) {
  for (const double value : values) CHECK(std::isnan(value));
}

}  // namespace

TEST_CASE("rolling kernels match fixed reference values", "[kernels][rolling]") {
  const std::vector<double> x = {1, 2, 3, 4, 5, 6, 7, 8, kNaN, 10};
  const std::vector<double> y = {2, 4, 6, 8, 10, 12, 14, 16, 18, 20};
  const std::size_t w = 4;
  const std::vector<double> rolling_sum4 = {kNaN, kNaN, kNaN, 10.0, 14.0, 18.0, 22.0, 26.0, kNaN, kNaN};
  const std::vector<double> rolling_mean4 = {kNaN, kNaN, kNaN, 2.5, 3.5, 4.5, 5.5, 6.5, kNaN, kNaN};
  const std::vector<double> rolling_std4 = {kNaN, kNaN, kNaN, 1.2909944487358056, 1.2909944487358056, 1.2909944487358056, 1.2909944487358056, 1.2909944487358056, kNaN, kNaN};
  const std::vector<double> rolling_min4 = {kNaN, kNaN, kNaN, 1.0, 2.0, 3.0, 4.0, 5.0, kNaN, kNaN};
  const std::vector<double> rolling_max4 = {kNaN, kNaN, kNaN, 4.0, 5.0, 6.0, 7.0, 8.0, kNaN, kNaN};
  const std::vector<double> rolling_argmax4 = {kNaN, kNaN, kNaN, 3.0, 3.0, 3.0, 3.0, 3.0, kNaN, kNaN};
  const std::vector<double> rolling_rank4 = {kNaN, kNaN, kNaN, 1.0, 1.0, 1.0, 1.0, 1.0, kNaN, kNaN};
  const std::vector<double> rolling_decay4 = {kNaN, kNaN, kNaN, 3.0, 4.0, 5.0, 6.0, 7.0, kNaN, kNaN};
  const std::vector<double> rolling_corr4 = {kNaN, kNaN, kNaN, 1.0, 1.0, 1.0, 1.0, 1.0, kNaN, kNaN};
  const std::vector<double> rolling_cov4 = {kNaN, kNaN, kNaN, 3.3333333333333335, 3.3333333333333335, 3.3333333333333335, 3.3333333333333335, 3.3333333333333335, kNaN, kNaN};
  expect_series(rolling1(qc::kernels::rolling_sum, x, w), rolling_sum4);
  expect_series(rolling1(qc::kernels::rolling_mean, x, w), rolling_mean4);
  expect_series(rolling1(qc::kernels::rolling_std, x, w), rolling_std4);
  expect_series(rolling1(qc::kernels::rolling_min, x, w), rolling_min4);
  expect_series(rolling1(qc::kernels::rolling_max, x, w), rolling_max4);
  expect_series(rolling1(qc::kernels::rolling_argmax, x, w), rolling_argmax4);
  expect_series(rolling1(qc::kernels::rolling_rank, x, w), rolling_rank4);
  expect_series(rolling1(qc::kernels::rolling_decay_linear, x, w), rolling_decay4);
  expect_series(rolling2(qc::kernels::rolling_corr, x, y, w), rolling_corr4);
  expect_series(rolling2(qc::kernels::rolling_cov, x, y, w), rolling_cov4);
}

TEST_CASE("rolling kernels handle warm-up, missing values and boundaries", "[kernels][rolling]") {
  const std::vector<double> short_series = {1, 2, 3};
  const std::size_t w = 2;
  expect_series(rolling1(qc::kernels::rolling_sum, short_series, w),
                std::vector<double>{kNaN, 3, 5});
  expect_series(rolling1(qc::kernels::rolling_mean, short_series, w),
                std::vector<double>{kNaN, 1.5, 2.5});
  expect_series(rolling1(qc::kernels::rolling_std, short_series, w),
                std::vector<double>{kNaN, 0.70710678118654757, 0.70710678118654757});
  expect_series(rolling1(qc::kernels::rolling_rank, short_series, w),
                std::vector<double>{kNaN, 1.0, 1.0});
  expect_series(rolling1(qc::kernels::rolling_decay_linear, short_series, w),
                std::vector<double>{kNaN, 5.0 / 3.0, 8.0 / 3.0});
  // window == 1: sum/mean/min/max/argmax/rank/decay pass through; std/corr/cov undefined.
  expect_series(rolling1(qc::kernels::rolling_sum, short_series, 1),
                std::vector<double>{1, 2, 3});
  expect_series(rolling1(qc::kernels::rolling_argmax, short_series, 1),
                std::vector<double>{0, 0, 0});
  expect_series(rolling1(qc::kernels::rolling_rank, short_series, 1),
                std::vector<double>{1, 1, 1});
  expect_all_nan(rolling1(qc::kernels::rolling_std, short_series, 1));
  expect_all_nan(rolling1(qc::kernels::rolling_std, short_series, 4));  // window > n
  expect_all_nan(rolling1(qc::kernels::rolling_sum, short_series, 4));
  expect_all_nan(rolling2(qc::kernels::rolling_corr, short_series, short_series, 1));
  expect_all_nan(rolling1(qc::kernels::rolling_mean,
                          std::vector<double>{kNaN, kNaN, kNaN}, 2));
  expect_series(rolling1(qc::kernels::rolling_mean,
                         std::vector<double>{1, 2, kNaN, 4, 5}, 2),
                std::vector<double>{kNaN, 1.5, kNaN, kNaN, 4.5});
  // A missing value invalidates a whole window only; windows after it recover.
  expect_series(rolling1(qc::kernels::rolling_mean,
                         std::vector<double>{1, 2, kNaN, 4, 5, 6}, 2),
                std::vector<double>{kNaN, 1.5, kNaN, kNaN, 4.5, 5.5});
  // Parameter validation.
  const std::vector<double> tiny = {1, 2};
  std::vector<double> out(2, kNaN);
  CHECK_THROWS_AS(qc::kernels::rolling_sum(tiny.data(), 2, 0, out.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::rolling_mean(nullptr, 2, 2, out.data()), std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::rolling_mean(tiny.data(), 2, 2, nullptr), std::invalid_argument);
  CHECK_NOTHROW(qc::kernels::rolling_mean(nullptr, 0, 2, nullptr));  // n == 0 is a no-op
}

TEST_CASE("corr/cov edge cases", "[kernels][rolling]") {
  const std::vector<double> x = {1, 2, 3, 4, 5};
  const std::vector<double> constant = {7, 7, 7, 7, 7};
  expect_all_nan(rolling2(qc::kernels::rolling_corr, x, constant, 2));
  expect_series(rolling2(qc::kernels::rolling_cov, x, constant, 2),
                std::vector<double>{kNaN, 0, 0, 0, 0});
  const std::vector<double> corr_expected = rolling2(qc::kernels::rolling_corr, x, x, 3);
  expect_series(corr_expected, std::vector<double>{kNaN, kNaN, 1, 1, 1});
}

TEST_CASE("cross-sectional kernels match fixed reference values", "[kernels][cross]") {
  const std::vector<double> x = {3, 1, 2, kNaN, 2, 10};
  const std::vector<double> cross_rank = {0.75, 0.0, 0.375, kNaN, 0.375, 1.0};
  const std::vector<double> cross_zscore = {-0.16452254913212455, -0.71293104623920633, -0.43872679768566542, kNaN, -0.43872679768566542, 1.7549071907426617};
  const std::vector<double> cross_mad_winsor3 = {3.0, 1.0, 2.0, kNaN, 2.0, 5.0};
  const std::vector<double> cross_quantile4 = {2.0, 0.0, 1.0, kNaN, 1.0, 3.0};
  const std::vector<double> cross_quantile5_1to10 = {0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0};
  std::vector<double> out(x.size(), kNaN);
  qc::kernels::cross_rank(x.data(), x.size(), out.data());
  expect_series(out, cross_rank);
  qc::kernels::cross_zscore(x.data(), x.size(), out.data());
  expect_series(out, cross_zscore);
  qc::kernels::cross_mad_winsor(x.data(), x.size(), 3.0, out.data());
  expect_series(out, cross_mad_winsor3);
  qc::kernels::cross_quantile(x.data(), x.size(), 0, 4, out.data());
  expect_series(out, cross_quantile4);
  const std::vector<double> d = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
  std::vector<double> dout(d.size(), kNaN);
  qc::kernels::cross_quantile(d.data(), d.size(), 0, 5, dout.data());
  expect_series(dout, cross_quantile5_1to10);
  // NaN stays NaN; a single valid name is neutral; all-NaN input stays NaN.
  expect_all_nan([] {
    std::vector<double> all_nan(4, kNaN);
    std::vector<double> out(4, kNaN);
    qc::kernels::cross_zscore(all_nan.data(), all_nan.size(), out.data());
    return out;
  }());
  const std::vector<double> single = {kNaN, 5, kNaN};
  std::vector<double> single_out(3, kNaN);
  qc::kernels::cross_rank(single.data(), 3, single_out.data());
  CHECK(std::isnan(single_out[0]));
  CHECK(single_out[1] == 0.5);
  qc::kernels::cross_zscore(single.data(), 3, single_out.data());
  CHECK(std::isnan(single_out[1]));
  qc::kernels::cross_quantile(single.data(), 3, 0, 10, single_out.data());
  CHECK(single_out[1] == 0.0);
  // Degenerate cross-sections.
  const std::vector<double> identical = {2, 2, 2, 2};
  std::vector<double> identical_out(4, kNaN);
  qc::kernels::cross_zscore(identical.data(), 4, identical_out.data());
  expect_all_nan(identical_out);
  qc::kernels::cross_mad_winsor(identical.data(), 4, 3.0, identical_out.data());
  expect_series(identical_out, std::vector<double>{2, 2, 2, 2});
  // Parameter validation.
  CHECK_THROWS_AS(qc::kernels::cross_mad_winsor(x.data(), 6, 0.0, out.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::cross_quantile(x.data(), 6, 0, 0, out.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::cross_quantile(x.data(), 6, -1, 4, out.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::cross_quantile(x.data(), 6, 4, 4, out.data()),
                  std::invalid_argument);
}

TEST_CASE("technical indicators match fixed reference values", "[kernels][indicators]") {
  const std::vector<double> close = {10, 11, 12, 11, 10, 11, 12, 13, 12, 11, 10, 11};
  const std::vector<double> high = {10.5, 11.5, 12.5, 11.5, 10.5, 11.5,
                                    12.5, 13.5, 12.5, 11.5, 10.5, 11.5};
  const std::vector<double> low = {9.5, 10.5, 11.5, 10.5, 9.5, 10.5,
                                   11.5, 12.5, 11.5, 10.5, 9.5, 10.5};
  const std::vector<double> volume = {100, 200, 300, 400, 500, 600,
                                      700, 800, 900, 1000, 1100, 1200};
  const std::size_t n = close.size();
  const std::vector<double> ma3 = {kNaN, kNaN, 11.0, 11.333333333333334, 11.0, 10.666666666666666, 11.0, 12.0, 12.333333333333334, 12.0, 11.0, 10.666666666666666};
  const std::vector<double> ema3 = {10.0, 10.5, 11.25, 11.125, 10.5625, 10.78125, 11.390625, 12.1953125, 12.09765625, 11.548828125, 10.7744140625, 10.88720703125};
  const std::vector<double> macd_dif_3_5_2 = {0.0, 0.16666666666666607, 0.36111111111111072, 0.1990740740740744, -0.054783950617283139, 0.036394032921810648, 0.22738768861453984, 0.4198209590763593, 0.2473285560509062, -0.018057004299395274, -0.27017602369959626, -0.14251969288306476};
  const std::vector<double> macd_dea_3_5_2 = {0.0, 0.11111111111111072, 0.27777777777777735, 0.22530864197530873, 0.038580246913580807, 0.03712277091906737, 0.16396604938271567, 0.3345359891784781, 0.27639770042676348, 0.080094563942657654, -0.1534191611521783, -0.14615284897276928};
  const std::vector<double> macd_hist_3_5_2 = {0.0, 0.055555555555555358, 0.08333333333333337, -0.026234567901234324, -0.093364197530863946, -0.00072873799725672178, 0.063421639231824173, 0.085284969897881202, -0.029069144375857281, -0.098151568242052928, -0.11675686254741796, 0.0036331560897045201};
  const std::vector<double> rsi3 = {kNaN, kNaN, kNaN, 66.666666666666657, 44.444444444444443, 62.962962962962962, 75.308641975308646, 83.539094650205769, 55.692729766803843, 37.128486511202567, 24.752324340801707, 49.834882893867807};
  const std::vector<double> kdj_k = {kNaN, kNaN, 61.111111111111114, 49.074074074074076, 38.271604938271608, 50.514403292181072, 61.454046639231827, 68.747142203932327, 54.164761469288223, 41.665396535081044, 33.33248657894292, 47.22165771929528};
  const std::vector<double> kdj_d = {kNaN, kNaN, 53.703703703703709, 52.160493827160501, 47.530864197530875, 48.525377229080945, 52.834933699131241, 58.139003200731608, 56.814255956917151, 51.764636149638456, 45.620586292739951, 46.154276768258399};
  const std::vector<double> kdj_j = {kNaN, kNaN, 75.925925925925924, 42.901234567901227, 19.753086419753075, 54.492455418381326, 78.692272519433004, 89.963420210333766, 48.865772494030367, 21.46691730596622, 8.7562871513488574, 49.356419621369042};
  const std::vector<double> boll_mid4 = {kNaN, kNaN, kNaN, 11.0, 11.0, 11.0, 11.0, 11.5, 12.0, 12.0, 11.5, 11.0};
  const std::vector<double> boll_upper4 = {kNaN, kNaN, kNaN, 12.632993161855453, 12.632993161855453, 12.632993161855453, 12.632993161855453, 14.081988897471611, 13.632993161855453, 13.632993161855453, 14.081988897471611, 12.632993161855453};
  const std::vector<double> boll_lower4 = {kNaN, kNaN, kNaN, 9.3670068381445475, 9.3670068381445475, 9.3670068381445475, 9.3670068381445475, 8.9180111025283892, 10.367006838144547, 10.367006838144547, 8.9180111025283892, 9.3670068381445475};
  const std::vector<double> atr3 = {kNaN, kNaN, kNaN, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5};
  const std::vector<double> obv = {0.0, 200.0, 500.0, 100.0, -400.0, 200.0, 900.0, 1700.0, 800.0, -200.0, -1300.0, -100.0};
  const std::vector<double> cci4 = {kNaN, kNaN, kNaN, 0.0, -133.33333333333334, 0.0, 133.33333333333334, 100.0, 0.0, -133.33333333333334, -100.0, 0.0};
  std::vector<double> a(n, kNaN), b(n, kNaN), c(n, kNaN);
  qc::kernels::ma(close.data(), n, 3, a.data());
  expect_series(a, ma3);
  qc::kernels::ema(close.data(), n, 3, a.data());
  expect_series(a, ema3);
  qc::kernels::macd(close.data(), n, 3, 5, 2, a.data(), b.data(), c.data());
  expect_series(a, macd_dif_3_5_2);
  expect_series(b, macd_dea_3_5_2);
  expect_series(c, macd_hist_3_5_2);
  qc::kernels::rsi(close.data(), n, 3, a.data());
  expect_series(a, rsi3);
  qc::kernels::kdj(high.data(), low.data(), close.data(), n, 3, 3, 3, a.data(), b.data(),
                   c.data());
  expect_series(a, kdj_k);
  expect_series(b, kdj_d);
  expect_series(c, kdj_j);
  qc::kernels::boll(close.data(), n, 4, 2.0, a.data(), b.data(), c.data());
  expect_series(a, boll_mid4);
  expect_series(b, boll_upper4);
  expect_series(c, boll_lower4);
  qc::kernels::atr(high.data(), low.data(), close.data(), n, 3, a.data());
  expect_series(a, atr3);
  qc::kernels::obv(close.data(), volume.data(), n, a.data());
  expect_series(a, obv);
  qc::kernels::cci(high.data(), low.data(), close.data(), n, 4, a.data());
  expect_series(a, cci4);
}

TEST_CASE("indicator missing values and parameter semantics", "[kernels][indicators]") {
  std::vector<double> out(6, kNaN);
  qc::kernels::ema(std::vector<double>{1, kNaN, 4}.data(), 3, 3, out.data());
  CHECK(out[0] == 1.0);
  CHECK(std::isnan(out[1]));
  CHECK(out[2] == Catch::Approx(2.5).margin(1e-15));  // state resumes after the gap
  const std::vector<double> flat = {5, 5, 5, 5};
  qc::kernels::rsi(flat.data(), 4, 3, out.data());
  CHECK(std::isnan(out[0]));
  CHECK(std::isnan(out[2]));
  CHECK(out[3] == 50.0);  // flat window is neutral
  const std::vector<double> up = {1, 2, 3, 4, 5};
  qc::kernels::rsi(up.data(), up.size(), 3, out.data());
  CHECK(out[4] == 100.0);  // no losses
  const std::vector<double> down = {5, 4, 3, 2, 1};
  qc::kernels::rsi(down.data(), down.size(), 3, out.data());
  CHECK(out[4] == 0.0);
  // BOLL window 1: middle band is defined, std bands are not.
  std::vector<double> mid(4, kNaN), upper(4, kNaN), lower(4, kNaN);
  qc::kernels::boll(flat.data(), 4, 1, 2.0, mid.data(), upper.data(), lower.data());
  CHECK(mid[0] == 5.0);
  CHECK(std::isnan(upper[0]));
  CHECK(std::isnan(lower[0]));
  // Short series and invalid parameters.
  CHECK_THROWS_AS(qc::kernels::rsi(up.data(), 5, 0, out.data()), std::invalid_argument);
  std::vector<double> macd_out(5, kNaN);
  CHECK_THROWS_AS(
      qc::kernels::macd(up.data(), 5, 0, 5, 2, macd_out.data(), macd_out.data(), macd_out.data()),
      std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::boll(up.data(), 5, 2, -1.0, macd_out.data(), macd_out.data(),
                                    macd_out.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::ma(up.data(), 5, 0, macd_out.data()), std::invalid_argument);
}

TEST_CASE("panel wrappers flatten rolling and cross-sectional kernels", "[kernels][panel_ops]") {
  const TempFile file{temp_path("ops")};
  const std::vector<qc::Date> dates = {20200102, 20200103, 20200106, 20200107, 20200108};
  std::vector<qc::Security> secs(2);
  secs[0] = {"A", "600000", "A", 0, 20000101, 0};
  secs[1] = {"B", "000001", "B", 0, 20000101, 0};
  std::vector<double> st(2 * dates.size());
  for (std::size_t s = 0; s < 2; ++s) {
    for (std::size_t t = 0; t < dates.size(); ++t) {
      st[s * dates.size() + t] = static_cast<double>(1 + s + t);
    }
  }
  {
    qc::PanelWriter writer(secs.size(), dates.size(), dates, secs);
    writer.add_field("close", qc::Layout::SecTime, st.data());
    writer.write(file.path);
  }
  const qc::Panel panel = qc::Panel::open(file.path);
  std::vector<double> out;
  qc::kernels::rolling_panel(panel, "close", 2, "mean", out, qc::Layout::SecTime);
  REQUIRE(out.size() == st.size());
  expect_series(out, std::vector<double>{kNaN, 1.5, 2.5, 3.5, 4.5, kNaN, 2.5, 3.5, 4.5, 5.5});
  std::vector<double> out_ts;
  qc::kernels::rolling_panel(panel, "close", 2, "mean", out_ts, qc::Layout::TimeSec);
  REQUIRE(out_ts.size() == st.size());
  // TimeSec order: out_ts[t * n_sec + s].
  CHECK(std::isnan(out_ts[0]));
  CHECK(std::isnan(out_ts[1]));
  CHECK(out_ts[1 * 2 + 0] == 1.5);
  CHECK(out_ts[1 * 2 + 1] == 2.5);
  CHECK(out_ts[4 * 2 + 1] == 5.5);
  qc::kernels::cross_panel(panel, "close", "rank", out, qc::Layout::SecTime);
  REQUIRE(out.size() == st.size());
  expect_series(out, std::vector<double>{0, 0, 0, 0, 0, 1, 1, 1, 1, 1});
  qc::kernels::cross_panel(panel, "close", "zscore", out, qc::Layout::SecTime);
  for (const double value : out) CHECK(std::isfinite(value));
  CHECK_THROWS_AS(qc::kernels::rolling_panel(panel, "nope", 2, "mean", out, qc::Layout::SecTime),
                  std::runtime_error);
  CHECK_THROWS_AS(qc::kernels::rolling_panel(panel, "close", 2, "corr", out, qc::Layout::SecTime),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::cross_panel(panel, "close", "nope", out, qc::Layout::SecTime),
                  std::invalid_argument);
  CHECK_THROWS_AS(qc::kernels::rolling_panel(panel, "close", 0, "mean", out, qc::Layout::SecTime),
                  std::invalid_argument);
}
