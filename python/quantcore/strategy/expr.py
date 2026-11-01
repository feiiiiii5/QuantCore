"""A small vectorised expression language used by declarative strategies.

Expressions operate on the ``(n_time, n_sec)`` matrices of a :class:`PanelView`; only
information visible in the view is accessible, so evaluation is lookahead-safe.  Example::

    ma(close, 20) > ma(close, 60) and rank(ret(close, 120)) > 0.8

Supported fields: any canonical bar field (``open/high/low/close/pre_close/volume/amount/
adj_factor/limit_up/limit_down/turnover/total_shares/float_shares/mktcap/float_mktcap/
suspended/st``).  Supported functions: ``ma, std, ret, shift, rank, zscore, abs, log,
sqrt, min, max``.  Supported operators: ``+ - * /``, comparisons, ``and/or/not``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import numpy as np

from ..errors import StrategyValidationError
from .base import PanelView

FIELDS: frozenset[str] = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "adj_factor",
        "limit_up",
        "limit_down",
        "suspended",
        "st",
        "turnover",
        "total_shares",
        "float_shares",
        "mktcap",
        "float_mktcap",
    }
)

#: function name -> number of arguments
FUNCTIONS: dict[str, int] = {
    "ma": 2,
    "std": 2,
    "ret": 2,
    "shift": 2,
    "ts_mean": 2,
    "ts_std": 2,
    "ts_sum": 2,
    "ts_min": 2,
    "ts_max": 2,
    "ts_rank": 2,
    "delay": 2,
    "rank": 1,
    "zscore": 1,
    "abs": 1,
    "log": 1,
    "sqrt": 1,
    "min": 2,
    "max": 2,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


@dataclass(frozen=True)
class CompiledExpression:
    source: str
    tree: ast.Expression
    referenced_fields: frozenset[str]

    def explain(self) -> dict[str, Any]:
        return {"source": self.source, "fields": sorted(self.referenced_fields)}


def _validate_node(node: ast.AST) -> None:
    if not isinstance(node, _ALLOWED_NODES):
        raise StrategyValidationError(f"unsupported expression construct: {type(node).__name__}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise StrategyValidationError(
                f"function not allowed: {ast.dump(node.func)}; allowed: {sorted(FUNCTIONS)}"
            )
        if len(node.args) != FUNCTIONS[node.func.id] or node.keywords:
            raise StrategyValidationError(
                f"{node.func.id}() expects {FUNCTIONS[node.func.id]} positional args"
            )
    if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
        raise StrategyValidationError(f"only numeric literals allowed, got {node.value!r}")
    if isinstance(node, ast.Name) and node.id not in FIELDS and node.id not in FUNCTIONS:
        raise StrategyValidationError(f"unknown identifier {node.id!r}; fields: {sorted(FIELDS)}")
    for child in ast.iter_child_nodes(node):
        _validate_node(child)


def _referenced_fields(tree: ast.AST) -> frozenset[str]:
    return frozenset(
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in FIELDS
    )


def compile_expression(source: str) -> CompiledExpression:
    """Parse and validate an expression string."""
    text = source.strip()
    if not text:
        raise StrategyValidationError("empty expression")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise StrategyValidationError(f"syntax error in expression {source!r}: {exc}") from exc
    _validate_node(tree)
    return CompiledExpression(source=text, tree=tree, referenced_fields=_referenced_fields(tree))


def _rolling(window: int, func: Any) -> Any:
    def apply(values: np.ndarray) -> np.ndarray:
        n_time, n_sec = values.shape
        out = np.full((n_time, n_sec), np.nan, dtype=np.float64)
        if window < 1 or window > n_time:
            return out
        windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            reduced = func(windows, axis=-1)
        out[window - 1 :] = reduced
        return out

    return apply


def _nanmean(windows: np.ndarray, axis: int) -> np.ndarray:
    counts = np.sum(~np.isnan(windows), axis=axis)
    totals = np.nansum(windows, axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        result = totals / counts
    result = np.where(counts > 0, result, np.nan)
    return result


def _nanstd(windows: np.ndarray, axis: int) -> np.ndarray:
    counts = np.sum(~np.isnan(windows), axis=axis)
    means = _nanmean(windows, axis)
    centered = windows - np.expand_dims(means, axis)
    with np.errstate(invalid="ignore"):
        variance = np.nansum(centered * centered, axis=axis) / np.maximum(counts - 1, 1)
    result = np.sqrt(variance)
    return np.where(counts > 1, result, np.nan)


def _rank_last(windows: np.ndarray, axis: int) -> np.ndarray:
    ranks = np.argsort(np.argsort(windows, axis=axis, kind="stable"), axis=axis, kind="stable")
    # argsort twice gives 0-based average-ish ordinal rank; convert to (rank-1)/(n-1).
    ordinal = ranks[..., -1].astype(np.float64)
    return ordinal / max(windows.shape[axis] - 1, 1)


def _cross_sectional_rank(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=np.float64)
    for row in range(values.shape[0]):
        line = values[row]
        valid = np.isfinite(line)
        count = int(valid.sum())
        if count == 0:
            continue
        ranks = np.argsort(np.argsort(line[valid], kind="stable"), kind="stable")
        out[row, valid] = (ranks + 1.0) / count
    return out


def _cross_sectional_zscore(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=np.float64)
    for row in range(values.shape[0]):
        line = values[row]
        valid = np.isfinite(line)
        count = int(valid.sum())
        if count == 0:
            continue
        subset = line[valid]
        mean = float(subset.mean())
        std = float(subset.std(ddof=0))
        if std > 0:
            out[row, valid] = (subset - mean) / std
        else:
            out[row, valid] = 0.0
    return out


class _Evaluator:
    def __init__(self, view: PanelView) -> None:
        self.view = view
        self._field_cache: dict[str, np.ndarray] = {}

    def field(self, name: str) -> np.ndarray:
        if name not in self._field_cache:
            values = self.view.field(name).astype(np.float64)
            self._field_cache[name] = values
        return self._field_cache[name]

    def evaluate(self, node: ast.AST) -> np.ndarray | float:
        if isinstance(node, ast.Expression):
            return self.evaluate(node.body)
        if isinstance(node, ast.Constant):
            return float(cast(float, node.value))
        if isinstance(node, ast.Name):
            return self.field(node.id)
        if isinstance(node, ast.UnaryOp):
            operand = self.evaluate(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.Not):
                return ~np.asarray(operand, dtype=bool)
        if isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return np.asarray(left) + right
            if isinstance(node.op, ast.Sub):
                return np.asarray(left) - right
            if isinstance(node.op, ast.Mult):
                return np.asarray(left) * right
            if isinstance(node.op, ast.Div):
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.asarray(left) / right
        if isinstance(node, ast.BoolOp):
            flags = [np.asarray(self.evaluate(child), dtype=bool) for child in node.values]
            combined = flags[0]
            for flag in flags[1:]:
                combined = (combined & flag) if isinstance(node.op, ast.And) else (combined | flag)
            return combined
        if isinstance(node, ast.Compare):
            left = np.asarray(self.evaluate(node.left))
            result: np.ndarray | None = None
            for operator, comparator in zip(node.ops, node.comparators, strict=False):
                right = np.asarray(self.evaluate(comparator))
                current = _compare(left, right, operator)
                result = current if result is None else (result & current)
                left = right
            assert result is not None
            return result
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name)
            return _call(function=node.func.id, args=[self.evaluate(arg) for arg in node.args])
        raise StrategyValidationError(f"cannot evaluate node: {type(node).__name__}")


def _compare(left: np.ndarray, right: np.ndarray, operator: ast.cmpop) -> np.ndarray:
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    raise StrategyValidationError(f"unsupported comparison: {type(operator).__name__}")


def _call(function: str, args: list[Any]) -> np.ndarray | float:
    values = [np.asarray(arg, dtype=np.float64) for arg in args]
    if function in {"ma", "ts_mean"}:
        return _rolling(int(values[1]), _nanmean)(values[0])
    if function in {"std", "ts_std"}:
        return _rolling(int(values[1]), _nanstd)(values[0])
    if function == "ts_sum":
        return _rolling(int(values[1]), lambda windows, axis: np.nansum(windows, axis=axis))(
            values[0]
        )
    if function == "ts_min":
        return _rolling(int(values[1]), lambda windows, axis: np.nanmin(windows, axis=axis))(
            values[0]
        )
    if function == "ts_max":
        return _rolling(int(values[1]), lambda windows, axis: np.nanmax(windows, axis=axis))(
            values[0]
        )
    if function == "ts_rank":
        window = int(values[1])
        if window < 2:
            raise StrategyValidationError("ts_rank window must be >= 2")
        return _rolling(window, _rank_last)(values[0])
    if function == "delay":
        return shift(values[0], int(values[1]))
    if function == "ret":
        window = int(values[1])
        if window < 1:
            raise StrategyValidationError("ret window must be >= 1")
        values_0 = values[0]
        shifted = np.full_like(values_0, np.nan)
        shifted[window:] = values_0[:-window]
        with np.errstate(divide="ignore", invalid="ignore"):
            return values_0 / shifted - 1.0
    if function == "shift":
        window = int(values[1])
        shifted = np.full_like(values[0], np.nan)
        if window <= 0:
            raise StrategyValidationError("shift window must be >= 1")
        shifted[window:] = values[0][:-window]
        return shifted
    if function == "rank":
        return _cross_sectional_rank(values[0])
    if function == "zscore":
        return _cross_sectional_zscore(values[0])
    if function == "abs":
        return np.abs(values[0])
    if function == "log":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(values[0])
    if function == "sqrt":
        with np.errstate(invalid="ignore"):
            return np.sqrt(values[0])
    if function == "min":
        return np.minimum(values[0], values[1])
    if function == "max":
        return np.maximum(values[0], values[1])
    raise StrategyValidationError(f"unsupported function: {function}")


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling mean over the time axis (NaN-aware)."""
    return _rolling(window, _nanmean)(np.asarray(values, dtype=np.float64))


def rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Causal sample standard deviation over the time axis (NaN-aware, ddof=1)."""
    return _rolling(window, _nanstd)(np.asarray(values, dtype=np.float64))


def cross_sectional_rank(values: np.ndarray) -> np.ndarray:
    """Per-row percentile rank in ``(0, 1]``; NaN stays NaN."""
    return _cross_sectional_rank(np.asarray(values, dtype=np.float64))


def cross_sectional_zscore(values: np.ndarray) -> np.ndarray:
    """Per-row z-score with NaN preserved."""
    return _cross_sectional_zscore(np.asarray(values, dtype=np.float64))


def shift(values: np.ndarray, window: int) -> np.ndarray:
    """Shift a matrix down the time axis by ``window`` rows (causal)."""
    array = np.asarray(values, dtype=np.float64)
    shifted = np.full_like(array, np.nan)
    if window <= 0:
        raise StrategyValidationError("shift window must be >= 1")
    shifted[window:] = array[:-window]
    return shifted


def evaluate_expression(expression: str | CompiledExpression, view: PanelView) -> np.ndarray:
    """Evaluate an expression against a panel view; returns an ``(n_time, n_sec)`` array."""
    compiled = (
        expression if isinstance(expression, CompiledExpression) else compile_expression(expression)
    )
    result = _Evaluator(view).evaluate(compiled.tree)
    array = np.asarray(result, dtype=np.float64)
    if array.ndim == 0:
        return np.full((view.n_time, view.n_sec), float(array))
    if array.shape != (view.n_time, view.n_sec):
        raise StrategyValidationError(
            f"expression {compiled.source!r} produced shape {array.shape}, expected "
            f"{(view.n_time, view.n_sec)}"
        )
    return array


class ExpressionLibrary:
    """Small convenience wrapper used by templates/tests."""

    FUNCTION_NAMES: ClassVar[tuple[str, ...]] = tuple(sorted(FUNCTIONS))

    @staticmethod
    def fields() -> list[str]:
        return sorted(FIELDS)

    @staticmethod
    def functions() -> list[str]:
        return sorted(FUNCTIONS)
