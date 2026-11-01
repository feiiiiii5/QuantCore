#pragma once
// Internal representation of the qcore factor-expression DSL.
// Tokenizer -> recursive-descent parser -> canonical DAG (CSE) -> evaluator.
// This header is private to cpp/src/expr and is not installed.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "qcore/panel.h"

// Evaluation contract (kept here so C++ and Python stay in sync):
// - NaN means "missing" and propagates: any NaN operand makes the result NaN, including
//   comparisons and and/or/not (whose finite outputs are exactly 1.0/0.0).
// - Truthiness for and/or/not is `value != 0`; division by zero is NaN (qc::safe_div);
//   log(x<=0), sqrt(x<0), pow(0,negative) and pow(negative, non-integer) are NaN.
// - Any non-finite result (overflow to +/-inf) is normalised to NaN.
// - Rolling ts_*(x, n): the whole window [t-n+1, t] must exist and be NaN-free, otherwise
//   NaN. ts_std is the sample std (ddof=1, n>=2). ts_rank is the percentile in [0,1] of
//   x[t] within the window with average tie ranks.
// - delay(x, n) = x[t-n] for t >= n, else NaN; n is a non-negative literal.
// - rank/zscore are cross-sectional over the non-NaN securities at the same t. rank is
//   (average_rank-1)/(m-1) in [0,1] (m = number of valid values); zscore uses the sample
//   std. m < 2 or zero dispersion yields NaN for the affected securities.
// - Field reads never touch t' > t and (sec, time) outside the panel yields NaN.

namespace qc::expr {

// Hard input limits so a hostile expression cannot exhaust the stack or allocate an
// unbounded rolling buffer.
constexpr size_t kMaxSourceLength = 65536;
constexpr int kMaxDepth = 256;
constexpr int kMaxWindow = 5000;

enum class TokenKind : uint8_t {
  End,
  Number,
  Identifier,
  LParen,
  RParen,
  Comma,
  Plus,
  Minus,
  Star,
  Slash,
  Lt,
  Le,
  Gt,
  Ge,
  Eq,
  Ne,
  And,
  Or,
  Not,
};

struct Token {
  TokenKind kind = TokenKind::End;
  std::string text;  // identifier spelling, number spelling or operator text
  double number = 0.0;
  size_t pos = 0;  // 0-based byte offset in the source
};

// Throws std::invalid_argument (message contains a 1-based position) on bad input.
std::vector<Token> tokenize(const std::string& source);

// Human-readable description used in parser error messages.
std::string token_desc(const Token& token);

enum class Op : uint8_t {
  Number,
  Field,
  Add,
  Sub,
  Mul,
  Div,
  Pow,
  Lt,
  Le,
  Gt,
  Ge,
  Eq,
  Ne,
  And,
  Or,
  Not,
  Neg,
  Abs,
  Log,
  Sqrt,
  Min,
  Max,
  TsMean,
  TsStd,
  TsSum,
  TsMin,
  TsMax,
  TsRank,
  Delay,
  Rank,
  ZScore,
};

// Cross-sectional operators (rank/zscore) need the whole time slice, not one point.
bool is_cross_sectional(Op op);
// Time-series window operators taking (value, integer window) arguments.
bool is_rolling(Op op);
const char* op_name(Op op);

struct Node {
  Op op = Op::Number;
  double number = 0.0;  // literal payload for Op::Number
  int arg = 0;          // field index (Op::Field) or window size (rolling/Delay)
  std::vector<int> kids;
  std::string key;  // canonical common-subexpression key
};

struct Program {
  std::string source;
  std::vector<Node> nodes;  // topological order: children always precede parents
  std::vector<std::string> field_names;
  int root = -1;
  bool has_cross = false;
};

// Parse + build the CSE-shared DAG. Throws std::invalid_argument on invalid input.
Program compile(const std::string& source);

// Multi-line readable AST/DAG summary. First lines are "source: ...", "nodes: N",
// "cross_sectional: ...", "ops: ..."; the DAG is listed topologically with #ids.
std::string explain(const Program& program);

// Value of the expression for one security/time. Returns NaN when sec/time are out of
// bounds or a rolling window is not fully covered. Throws std::invalid_argument when a
// referenced field is missing from the panel.
double eval_point(const Program& program, const Panel& panel, size_t sec, size_t time);

// Same result as eval_point, but evaluates the whole cross-section at `time` and picks
// `sec`: cross-sectional operators (rank/zscore) are cheap to add this way.
double eval_cross_point(const Program& program, const Panel& panel, size_t sec, size_t time);

// Evaluate the whole panel into `out`, a row-major (C-order) buffer of n_sec*n_time
// doubles in the requested layout. Used by the Python `evaluate_panel` helper.
void eval_panel_values(const Program& program, const Panel& panel, Layout layout, double* out);

}  // namespace qc::expr
