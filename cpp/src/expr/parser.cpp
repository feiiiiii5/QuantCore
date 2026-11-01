#include "expr_internal.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace qc::expr {

bool is_cross_sectional(Op op) {
  return op == Op::Rank || op == Op::ZScore;
}

bool is_rolling(Op op) {
  switch (op) {
    case Op::TsMean:
    case Op::TsStd:
    case Op::TsSum:
    case Op::TsMin:
    case Op::TsMax:
    case Op::TsRank:
      return true;
    default:
      return false;
  }
}

const char* op_name(Op op) {
  switch (op) {
    case Op::Number:
      return "num";
    case Op::Field:
      return "field";
    case Op::Add:
      return "add";
    case Op::Sub:
      return "sub";
    case Op::Mul:
      return "mul";
    case Op::Div:
      return "div";
    case Op::Pow:
      return "pow";
    case Op::Lt:
      return "lt";
    case Op::Le:
      return "le";
    case Op::Gt:
      return "gt";
    case Op::Ge:
      return "ge";
    case Op::Eq:
      return "eq";
    case Op::Ne:
      return "ne";
    case Op::And:
      return "and";
    case Op::Or:
      return "or";
    case Op::Not:
      return "not";
    case Op::Neg:
      return "neg";
    case Op::Abs:
      return "abs";
    case Op::Log:
      return "log";
    case Op::Sqrt:
      return "sqrt";
    case Op::Min:
      return "min";
    case Op::Max:
      return "max";
    case Op::TsMean:
      return "ts_mean";
    case Op::TsStd:
      return "ts_std";
    case Op::TsSum:
      return "ts_sum";
    case Op::TsMin:
      return "ts_min";
    case Op::TsMax:
      return "ts_max";
    case Op::TsRank:
      return "ts_rank";
    case Op::Delay:
      return "delay";
    case Op::Rank:
      return "rank";
    case Op::ZScore:
      return "zscore";
  }
  return "?";
}

namespace {

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

std::string number_key(double value) {
  unsigned long long bits = 0;
  static_assert(sizeof(bits) == sizeof(value), "double must be 64-bit");
  std::memcpy(&bits, &value, sizeof(bits));
  char buffer[24];
  std::snprintf(buffer, sizeof(buffer), "%016llx", bits);
  return std::string("num:") + buffer;
}

bool is_commutative(Op op) {
  switch (op) {
    case Op::Add:
    case Op::Mul:
    case Op::Eq:
    case Op::Ne:
    case Op::And:
    case Op::Or:
    case Op::Min:
    case Op::Max:
      return true;
    default:
      return false;
  }
}

bool is_field_name(const std::string& name) {
  return name == "open" || name == "high" || name == "low" || name == "close" || name == "volume" ||
         name == "amount" || name == "returns";
}

struct FunctionInfo {
  const char* name;
  Op op;
  int arity;
  bool window;
};

constexpr FunctionInfo kFunctions[] = {
    {"abs", Op::Abs, 1, false},       {"log", Op::Log, 1, false},
    {"sqrt", Op::Sqrt, 1, false},     {"rank", Op::Rank, 1, false},
    {"zscore", Op::ZScore, 1, false}, {"pow", Op::Pow, 2, false},
    {"min", Op::Min, 2, false},       {"max", Op::Max, 2, false},
    {"ts_mean", Op::TsMean, 2, true}, {"ts_std", Op::TsStd, 2, true},
    {"ts_sum", Op::TsSum, 2, true},   {"ts_min", Op::TsMin, 2, true},
    {"ts_max", Op::TsMax, 2, true},   {"ts_rank", Op::TsRank, 2, true},
    {"delay", Op::Delay, 2, true},
};

const FunctionInfo* lookup_function(const std::string& name) {
  for (const FunctionInfo& info : kFunctions) {
    if (name == info.name)
      return &info;
  }
  return nullptr;
}

// ---------------------------------------------------------------------------
// Parser: recursive descent with precedence
//   or        := and ('or' and)*
//   and       := not ('and' not)*
//   not       := 'not' not | comparison
//   comparison:= additive (('<'|'<='|'>'|'>='|'=='|'!=') additive)?
//   additive  := term (('+'|'-') term)*
//   term      := unary (('*'|'/') unary)*
//   unary     := ('-'|'+') unary | primary
//   primary   := number | field | function '(' args ')' | '(' or ')'
// ---------------------------------------------------------------------------
class Parser {
 public:
  Parser(std::string source, std::vector<Token> tokens)
      : source_(std::move(source)), tokens_(std::move(tokens)) {}

  Program run() {
    program_.source = source_;
    if (tokens_.size() <= 1)
      fail(0, "empty expression");
    const int root = parse_or();
    if (!at(TokenKind::End))
      fail(peek().pos, "unexpected " + token_desc(peek()));
    program_.root = root;
    return std::move(program_);
  }

 private:
  [[noreturn]] void fail(size_t pos, const std::string& message) const {
    throw std::invalid_argument("expression parse error at position " + std::to_string(pos + 1) +
                                ": " + message);
  }

  const Token& peek() const {
    return tokens_[pos_];
  }
  bool at(TokenKind kind) const {
    return tokens_[pos_].kind == kind;
  }
  bool accept(TokenKind kind) {
    if (!at(kind))
      return false;
    ++pos_;
    return true;
  }
  size_t advance() {
    const size_t pos = tokens_[pos_].pos;
    ++pos_;
    return pos;
  }
  void expect(TokenKind kind, const char* what) {
    if (!at(kind))
      fail(peek().pos, std::string("expected ") + what + ", got " + token_desc(peek()));
    ++pos_;
  }
  void enter(size_t pos) {
    if (++depth_ > kMaxDepth) {
      fail(pos, "expression nesting too deep (limit " + std::to_string(kMaxDepth) + ")");
    }
  }
  void leave() {
    --depth_;
  }

  int parse_or() {
    int lhs = parse_and();
    while (accept(TokenKind::Or)) {
      const int rhs = parse_and();
      lhs = make_binary(Op::Or, lhs, rhs);
    }
    return lhs;
  }

  int parse_and() {
    int lhs = parse_not();
    while (accept(TokenKind::And)) {
      const int rhs = parse_not();
      lhs = make_binary(Op::And, lhs, rhs);
    }
    return lhs;
  }

  int parse_not() {
    if (at(TokenKind::Not)) {
      const size_t pos = advance();
      enter(pos);
      const int kid = parse_not();
      leave();
      return make_unary(Op::Not, kid);
    }
    return parse_comparison();
  }

  int parse_comparison() {
    const int lhs = parse_additive();
    Op op;
    switch (peek().kind) {
      case TokenKind::Lt:
        op = Op::Lt;
        break;
      case TokenKind::Le:
        op = Op::Le;
        break;
      case TokenKind::Gt:
        op = Op::Gt;
        break;
      case TokenKind::Ge:
        op = Op::Ge;
        break;
      case TokenKind::Eq:
        op = Op::Eq;
        break;
      case TokenKind::Ne:
        op = Op::Ne;
        break;
      default:
        return lhs;
    }
    ++pos_;
    const int rhs = parse_additive();
    switch (peek().kind) {
      case TokenKind::Lt:
      case TokenKind::Le:
      case TokenKind::Gt:
      case TokenKind::Ge:
      case TokenKind::Eq:
      case TokenKind::Ne:
        fail(peek().pos, "chained comparisons are not supported; add parentheses");
      default:
        break;
    }
    return make_binary(op, lhs, rhs);
  }

  int parse_additive() {
    int lhs = parse_term();
    for (;;) {
      Op op;
      if (at(TokenKind::Plus)) {
        op = Op::Add;
      } else if (at(TokenKind::Minus)) {
        op = Op::Sub;
      } else {
        return lhs;
      }
      ++pos_;
      lhs = make_binary(op, lhs, parse_term());
    }
  }

  int parse_term() {
    int lhs = parse_unary();
    for (;;) {
      Op op;
      if (at(TokenKind::Star)) {
        op = Op::Mul;
      } else if (at(TokenKind::Slash)) {
        op = Op::Div;
      } else {
        return lhs;
      }
      ++pos_;
      lhs = make_binary(op, lhs, parse_unary());
    }
  }

  int parse_unary() {
    if (at(TokenKind::Minus) || at(TokenKind::Plus)) {
      const bool negate = at(TokenKind::Minus);
      const size_t pos = advance();
      enter(pos);
      int kid = parse_unary();
      leave();
      return negate ? make_unary(Op::Neg, kid) : kid;
    }
    return parse_primary();
  }

  int parse_primary() {
    switch (peek().kind) {
      case TokenKind::Number: {
        const double value = peek().number;
        ++pos_;
        return make_number(value);
      }
      case TokenKind::LParen: {
        const size_t pos = advance();
        enter(pos);
        const int inner = parse_or();
        leave();
        expect(TokenKind::RParen, "')'");
        return inner;
      }
      case TokenKind::Identifier:
        return parse_identifier();
      default:
        fail(peek().pos, "unexpected " + token_desc(peek()));
    }
  }

  int parse_identifier() {
    const std::string name = peek().text;
    const size_t pos = advance();
    const FunctionInfo* function = lookup_function(name);
    if (at(TokenKind::LParen)) {
      if (function == nullptr)
        fail(pos, "unknown function '" + name + "'");
      return parse_call(*function, pos);
    }
    if (function != nullptr) {
      fail(pos, "function '" + name + "' must be called with arguments, e.g. " + name + "(...)");
    }
    if (!is_field_name(name)) {
      fail(pos, "unknown identifier '" + name +
                    "'; expected a field (open/high/low/close/volume/amount/returns) or a "
                    "function call");
    }
    return make_field(name);
  }

  int parse_call(const FunctionInfo& function, size_t call_pos) {
    expect(TokenKind::LParen, "'('");
    enter(call_pos);
    std::vector<int> args;
    std::vector<size_t> arg_pos;
    if (!at(TokenKind::RParen)) {
      for (;;) {
        arg_pos.push_back(peek().pos);
        args.push_back(parse_or());
        if (!accept(TokenKind::Comma))
          break;
      }
    }
    leave();
    expect(TokenKind::RParen, "')'");
    const std::string name = function.name;
    const int got = static_cast<int>(args.size());
    if (got != function.arity) {
      fail(call_pos, name + " expects " + std::to_string(function.arity) +
                         (function.arity == 1 ? " argument" : " arguments") + ", got " +
                         std::to_string(got));
    }
    if (function.window)
      return make_window(function, args[0], args[1], arg_pos[1], name);
    if (got == 1)
      return make_unary(function.op, args[0]);
    return make_binary(function.op, args[0], args[1]);
  }

  int make_window(const FunctionInfo& function, int value_id, int window_id, size_t window_pos,
                  const std::string& name) {
    const Node& window_node = program_.nodes[static_cast<size_t>(window_id)];
    if (window_node.op != Op::Number) {
      fail(window_pos, name + " window must be an integer literal");
    }
    const double raw = window_node.number;
    if (!std::isfinite(raw) || raw != std::floor(raw)) {
      fail(window_pos, name + " window must be an integer literal");
    }
    const int lo = function.op == Op::Delay ? 0 : 1;
    if (raw < static_cast<double>(lo) || raw > static_cast<double>(kMaxWindow)) {
      fail(window_pos, name + " window must be in [" + std::to_string(lo) + ", " +
                           std::to_string(kMaxWindow) + "]");
    }
    return intern(function.op, {value_id}, 0.0, static_cast<int>(raw));
  }

  int make_number(double value) {
    return intern(Op::Number, {}, value, 0);
  }

  int make_field(const std::string& name) {
    auto it = field_index_.find(name);
    int index;
    if (it != field_index_.end()) {
      index = it->second;
    } else {
      index = static_cast<int>(program_.field_names.size());
      program_.field_names.push_back(name);
      field_index_.emplace(name, index);
    }
    return intern(Op::Field, {}, 0.0, index);
  }

  int make_unary(Op op, int kid) {
    return intern(op, {kid}, 0.0, 0);
  }
  int make_binary(Op op, int a, int b) {
    return intern(op, {a, b}, 0.0, 0);
  }

  // Canonical intern: a node is shared whenever its normalised key was seen before.
  int intern(Op op, std::vector<int> kids, double number, int arg) {
    // Commutative operands are normalised for the CSE key only; `kids` keeps source
    // order so explain() stays readable.
    std::vector<int> ordered = kids;
    if (is_commutative(op) && ordered.size() == 2) {
      std::sort(ordered.begin(), ordered.end(), [this](int a, int b) {
        return program_.nodes[static_cast<size_t>(a)].key <
               program_.nodes[static_cast<size_t>(b)].key;
      });
    }
    std::string key;
    switch (op) {
      case Op::Number:
        key = number_key(number);
        break;
      case Op::Field:
        key = "field:" + program_.field_names[static_cast<size_t>(arg)];
        break;
      default: {
        key = op_name(op);
        key += '(';
        for (size_t i = 0; i < ordered.size(); ++i) {
          if (i != 0)
            key += ',';
          key += program_.nodes[static_cast<size_t>(ordered[i])].key;
        }
        if (is_rolling(op) || op == Op::Delay) {
          key += ',';
          key += std::to_string(arg);
        }
        key += ')';
        break;
      }
    }
    const auto existing = cse_.find(key);
    if (existing != cse_.end())
      return existing->second;
    Node node;
    node.op = op;
    node.number = number;
    node.arg = arg;
    node.kids = std::move(kids);
    node.key = key;
    const int id = static_cast<int>(program_.nodes.size());
    program_.nodes.push_back(std::move(node));
    cse_.emplace(std::move(key), id);
    if (is_cross_sectional(op))
      program_.has_cross = true;
    return id;
  }

  std::string source_;
  std::vector<Token> tokens_;
  size_t pos_ = 0;
  int depth_ = 0;
  Program program_;
  std::unordered_map<std::string, int> field_index_;
  std::unordered_map<std::string, int> cse_;
};

}  // namespace

Program compile(const std::string& source) {
  if (source.size() > kMaxSourceLength) {
    throw std::invalid_argument("expression parse error at position " +
                                std::to_string(kMaxSourceLength + 1) + ": source is longer than " +
                                std::to_string(kMaxSourceLength) + " characters");
  }
  Parser parser(source, tokenize(source));
  return parser.run();
}

}  // namespace qc::expr
