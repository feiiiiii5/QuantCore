# ruff: noqa: RUF001 -- user-facing Chinese copy intentionally uses full-width punctuation.
"""Compare saved research runs without hiding capital or assumption differences."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np

from ..backtest.result import BacktestResult
from .store import ExperimentRecord, ExperimentStore


def _recorded_text(value: Any) -> str | None:
    return str(value) if value not in (None, "", "unknown", "missing") else None


def _provenance(record: ExperimentRecord, result: BacktestResult) -> dict[str, Any]:
    metadata = record.metadata
    strategy = metadata.get("strategy") or result.strategy.get("spec") or result.strategy
    snapshot = result.snapshot or metadata.get("snapshot") or {}
    environment = metadata.get("environment") or {}
    return {
        "strategy_name": metadata.get("strategy_name") or strategy.get("name"),
        "template": strategy.get("template"),
        "strategy_hash": metadata.get("strategy_hash") or result.strategy.get("spec_hash"),
        "params": strategy.get("params") or metadata.get("params") or {},
        "snapshot_id": snapshot.get("snapshot_id"),
        "content_hash": _recorded_text(snapshot.get("content_hash")),
        "source": _recorded_text(snapshot.get("source")),
        "synthetic": snapshot.get("synthetic", metadata.get("synthetic")),
        "config": result.config or metadata.get("config") or {},
        "engine_backend": _recorded_text(result.engine_backend),
        "engine_version": _recorded_text(result.engine_version),
        "git_commit": environment.get("git_commit"),
        "parent_run_id": metadata.get("parent_run_id"),
    }


def _series(record: ExperimentRecord, result: BacktestResult) -> dict[str, Any]:
    provenance = _provenance(record, result)
    recorded_cash = provenance["config"].get("initial_cash")
    initial_cash = (
        float(recorded_cash)
        if isinstance(recorded_cash, (float, int))
        and not isinstance(recorded_cash, bool)
        and math.isfinite(recorded_cash)
        and recorded_cash > 0
        else None
    )
    equity = result.equity_yuan
    if equity.size:
        # Include starting capital, so first-day fees/losses are not erased.
        peaks = np.maximum.accumulate(
            np.concatenate(([initial_cash], equity)) if initial_cash is not None else equity
        )[-len(equity) :]
        drawdown = np.divide(equity, peaks, out=np.ones_like(equity), where=peaks > 0) - 1.0
    else:
        drawdown = equity
    return {
        "run_id": record.run_id,
        "label": provenance["strategy_name"] or provenance["template"] or record.run_id,
        "dates": result.dates.astype(int).tolist(),
        "equity": equity.tolist(),
        "initial_cash": initial_cash,
        "normalized_equity": (equity / initial_cash).tolist() if initial_cash is not None else None,
        "drawdown": drawdown.tolist(),
        "provenance": provenance,
    }


def _assumptions(series: dict[str, Any]) -> dict[str, Any]:
    provenance = series["provenance"]
    config = provenance["config"]
    dates = series["dates"]
    calendar = (
        {
            "start": dates[0],
            "end": dates[-1],
            "observations": len(dates),
            "calendar_hash": hashlib.sha256(",".join(map(str, dates)).encode("ascii")).hexdigest(),
        }
        if dates
        else None
    )
    backend, version = provenance["engine_backend"], provenance["engine_version"]
    return {
        "dates": calendar,
        "data_hash": provenance["content_hash"],
        "source": provenance["source"],
        "synthetic": provenance["synthetic"],
        "initial_cash": series["initial_cash"],
        "costs": config.get("costs"),
        "execution": config.get("exec"),
        "rules": config.get("rules"),
        "corporate_actions": (
            {
                "panel": config.get("use_panel_corporate_actions", False),
                "explicit": config.get("corporate_actions", [])
                if "use_panel_corporate_actions" in config
                else [],
            }
            if "corporate_actions" in config
            else None
        ),
        "risk": config.get("risk"),
        "annual_days": config.get("annual_days"),
        # A recorded null benchmark means no benchmark; an absent key is unknown.
        "benchmark": {"code": config["benchmark_code"]} if "benchmark_code" in config else None,
        "engine": {"backend": backend, "version": version} if backend and version else None,
    }


_DIMENSIONS = (
    ("dates", "交易区间与交易日", "实际交易日不同；曲线保留各自区间，不截断重算收益。"),
    ("data_hash", "数据内容指纹", "数据内容不同；收益差异可能来自股票池、行情或复权口径。"),
    ("source", "数据来源", "数据来源不同；请先确认行情与复权口径。"),
    ("synthetic", "合成 / 真实数据", "合成与非合成数据混合；不能据此比较真实市场表现。"),
    (
        "initial_cash",
        "初始资金",
        "初始资金不同；净值已按各自初始资金归一，最低佣金与整手约束仍可能影响结果。",
    ),
    ("costs", "费用模型", "费用设置不同；净收益差异包含费用模型的影响。"),
    ("execution", "成交与滑点", "成交或滑点设置不同；收益差异不能只归因于策略。"),
    ("rules", "交易规则", "交易规则不同；请核对手数、T+1 与涨跌停等约束。"),
    ("corporate_actions", "公司行为", "公司行为设置不同；分红、送转等事件会影响现金与持仓。"),
    ("risk", "风险约束", "风险约束不同；请核对最大持仓数与单票权重等设置。"),
    ("annual_days", "年化交易日", "年化交易日不同；年化收益与风险指标采用不同口径。"),
    ("benchmark", "基准", "基准不同；超额收益与跟踪指标不能直接横比。"),
    ("engine", "引擎版本", "引擎或版本不同；结果差异可能包含实现变化。"),
)


def compare_experiments(store: ExperimentStore, run_ids: list[str]) -> dict[str, Any]:
    """Return raw curves, capital-normalized curves and recorded assumption checks.

    Matching assumptions describe the comparison setup, not strategy quality or
    data accuracy. Curves keep their original dates; no interpolation or overlap
    rebasing changes the meaning of the saved metrics.
    """
    metrics: dict[str, Any] = {}
    equity: list[dict[str, Any]] = []
    assumptions: dict[str, dict[str, Any]] = {}
    for run_id in run_ids:
        record = store.get(run_id)
        result = store.load_result(run_id)
        metrics[run_id] = result.metrics
        series = _series(record, result)
        equity.append(series)
        assumptions[run_id] = _assumptions(series)

    dimensions: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for key, label, mismatch in _DIMENSIONS:
        values = {run_id: assumptions[run_id][key] for run_id in run_ids}
        known_values = [value for value in values.values() if value is not None]
        differs = any(value != known_values[0] for value in known_values[1:])
        status = (
            "different" if differs else "unknown" if len(known_values) < len(run_ids) else "matched"
        )
        dimensions.append({"key": key, "label": label, "status": status, "values": values})
        if status == "different":
            warnings.append({"code": key, "message": mismatch})
        elif status == "unknown":
            warnings.append({"code": key, "message": f"{label}记录不完整，无法确认是否一致。"})
    status = (
        "different"
        if any(row["status"] == "different" for row in dimensions)
        else "unknown"
        if any(row["status"] == "unknown" for row in dimensions)
        else "matched"
    )
    return {
        "ids": run_ids,
        "metrics": metrics,
        "equity": equity,
        "comparison": {"status": status, "dimensions": dimensions, "warnings": warnings},
    }
