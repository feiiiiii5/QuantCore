#include "expr_internal.h"

#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace qc::expr {
namespace {

std::string format_double(double value) {
  if (value == 0.0) return "0";  // also normalises -0
  char buffer[40];
  for (int precision = 15; precision <= 17; ++precision) {
    std::snprintf(buffer, sizeof(buffer), "%.*g", precision, value);
    if (std::strtod(buffer, nullptr) == value) return buffer;
  }
  std::snprintf(buffer, sizeof(buffer), "%.17g", value);
  return buffer;
}

std::string id_ref(int id) { return "#" + std::to_string(id); }

const char* binary_symbol(Op op) {
  switch (op) {
    case Op::Add: return "+";
    case Op::Sub: return "-";
    case Op::Mul: return "*";
    case Op::Div: return "/";
    case Op::Lt: return "<";
    case Op::Le: return "<=";
    case Op::Gt: return ">";
    case Op::Ge: return ">=";
    case Op::Eq: return "==";
    case Op::Ne: return "!=";
    default: return nullptr;
  }
}

std::string format_node(const Program& program, size_t id) {
  const Node& node = program.nodes[id];
  switch (node.op) {
    case Op::Number:
      return format_double(node.number);
    case Op::Field:
      return program.field_names[static_cast<size_t>(node.arg)];
    case Op::Not:
      return "(not " + id_ref(node.kids[0]) + ")";
    case Op::Neg:
      return "(-" + id_ref(node.kids[0]) + ")";
    default:
      break;
  }
  if (node.kids.size() == 2) {
    if (const char* symbol = binary_symbol(node.op); symbol != nullptr) {
      return "(" + id_ref(node.kids[0]) + " " + symbol + " " + id_ref(node.kids[1]) + ")";
    }
    if (node.op == Op::And) {
      return "(" + id_ref(node.kids[0]) + " and " + id_ref(node.kids[1]) + ")";
    }
    if (node.op == Op::Or) {
      return "(" + id_ref(node.kids[0]) + " or " + id_ref(node.kids[1]) + ")";
    }
  }
  std::string text = op_name(node.op);
  text += '(';
  for (size_t i = 0; i < node.kids.size(); ++i) {
    if (i != 0) text += ", ";
    text += id_ref(node.kids[i]);
  }
  if (is_rolling(node.op) || node.op == Op::Delay) {
    if (!node.kids.empty()) text += ", ";
    text += std::to_string(node.arg);
  }
  text += ')';
  return text;
}

}  // namespace

std::string explain(const Program& program) {
  std::string out;
  out += "source: " + (program.source.empty() ? std::string("<empty>") : program.source) + "\n";
  out += "nodes: " + std::to_string(program.nodes.size()) + "\n";
  out += std::string("cross_sectional: ") + (program.has_cross ? "true" : "false") + "\n";
  if (program.root < 0 || program.nodes.empty()) {
    out += "ops: <empty>\n";
    out += "dag: <empty>\n";
    return out;
  }
  std::vector<std::string> ops;
  for (const Node& node : program.nodes) {
    const std::string name = op_name(node.op);
    if (std::find(ops.begin(), ops.end(), name) == ops.end()) ops.push_back(name);
  }
  out += "ops: ";
  for (size_t i = 0; i < ops.size(); ++i) {
    if (i != 0) out += ", ";
    out += ops[i];
  }
  out += "\n";
  std::vector<size_t> uses(program.nodes.size(), 0);
  for (const Node& node : program.nodes) {
    for (const int kid : node.kids) ++uses[static_cast<size_t>(kid)];
  }
  ++uses[static_cast<size_t>(program.root)];
  out += "dag:\n";
  for (size_t i = 0; i < program.nodes.size(); ++i) {
    out += "  #" + std::to_string(i) + " " + format_node(program, i);
    if (i == static_cast<size_t>(program.root)) {
      out += " [root]";
    } else if (uses[i] > 1) {
      out += " [uses=" + std::to_string(uses[i]) + "]";
    }
    out += "\n";
  }
  return out;
}

}  // namespace qc::expr
