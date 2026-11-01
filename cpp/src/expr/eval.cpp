#include "expr_internal.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "qcore/expr.h"

namespace qc::expr {
namespace {

// ---------------------------------------------------------------------------
// Value helpers. NaN marks a missing value and propagates through every operator;
// non-finite results (overflow) are normalised to NaN so downstream ranks never see
// infinities. Division by zero is NaN, matching qc::safe_div.
// ---------------------------------------------------------------------------

double normalize(double value) {
  return std::isfinite(value) ? value : kNaN;
}

bool truthy(double value) {
  return value != 0.0;
}

double ranked_percentile(size_t less, size_t equal, size_t total) {
  const double offset = static_cast<double>(less) + 0.5 * static_cast<double>(equal - 1);
  return offset / static_cast<double>(total - 1);
}

// Average-rank percentile of every non-NaN entry in x; NaN entries stay NaN.
void cross_rank(const std::vector<double>& x, std::vector<double>& out) {
  out.assign(x.size(), kNaN);
  std::vector<size_t> order;
  order.reserve(x.size());
  for (size_t i = 0; i < x.size(); ++i) {
    if (!std::isnan(x[i]))
      order.push_back(i);
  }
  const size_t count = order.size();
  if (count < 2)
    return;
  std::sort(order.begin(), order.end(), [&x](size_t a, size_t b) {
    if (x[a] != x[b])
      return x[a] < x[b];
    return a < b;
  });
  size_t begin = 0;
  while (begin < count) {
    size_t end = begin;
    while (end + 1 < count && x[order[end + 1]] == x[order[begin]])
      ++end;
    const double percentile = ranked_percentile(begin, end - begin + 1, count);
    for (size_t i = begin; i <= end; ++i)
      out[order[i]] = percentile;
    begin = end + 1;
  }
}

// Cross-sectional z-score (sample std, ddof=1); NaN entries stay NaN.
void cross_zscore(const std::vector<double>& x, std::vector<double>& out) {
  out.assign(x.size(), kNaN);
  double sum = 0.0;
  size_t count = 0;
  for (const double value : x) {
    if (std::isnan(value))
      continue;
    sum += value;
    ++count;
  }
  if (count < 2)
    return;
  const double mean = sum / static_cast<double>(count);
  double sum_sq = 0.0;
  for (const double value : x) {
    if (std::isnan(value))
      continue;
    const double diff = value - mean;
    sum_sq += diff * diff;
  }
  const double stddev = std::sqrt(sum_sq / static_cast<double>(count - 1));
  if (!(stddev > 0.0) || !std::isfinite(stddev))
    return;
  for (size_t i = 0; i < x.size(); ++i) {
    if (!std::isnan(x[i]))
      out[i] = normalize((x[i] - mean) / stddev);
  }
}

// Scalar operators (NaN operands are filtered by the caller).
double op_add(double a, double b) {
  return a + b;
}
double op_sub(double a, double b) {
  return a - b;
}
double op_mul(double a, double b) {
  return a * b;
}
double op_div(double a, double b) {
  return b == 0.0 ? kNaN : a / b;
}
double op_pow(double a, double b) {
  if (a == 0.0 && b < 0.0)
    return kNaN;
  if (a < 0.0 && b != std::floor(b))
    return kNaN;
  return std::pow(a, b);
}
double op_min(double a, double b) {
  return std::min(a, b);
}
double op_max(double a, double b) {
  return std::max(a, b);
}
double op_lt(double a, double b) {
  return a < b ? 1.0 : 0.0;
}
double op_le(double a, double b) {
  return a <= b ? 1.0 : 0.0;
}
double op_gt(double a, double b) {
  return a > b ? 1.0 : 0.0;
}
double op_ge(double a, double b) {
  return a >= b ? 1.0 : 0.0;
}
double op_eq(double a, double b) {
  return a == b ? 1.0 : 0.0;
}
double op_ne(double a, double b) {
  return a != b ? 1.0 : 0.0;
}

struct ScalarKey {
  int node = 0;
  size_t sec = 0;
  size_t time = 0;
  bool operator==(const ScalarKey& other) const {
    return node == other.node && sec == other.sec && time == other.time;
  }
};

struct ScalarKeyHash {
  size_t operator()(const ScalarKey& key) const {
    size_t seed = std::hash<int>{}(key.node);
    seed ^= std::hash<size_t>{}(key.sec) + static_cast<size_t>(0x9e3779b97f4a7c15ULL) +
            (seed << 6) + (seed >> 2);
    seed ^= std::hash<size_t>{}(key.time) + static_cast<size_t>(0x9e3779b97f4a7c15ULL) +
            (seed << 6) + (seed >> 2);
    return seed;
  }
};

struct VectorKey {
  int node = 0;
  size_t time = 0;
  bool operator==(const VectorKey& other) const {
    return node == other.node && time == other.time;
  }
};

struct VectorKeyHash {
  size_t operator()(const VectorKey& key) const {
    size_t seed = std::hash<int>{}(key.node);
    seed ^= std::hash<size_t>{}(key.time) + static_cast<size_t>(0x9e3779b97f4a7c15ULL) +
            (seed << 6) + (seed >> 2);
    return seed;
  }
};

struct FieldSource {
  FieldView view{};
  FieldView close{};
  bool ready = false;
  bool derived_returns = false;
  bool close_ready = false;
};

// One evaluation pass: memoises scalar points and cross-sectional vectors so that a
// rolling window never re-evaluates a shared sub-expression exponentially.
class EvalContext {
 public:
  EvalContext(const Program& program, const Panel& panel)
      : program_(program),
        panel_(panel),
        n_sec_(panel.n_sec()),
        field_sources_(program.field_names.size()) {}

  double scalar(int id, size_t sec, size_t time) {
    const Node& node = program_.nodes[static_cast<size_t>(id)];
    if (is_cross_sectional(node.op)) {
      const std::vector<double>& values = vector(id, time);
      return sec < values.size() ? values[sec] : kNaN;
    }
    const ScalarKey key{id, sec, time};
    const auto existing = scalar_memo_.find(key);
    if (existing != scalar_memo_.end())
      return existing->second;
    const double value = eval_scalar(node, sec, time);
    scalar_memo_.emplace(key, value);
    return value;
  }

  // Whole cross-section of the root expression at `time` (indexed by security).
  const std::vector<double>& cross_section(size_t time) {
    return vector(program_.root, time);
  }

 private:
  const std::vector<double>& vector(int id, size_t time) {
    const VectorKey key{id, time};
    const auto existing = vector_memo_.find(key);
    if (existing != vector_memo_.end())
      return existing->second;
    const Node& node = program_.nodes[static_cast<size_t>(id)];
    std::vector<double> values(n_sec_, kNaN);
    if (is_cross_sectional(node.op)) {
      const std::vector<double>& input = vector(node.kids[0], time);
      if (node.op == Op::Rank) {
        cross_rank(input, values);
      } else {
        cross_zscore(input, values);
      }
    } else {
      for (size_t sec = 0; sec < n_sec_; ++sec)
        values[sec] = scalar(id, sec, time);
    }
    const auto inserted = vector_memo_.emplace(key, std::move(values));
    return inserted.first->second;
  }

  double binary(const Node& node, size_t sec, size_t time, double (*op)(double, double)) {
    const double a = scalar(node.kids[0], sec, time);
    const double b = scalar(node.kids[1], sec, time);
    if (std::isnan(a) || std::isnan(b))
      return kNaN;
    return normalize(op(a, b));
  }

  double eval_scalar(const Node& node, size_t sec, size_t time) {
    switch (node.op) {
      case Op::Number:
        return node.number;
      case Op::Field:
        return field_value(static_cast<size_t>(node.arg), sec, time);
      case Op::Add:
        return binary(node, sec, time, op_add);
      case Op::Sub:
        return binary(node, sec, time, op_sub);
      case Op::Mul:
        return binary(node, sec, time, op_mul);
      case Op::Div:
        return binary(node, sec, time, op_div);
      case Op::Pow:
        return binary(node, sec, time, op_pow);
      case Op::Min:
        return binary(node, sec, time, op_min);
      case Op::Max:
        return binary(node, sec, time, op_max);
      case Op::Lt:
        return binary(node, sec, time, op_lt);
      case Op::Le:
        return binary(node, sec, time, op_le);
      case Op::Gt:
        return binary(node, sec, time, op_gt);
      case Op::Ge:
        return binary(node, sec, time, op_ge);
      case Op::Eq:
        return binary(node, sec, time, op_eq);
      case Op::Ne:
        return binary(node, sec, time, op_ne);
      case Op::And: {
        const double a = scalar(node.kids[0], sec, time);
        const double b = scalar(node.kids[1], sec, time);
        if (std::isnan(a) || std::isnan(b))
          return kNaN;
        return truthy(a) && truthy(b) ? 1.0 : 0.0;
      }
      case Op::Or: {
        const double a = scalar(node.kids[0], sec, time);
        const double b = scalar(node.kids[1], sec, time);
        if (std::isnan(a) || std::isnan(b))
          return kNaN;
        return truthy(a) || truthy(b) ? 1.0 : 0.0;
      }
      case Op::Not: {
        const double value = scalar(node.kids[0], sec, time);
        if (std::isnan(value))
          return kNaN;
        return truthy(value) ? 0.0 : 1.0;
      }
      case Op::Neg: {
        const double value = scalar(node.kids[0], sec, time);
        return std::isnan(value) ? kNaN : normalize(-value);
      }
      case Op::Abs: {
        const double value = scalar(node.kids[0], sec, time);
        return std::isnan(value) ? kNaN : normalize(std::fabs(value));
      }
      case Op::Log: {
        const double value = scalar(node.kids[0], sec, time);
        if (std::isnan(value) || !(value > 0.0))
          return kNaN;
        return normalize(std::log(value));
      }
      case Op::Sqrt: {
        const double value = scalar(node.kids[0], sec, time);
        if (std::isnan(value) || value < 0.0)
          return kNaN;
        return normalize(std::sqrt(value));
      }
      case Op::Delay: {
        const size_t shift = static_cast<size_t>(node.arg);
        if (time < shift)
          return kNaN;
        return scalar(node.kids[0], sec, time - shift);
      }
      case Op::TsMean:
      case Op::TsStd:
      case Op::TsSum:
      case Op::TsMin:
      case Op::TsMax:
      case Op::TsRank:
        return rolling_value(node, sec, time);
      case Op::Rank:
      case Op::ZScore:
        return kNaN;  // unreachable: handled by scalar()
    }
    return kNaN;
  }

  // ts_*: the whole window must be inside the panel (no future data) and free of NaN.
  double rolling_value(const Node& node, size_t sec, size_t time) {
    const size_t window = static_cast<size_t>(node.arg);
    if (window == 0 || time + 1 < window)
      return kNaN;
    const size_t begin = time + 1 - window;
    std::vector<double> values(window);
    for (size_t i = 0; i < window; ++i) {
      const double value = scalar(node.kids[0], sec, begin + i);
      if (std::isnan(value))
        return kNaN;
      values[i] = value;
    }
    double sum = 0.0;
    for (const double value : values)
      sum += value;
    switch (node.op) {
      case Op::TsSum:
        return normalize(sum);
      case Op::TsMean:
        return normalize(sum / static_cast<double>(window));
      case Op::TsStd: {
        if (window < 2)
          return kNaN;
        const double mean = sum / static_cast<double>(window);
        double sum_sq = 0.0;
        for (const double value : values) {
          const double diff = value - mean;
          sum_sq += diff * diff;
        }
        const double variance = sum_sq / static_cast<double>(window - 1);
        return normalize(std::sqrt(variance > 0.0 ? variance : 0.0));
      }
      case Op::TsMin: {
        double result = values[0];
        for (size_t i = 1; i < window; ++i)
          result = std::min(result, values[i]);
        return result;
      }
      case Op::TsMax: {
        double result = values[0];
        for (size_t i = 1; i < window; ++i)
          result = std::max(result, values[i]);
        return result;
      }
      case Op::TsRank: {
        if (window < 2)
          return kNaN;
        const double last = values.back();
        size_t less = 0;
        size_t equal = 0;
        for (const double value : values) {
          if (value < last) {
            ++less;
          } else if (value == last) {
            ++equal;
          }
        }
        return ranked_percentile(less, equal, window);
      }
      default:
        return kNaN;
    }
  }

  double field_value(size_t index, size_t sec, size_t time) {
    FieldSource& source = field_sources_[index];
    if (!source.ready)
      resolve_field(source, index);
    if (!source.derived_returns)
      return normalize(source.view.at(sec, time));
    if (time == 0)
      return kNaN;
    if (!source.close_ready) {
      source.close = panel_.field("close");
      source.close_ready = true;
    }
    const double previous = normalize(source.close.at(sec, time - 1));
    const double current = normalize(source.close.at(sec, time));
    if (std::isnan(previous) || std::isnan(current) || previous == 0.0)
      return kNaN;
    return normalize(current / previous - 1.0);
  }

  void resolve_field(FieldSource& source, size_t index) {
    const std::string& name = program_.field_names[index];
    if (name == "returns" && !panel_.has_field("returns")) {
      // Convenience: derive simple returns from close when the snapshot has no
      // explicit returns column. Reads only time-1 and time, i.e. no future data.
      if (!panel_.has_field("close")) {
        throw std::invalid_argument(
            "expression eval error: field 'returns' is unavailable: panel has neither "
            "'returns' nor 'close'");
      }
      source.derived_returns = true;
      source.ready = true;
      return;
    }
    if (!panel_.has_field(name)) {
      throw std::invalid_argument("expression eval error: field '" + name + "' not found in panel");
    }
    source.view = panel_.field(name);
    source.ready = true;
  }

  const Program& program_;
  const Panel& panel_;
  size_t n_sec_;
  std::vector<FieldSource> field_sources_;
  std::unordered_map<ScalarKey, double, ScalarKeyHash> scalar_memo_;
  std::unordered_map<VectorKey, std::vector<double>, VectorKeyHash> vector_memo_;
};

}  // namespace

double eval_point(const Program& program, const Panel& panel, size_t sec, size_t time) {
  if (program.root < 0 || sec >= panel.n_sec() || time >= panel.n_time())
    return kNaN;
  EvalContext context(program, panel);
  return context.scalar(program.root, sec, time);
}

double eval_cross_point(const Program& program, const Panel& panel, size_t sec, size_t time) {
  if (program.root < 0 || sec >= panel.n_sec() || time >= panel.n_time())
    return kNaN;
  EvalContext context(program, panel);
  const std::vector<double>& values = context.cross_section(time);
  return values[sec];
}

void eval_panel_values(const Program& program, const Panel& panel, Layout layout, double* out) {
  const size_t n_sec = panel.n_sec();
  const size_t n_time = panel.n_time();
  for (size_t i = 0; i < n_sec * n_time; ++i)
    out[i] = kNaN;
  if (program.root < 0 || n_sec == 0 || n_time == 0)
    return;
  for (size_t time = 0; time < n_time; ++time) {
    // One context per time slice: memoisation removes exponential re-evaluation of
    // shared sub-expressions while scratch memory stays bounded by a single column
    // instead of the whole panel. (Rolling reductions are still O(window) per cell; the
    // incremental/panel-wide kernel path is a later optimisation.)
    EvalContext context(program, panel);
    const std::vector<double>& values = context.cross_section(time);
    if (layout == Layout::SecTime) {
      for (size_t sec = 0; sec < n_sec; ++sec)
        out[sec * n_time + time] = values[sec];
    } else {
      double* row = out + time * n_sec;
      for (size_t sec = 0; sec < n_sec; ++sec)
        row[sec] = values[sec];
    }
  }
}

}  // namespace qc::expr

namespace qc {

struct Expression::Impl {
  expr::Program program;
};

Expression::Expression() = default;
Expression::~Expression() = default;
Expression::Expression(Expression&&) noexcept = default;
Expression& Expression::operator=(Expression&&) noexcept = default;

Expression Expression::parse(const std::string& source) {
  Expression expression;
  expression.impl_ = std::make_unique<Impl>();
  expression.impl_->program = expr::compile(source);
  return expression;
}

double Expression::eval(const Panel& panel, size_t sec, size_t time) const {
  if (!impl_)
    return kNaN;
  return expr::eval_point(impl_->program, panel, sec, time);
}

double Expression::eval_cross(const Panel& panel, size_t sec, size_t time) const {
  if (!impl_)
    return kNaN;
  return expr::eval_cross_point(impl_->program, panel, sec, time);
}

const std::string& Expression::source() const {
  static const std::string kEmpty;
  return impl_ ? impl_->program.source : kEmpty;
}

std::string Expression::explain() const {
  if (!impl_) {
    return "source: <empty>\nnodes: 0\ncross_sectional: false\nops: <empty>\ndag: <empty>\n";
  }
  return expr::explain(impl_->program);
}

}  // namespace qc
