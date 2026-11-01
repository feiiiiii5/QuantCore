#pragma once
// Minimal factor expression DSL: rank(ts_mean(close,5)/ts_mean(close,20)); compiled to a DAG.
#include <memory>
#include <string>
#include <vector>
#include "qcore/panel.h"

namespace qc {
class Expression {
 public:
  static Expression parse(const std::string& source);
  double eval(const Panel& panel, size_t sec, size_t time) const;
  double eval_cross(const Panel& panel, size_t sec, size_t time) const;
  const std::string& source() const;
  std::string explain() const;
  Expression();
  ~Expression();
  Expression(Expression&&) noexcept;
  Expression& operator=(Expression&&) noexcept;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace qc
