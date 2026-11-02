# ruff: noqa: RUF001 -- user-facing Chinese copy intentionally uses full-width punctuation.
"""Beginner onboarding state, plain-language strategy presets and watchlist helpers.

Everything here is local-only: SQLite meta plus filesystem detection.  No network
access, no order routing, and no real-market claims.  The UI decides whether to show
beginner mode; this module always reports ``beginner=True`` and lets the client hide it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server.workspace import Workspace

META_KEY = "onboarding"
WATCHLIST_META_KEY = "watchlist"
MAX_WATCHLIST = 50
CODE_PATTERN = re.compile(r"^[0-9]{6}$")

#: Four beginner steps, in display order.  ``done`` is filled in by :func:`build_state`.
STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "data",
        "title": "生成示例数据",
        "description": "用 SYNTHETIC 合成数据生成第一个快照；不联网，也不是真实行情。",
        "action": "bootstrap",
        "label": "生成示例数据",
        "done": False,
    },
    {
        "id": "backtest",
        "title": "跑第一个回测",
        "description": "选一个白话策略预设，在示例数据上跑一次回测。",
        "action": "backtest",
        "label": "去跑回测",
        "done": False,
    },
    {
        "id": "result",
        "title": "看懂结果",
        "description": "到实验页看收益、回撤、夏普和可信度提示，知道这个结果能不能信。",
        "action": "browse",
        "label": "看结果页",
        "done": False,
    },
    {
        "id": "data_health",
        "title": "查看数据体检",
        "description": "打开数据体检，确认覆盖率、缺口和 OHLC 自洽，再决定是否继续研究。",
        "action": "data",
        "label": "查看数据体检",
        "done": False,
    },
)

STEP_IDS: tuple[str, ...] = tuple(str(step["id"]) for step in STEPS)

#: Plain-language presets.  ``template`` ids and ``params`` are validated by tests and must
#: stay runnable against the built-in templates.
PRESETS: list[dict[str, Any]] = [
    {
        "id": "trend_following",
        "name": "双均线趋势",
        "tagline": "短期均线在上就持有，跌破就换",
        "description": "用 5 日均线和 20 日均线判断趋势：短均线在长均线上方时，买入走势较强的股票；每周调仓。",
        "plain_terms": "均线=最近 N 天收盘价的平均；短均线上穿长均线=趋势偏强；调仓=重新挑一遍股票。",
        "risk_note": "震荡市会频繁买卖，交易成本和回撤可能变大；仅用于研究与模拟，不构成投资建议。",
        "template": "dual_ma",
        "params": {"short": 5, "long": 20, "top_n": 10, "rebalance": "weekly"},
        "horizon": "1–3 个月",
        "suitable_for": "想跟着趋势走、能接受震荡期反复小亏的人",
    },
    {
        "id": "momentum_leaders",
        "name": "动量强者",
        "tagline": "过去 3 个月涨得好的，继续持有",
        "description": "按过去 60 个交易日收益排序，买入排名靠前的 10 只，每月调仓。",
        "plain_terms": "动量=过去一段时间的涨幅；横截面=把所有股票放在一起比；调仓=定期换股。",
        "risk_note": "追涨策略在风格切换时可能集中回撤；历史涨幅不代表未来。仅研究与模拟。",
        "template": "momentum",
        "params": {"lookback": 60, "skip": 5, "top_n": 10, "rebalance": "monthly"},
        "horizon": "3–6 个月",
        "suitable_for": "相信强者恒强、愿意定期换股的人",
    },
    {
        "id": "low_volatility",
        "name": "低波动防守",
        "tagline": "挑波动最小的股票，先求稳",
        "description": "按过去 60 个交易日波动率排序，持有波动最低的 10 只，每月调仓。",
        "plain_terms": "波动率=价格上下晃动的幅度；低波动=平时涨跌比较温和；最大回撤=从高点最多跌多少。",
        "risk_note": "低波动不等于不亏；极端行情里也会一起下跌。仅研究与模拟。",
        "template": "low_vol",
        "params": {"lookback": 60, "top_n": 10, "rebalance": "monthly"},
        "horizon": "6–12 个月",
        "suitable_for": "不想天天盯盘、更在意回撤的人",
    },
    {
        "id": "dividend_quality",
        "name": "红利质量",
        "tagline": "股息率高、赚钱能力稳的公司",
        "description": "用股息率加 ROE 质量打分，持有综合得分靠前的 10 只，每季度调仓。",
        "plain_terms": "股息率=每股分红/股价；ROE=净资产收益率，衡量公司赚钱效率；PIT=只使用当时已公布的财报。",
        "risk_note": "高股息可能来自股价下跌；财报口径和分红政策会变。仅研究与模拟。",
        "template": "dividend_quality",
        "params": {"top_n": 10, "min_roe": 0.0, "rebalance": "quarterly"},
        "horizon": "6–12 个月",
        "suitable_for": "偏好慢一点、看重分红和基本面的人",
    },
    {
        "id": "small_cap_liquidity",
        "name": "小市值流动性",
        "tagline": "小盘股里挑成交活跃的",
        "description": "在小流通市值股票中过滤掉成交额最低的 30%，等权持有 10 只，每月调仓。",
        "plain_terms": "流通市值=能在市场上买卖的股票总价值；流动性=买卖是否容易；成交额=当天成交了多少钱。",
        "risk_note": "小盘股波动和流动性风险更高，容量有限；仅研究与模拟。",
        "template": "small_cap_liquidity",
        "params": {
            "top_n": 10,
            "amount_lookback": 20,
            "liquidity_quantile": 0.3,
            "rebalance": "monthly",
        },
        "horizon": "3–6 个月",
        "suitable_for": "愿意承担更高波动、关注小盘风格的人",
    },
    {
        "id": "multi_factor",
        "name": "多因子均衡",
        "tagline": "动量、低波、价值、质量一起打分",
        "description": "把动量、低波动、估值和质量四个分数合成一个总分，持有前 10 名，每月调仓。",
        "plain_terms": "因子=用来打分的指标；估值=贵不贵；质量=公司赚钱能力；合成=几个分数加权成一个。",
        "risk_note": "多因子不是稳赚，权重和样本期会显著影响结果；仅研究与模拟。",
        "template": "multi_factor",
        "params": {
            "momentum_window": 120,
            "vol_window": 60,
            "top_n": 10,
            "rebalance": "monthly",
        },
        "horizon": "6–12 个月",
        "suitable_for": "想做分散配置、不想押单一风格的人",
    },
]


def _has_experiment(root: Path) -> bool:
    """True when at least one persisted experiment directory exists (no store side effect)."""
    try:
        return any(
            child.is_dir() and (child / "metadata.json").is_file() for child in root.iterdir()
        )
    except OSError:
        return False


def _completed_from(raw: Any) -> list[str]:
    if not isinstance(raw, dict):
        return []
    completed = raw.get("completed")
    if isinstance(completed, dict):
        completed = list(completed)
    if not isinstance(completed, list):
        return []
    seen = {str(item) for item in completed}
    return [step for step in STEP_IDS if step in seen]


def _completed_payload(completed: list[str]) -> dict[str, Any]:
    return {"completed": completed, "updated_at": datetime.now(UTC).isoformat()}


def build_state(workspace: Workspace) -> dict[str, Any]:
    """Combine recorded progress with automatic detection of local artefacts."""
    raw = workspace.state.get_meta(META_KEY)
    completed = set(_completed_from(raw))
    auto_done: set[str] = set()
    if workspace.list_snapshot_manifests():
        auto_done.add("data")
    if _has_experiment(workspace.settings.experiments_root):
        auto_done.update({"backtest", "result"})

    steps: list[dict[str, Any]] = []
    for definition in STEPS:
        done = bool(definition["id"] in completed or definition["id"] in auto_done)
        steps.append({**definition, "done": done})
    done_count = sum(1 for step in steps if step["done"])
    return {
        "first_run": raw is None,
        "beginner": True,
        "steps": steps,
        "progress": {"done": done_count, "total": len(steps)},
    }


def complete_step(workspace: Workspace, step_id: str) -> dict[str, Any]:
    """Record one completed step (idempotent) and return the refreshed state."""
    if step_id not in STEP_IDS:
        raise ValueError(f"unknown onboarding step: {step_id!r}")
    completed = _completed_from(workspace.state.get_meta(META_KEY))
    if step_id not in completed:
        completed.append(step_id)
    workspace.state.set_meta(META_KEY, _completed_payload(completed))
    return build_state(workspace)


def reset_onboarding(workspace: Workspace) -> dict[str, Any]:
    """Clear the recorded onboarding meta; auto-detected artefacts remain visible."""
    workspace.state.set_meta(META_KEY, None)
    return build_state(workspace)


def _normalise_codes(codes: list[Any]) -> list[str]:
    seen: set[str] = set()
    normalised: list[str] = []
    for item in codes:
        if not isinstance(item, str):
            raise ValueError("watchlist codes must be strings")
        code = item.strip()
        if not CODE_PATTERN.fullmatch(code):
            raise ValueError(f"invalid watchlist code: {item!r} (expected 6 digits)")
        if code not in seen:
            seen.add(code)
            normalised.append(code)
    if len(normalised) > MAX_WATCHLIST:
        raise ValueError(f"watchlist supports at most {MAX_WATCHLIST} codes")
    return normalised


def read_watchlist(workspace: Workspace) -> list[str]:
    """Read the persisted watchlist, tolerating old/corrupt meta shapes."""
    raw = workspace.state.get_meta(WATCHLIST_META_KEY, [])
    if isinstance(raw, dict):
        raw = raw.get("codes", [])
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    codes: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        code = item.strip()
        if CODE_PATTERN.fullmatch(code) and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def save_watchlist(workspace: Workspace, codes: Any) -> list[str]:
    """Validate, deduplicate and persist a watchlist; raises ``ValueError`` on bad input."""
    if not isinstance(codes, list):
        raise ValueError("watchlist payload must be {'codes': [...]}")
    normalised = _normalise_codes(codes)
    # The live-quote service reads this meta key as a plain list of codes.
    workspace.state.set_meta(WATCHLIST_META_KEY, normalised)
    return normalised


__all__ = [
    "CODE_PATTERN",
    "MAX_WATCHLIST",
    "META_KEY",
    "PRESETS",
    "STEPS",
    "STEP_IDS",
    "WATCHLIST_META_KEY",
    "build_state",
    "complete_step",
    "read_watchlist",
    "reset_onboarding",
    "save_watchlist",
]
