"""Registry for built-in strategy templates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import StrategyValidationError
from ..strategy.base import Strategy, UniverseFilter
from . import builtin, research


@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    description: str
    params_model: type[BaseModel]
    factory: Callable[[Any, UniverseFilter, str], Strategy]


_TEMPLATES: dict[str, TemplateEntry] = {}


def register_template(entry: TemplateEntry) -> None:
    _TEMPLATES[entry.template_id] = entry


for _entry in (
    TemplateEntry(
        "buy_and_hold",
        "买入持有: 首个可交易日等权买入并持有",
        builtin.BuyAndHoldParams,
        lambda params, universe, name: builtin.BuyAndHoldStrategy(params, universe, name),
    ),
    TemplateEntry(
        "dual_ma",
        "双均线: 短均线在长均线上方时持有",
        builtin.DualMAParams,
        lambda params, universe, name: builtin.DualMAStrategy(params, universe, name),
    ),
    TemplateEntry(
        "momentum",
        "动量: 按回看收益横截面排序, 持有领先者",
        builtin.MomentumParams,
        lambda params, universe, name: builtin.MomentumStrategy(params, universe, name),
    ),
    TemplateEntry(
        "low_vol",
        "低波动: 持有波动率最低的证券",
        builtin.LowVolParams,
        lambda params, universe, name: builtin.LowVolStrategy(params, universe, name),
    ),
    TemplateEntry(
        "dividend_quality",
        "红利质量: 股息率 + PIT ROE 质量",
        builtin.DividendQualityParams,
        lambda params, universe, name: builtin.DividendQualityStrategy(params, universe, name),
    ),
    TemplateEntry(
        "small_cap_liquidity",
        "小市值+流动性: 小流通市值并过滤低流动性",
        builtin.SmallCapLiquidityParams,
        lambda params, universe, name: builtin.SmallCapLiquidityStrategy(params, universe, name),
    ),
    TemplateEntry(
        "multi_factor",
        "多因子打分: 动量 + 低波 + 价值 + 质量",
        builtin.MultiFactorParams,
        lambda params, universe, name: builtin.MultiFactorStrategy(params, universe, name),
    ),
    TemplateEntry(
        "trend_momentum",
        "趋势动量研究候选: 正动量与长期均线过滤, 等权配置",
        research.TrendMomentumParams,
        lambda params, universe, name: research.TrendMomentumStrategy(params, universe, name),
    ),
    TemplateEntry(
        "liquid_reversal",
        "流动性反转研究候选: 短期落后、长期趋势与成交额过滤",
        research.LiquidReversalParams,
        lambda params, universe, name: research.LiquidReversalStrategy(params, universe, name),
    ),
    TemplateEntry(
        "defensive_low_vol",
        "防御低波研究候选: 正趋势、低波筛选与逆波动配置",
        research.DefensiveLowVolParams,
        lambda params, universe, name: research.DefensiveLowVolStrategy(params, universe, name),
    ),
):
    register_template(_entry)


_ALIASES: dict[str, str] = {"ma_cross": "dual_ma"}


def _canonical(template_id: str) -> str:
    return _ALIASES.get(template_id, template_id)


def template_ids() -> list[str]:
    return sorted(_TEMPLATES)


def get_template_entry(template_id: str) -> TemplateEntry:
    entry = _TEMPLATES.get(_canonical(template_id))
    if entry is None:
        raise StrategyValidationError(
            f"unknown strategy template {template_id!r}; available: {template_ids()}"
        )
    return entry


def template_param_model(template_id: str) -> type[BaseModel]:
    return get_template_entry(template_id).params_model


def template_params_schema(template_id: str) -> dict[str, Any]:
    return template_param_model(template_id).model_json_schema()


def create_template(
    template_id: str,
    params: dict[str, Any] | BaseModel | None = None,
    universe: UniverseFilter | None = None,
    name: str | None = None,
) -> Strategy:
    """Validate ``params`` against the template's pydantic model and build the strategy."""
    entry = get_template_entry(template_id)
    try:
        if isinstance(params, BaseModel):
            model = entry.params_model.model_validate(params.model_dump())
        else:
            model = entry.params_model.model_validate(params or {})
    except ValidationError as exc:
        raise StrategyValidationError(
            f"invalid params for template {template_id!r}: {exc.errors()}"
        ) from exc
    return entry.factory(model, universe or UniverseFilter(), name or template_id)


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": entry.template_id,
            "description": entry.description,
            "params_schema": entry.params_model.model_json_schema(),
        }
        for entry in (_TEMPLATES[key] for key in template_ids())
    ]
