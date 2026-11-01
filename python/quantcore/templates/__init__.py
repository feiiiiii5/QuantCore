"""Built-in strategy templates (7) and their parameter schemas."""

from __future__ import annotations

from .builtin import (
    BuyAndHoldParams,
    BuyAndHoldStrategy,
    DividendQualityParams,
    DividendQualityStrategy,
    DualMAParams,
    DualMAStrategy,
    LowVolParams,
    LowVolStrategy,
    MomentumParams,
    MomentumStrategy,
    MultiFactorParams,
    MultiFactorStrategy,
    SmallCapLiquidityParams,
    SmallCapLiquidityStrategy,
    TemplateParams,
)
from .registry import (
    TemplateEntry,
    create_template,
    get_template_entry,
    list_templates,
    register_template,
    template_ids,
    template_param_model,
    template_params_schema,
)

__all__ = [
    "BuyAndHoldParams",
    "BuyAndHoldStrategy",
    "DividendQualityParams",
    "DividendQualityStrategy",
    "DualMAParams",
    "DualMAStrategy",
    "LowVolParams",
    "LowVolStrategy",
    "MomentumParams",
    "MomentumStrategy",
    "MultiFactorParams",
    "MultiFactorStrategy",
    "SmallCapLiquidityParams",
    "SmallCapLiquidityStrategy",
    "TemplateEntry",
    "TemplateParams",
    "create_template",
    "get_template_entry",
    "list_templates",
    "register_template",
    "template_ids",
    "template_param_model",
    "template_params_schema",
]
