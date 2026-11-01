#include <catch2/catch_test_macros.hpp>

#include <stdexcept>
#include <string>

#include "qcore/expr.h"

namespace {

void require_invalid(const std::string& source, const std::string& expected_fragment) {
  bool threw = false;
  try {
    const qc::Expression expression = qc::Expression::parse(source);
    (void)expression;
  } catch (const std::invalid_argument& error) {
    threw = true;
    const std::string message = error.what();
    REQUIRE(message.find("position") != std::string::npos);
    REQUIRE(message.find(expected_fragment) != std::string::npos);
  }
  REQUIRE(threw);
}

}  // namespace

TEST_CASE("expression source round-trip and explain summary", "[expr][parse]") {
  const std::string source = "rank(ts_mean(close, 5) / ts_mean(close, 20))";
  const qc::Expression expression = qc::Expression::parse(source);
  REQUIRE(expression.source() == source);

  const std::string summary = expression.explain();
  REQUIRE(summary.find("source: " + source) != std::string::npos);
  REQUIRE(summary.find("nodes: 7") != std::string::npos);
  REQUIRE(summary.find("cross_sectional: true") != std::string::npos);
  REQUIRE(summary.find("ts_mean") != std::string::npos);
  REQUIRE(summary.find("rank") != std::string::npos);
  REQUIRE(summary.find("[root]") != std::string::npos);

  const qc::Expression plain = qc::Expression::parse("close");
  REQUIRE(plain.explain().find("cross_sectional: false") != std::string::npos);
}

TEST_CASE("default expression is empty", "[expr][parse]") {
  const qc::Expression expression;
  REQUIRE(expression.source().empty());
  const std::string summary = expression.explain();
  REQUIRE(summary.find("nodes: 0") != std::string::npos);
  REQUIRE(summary.find("<empty>") != std::string::npos);
}

TEST_CASE("logical and comparison spelling variants parse", "[expr][parse]") {
  const qc::Expression wordy =
      qc::Expression::parse("not (close > open and volume > 0) or amount <= 0");
  REQUIRE(wordy.explain().find("cross_sectional: false") != std::string::npos);

  const qc::Expression symbolic =
      qc::Expression::parse("!(close > open && volume > 0) || amount <= 0");
  REQUIRE(symbolic.source() == "!(close > open && volume > 0) || amount <= 0");

  const qc::Expression unary = qc::Expression::parse("-close + +open");
  REQUIRE(unary.source() == "-close + +open");
}

TEST_CASE("common subexpressions share DAG nodes", "[expr][cse]") {
  // A repeated field is one node used twice.
  const std::string repeated = qc::Expression::parse("close / close").explain();
  REQUIRE(repeated.find("nodes: 2") != std::string::npos);
  REQUIRE(repeated.find("uses=2") != std::string::npos);

  // A repeated rolling sub-expression is shared as well.
  const std::string rolling =
      qc::Expression::parse("ts_mean(close, 5) / ts_mean(close, 5)").explain();
  REQUIRE(rolling.find("nodes: 4") != std::string::npos);
  REQUIRE(rolling.find("uses=2") != std::string::npos);

  // Two different windows share the field and the window-independent structure.
  const std::string windows =
      qc::Expression::parse("ts_mean(close, 5) / ts_mean(close, 20)").explain();
  REQUIRE(windows.find("nodes: 6") != std::string::npos);

  // Commutative operands are normalised: min(close, open) and min(open, close) collapse.
  const std::string commutative =
      qc::Expression::parse("min(close, open) + min(open, close)").explain();
  REQUIRE(commutative.find("nodes: 4") != std::string::npos);
  REQUIRE(commutative.find("uses=2") != std::string::npos);

  // Constant literals are interned too: 1 + 2 + 1 has two number nodes.
  const std::string constants = qc::Expression::parse("1 + 2 + 1").explain();
  REQUIRE(constants.find("nodes: 4") != std::string::npos);
}

TEST_CASE("invalid expressions throw std::invalid_argument with a position", "[expr][parse]") {
  require_invalid("", "empty expression");
  require_invalid("   ", "empty expression");
  require_invalid("1 +", "unexpected end of expression");
  require_invalid("close +", "unexpected end of expression");
  require_invalid("(close", "expected ')'");
  require_invalid("ts_mean(close)", "ts_mean expects 2 arguments, got 1");
  require_invalid("ts_mean(close, 5, 6)", "ts_mean expects 2 arguments, got 3");
  require_invalid("abs(close, open)", "abs expects 1 argument, got 2");
  require_invalid("ts_mean(close, 0)", "ts_mean window must be in [1, 5000]");
  require_invalid("ts_mean(close, 5001)", "ts_mean window must be in [1, 5000]");
  require_invalid("ts_mean(close, 2.5)", "ts_mean window must be an integer literal");
  require_invalid("ts_mean(close, 1 + 1)", "ts_mean window must be an integer literal");
  require_invalid("delay(close, -1)", "delay window must be an integer literal");
  require_invalid("ts_mean(close, 1e999)", "number literal out of range");
  require_invalid("foo(close)", "unknown function 'foo'");
  require_invalid("ts_mean + 1", "must be called with arguments");
  require_invalid("mystery + 1", "unknown identifier 'mystery'");
  require_invalid("close @ 2", "unexpected character '@'");
  require_invalid("close > 1 > 2", "chained comparisons are not supported");
  require_invalid("1 = 2", "use '==' for equality");
  require_invalid("close & open", "use '&&' or 'and'");
  require_invalid("close | open", "use '||' or 'or'");
  require_invalid("1e", "malformed number literal");
  require_invalid("close 5", "unexpected number '5'");
  require_invalid("min(close)", "min expects 2 arguments, got 1");
  require_invalid("pow(close)", "pow expects 2 arguments, got 1");
}

TEST_CASE("parser rejects pathologically deep or long input", "[expr][parse][limits]") {
  std::string deep;
  for (int i = 0; i < 300; ++i) deep += "(";
  deep += "close";
  for (int i = 0; i < 300; ++i) deep += ")";
  require_invalid(deep, "nesting too deep");

  const std::string huge(70000, '1');
  require_invalid(huge, "longer than 65536");
}
