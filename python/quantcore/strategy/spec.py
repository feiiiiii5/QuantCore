"""Strategy specification: ``strategy.yaml``, JSON Schema validation and content hash.

A spec references either a built-in template (with validated parameters) or a custom
strategy module (loaded through the static sandbox audit).  The content hash covers the
specification *and* the strategy code bytes, so it can be recorded in experiment
metadata for exact replay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..errors import StrategyValidationError
from .base import Strategy, UniverseFilter

BUILTIN_TEMPLATE_FILES = (
    Path(__file__).resolve().parent.parent / "templates" / "builtin.py",
    Path(__file__).resolve().parent.parent / "templates" / "base.py",
)


class UniverseSpec(BaseModel):
    """Serialisable universe filter used by specs and templates."""

    model_config = ConfigDict(extra="forbid")
    exclude_st: bool = True
    exclude_suspended: bool = True
    min_price: float = Field(default=1.0, ge=0.0)
    min_list_days: int = Field(default=0, ge=0)
    boards: list[str] | None = None
    min_amount: float = Field(default=0.0, ge=0.0)

    def to_universe(self) -> UniverseFilter:
        boards = tuple(self.boards) if self.boards else None
        return UniverseFilter(
            exclude_st=self.exclude_st,
            exclude_suspended=self.exclude_suspended,
            min_price=self.min_price,
            min_list_days=self.min_list_days,
            boards=boards,
            min_amount=self.min_amount,
        )


class StrategySpec(BaseModel):
    """A complete strategy definition loaded from YAML or constructed in code."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    template: str | None = None
    module: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    rebalance: str | int | None = None
    description: str = ""
    version: str = "1"

    @model_validator(mode="after")
    def _exactly_one_source(self) -> StrategySpec:
        from ..templates.registry import template_ids

        if (self.template is None) == (self.module is None):
            raise ValueError("a strategy spec needs exactly one of 'template' or 'module'")
        if self.template is not None and self.template not in template_ids():
            raise ValueError(f"unknown template {self.template!r}; available: {template_ids()}")
        return self

    # -- parameter validation --------------------------------------------
    def resolved_params(self) -> tuple[str, dict[str, Any]]:
        """Return ``(template_id, params)`` with the spec-level rebalance folded in."""
        if self.template is None:  # pragma: no cover - guarded by validator
            raise StrategyValidationError("spec has no template")
        params = dict(self.params)
        if self.rebalance is not None:
            params["rebalance"] = self.rebalance
        return self.template, params

    def validate_params(self) -> dict[str, Any]:
        """Validate template params against the template's JSON-schema model."""
        if self.template is None:
            return {}
        from ..templates.registry import template_param_model

        template_id, params = self.resolved_params()
        try:
            model = template_param_model(template_id).model_validate(params)
        except ValidationError as exc:
            raise StrategyValidationError(
                f"invalid params for template {template_id!r}: {exc.errors()}"
            ) from exc
        return model.model_dump(mode="json")

    # -- loading ----------------------------------------------------------
    def load(self, base_dir: str | Path | None = None) -> Strategy:
        """Instantiate the strategy described by this spec."""
        universe = self.universe.to_universe()
        if self.template is not None:
            from ..templates.registry import create_template

            template_id, params = self.resolved_params()
            return create_template(template_id, params, universe=universe, name=self.name)
        assert self.module is not None
        module_path = Path(self.module)
        if not module_path.is_absolute() and base_dir is not None:
            module_path = Path(base_dir) / module_path
        from .sandbox import load_strategy_module

        return load_strategy_module(module_path, universe=universe, name=self.name)

    # -- serialisation / hashing -----------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls, text_or_path: str | Path) -> StrategySpec:
        """Load a spec from YAML text or a file path."""
        text: str
        if isinstance(text_or_path, Path) or (
            isinstance(text_or_path, str)
            and "\n" not in text_or_path
            and Path(text_or_path).exists()
        ):
            text = Path(text_or_path).read_text(encoding="utf-8")
        else:
            text = str(text_or_path)
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise StrategyValidationError(f"invalid strategy YAML: {exc}") from exc
        if not isinstance(payload, dict):
            raise StrategyValidationError("strategy YAML must be a mapping")
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            raise StrategyValidationError(f"invalid strategy spec: {exc.errors()}") from exc

    def code_bytes(self, base_dir: str | Path | None = None) -> bytes:
        """Source bytes that define the strategy behaviour (for the content hash)."""
        if self.template is not None:
            chunks = []
            for path in BUILTIN_TEMPLATE_FILES:
                if path.exists():
                    chunks.append(path.read_bytes())
            return b"\n".join(chunks)
        assert self.module is not None
        module_path = Path(self.module)
        if not module_path.is_absolute() and base_dir is not None:
            module_path = Path(base_dir) / module_path
        if not module_path.exists():
            raise StrategyValidationError(f"strategy module not found: {module_path}")
        return module_path.read_bytes()

    def content_hash(self, base_dir: str | Path | None = None) -> str:
        """Stable hash of the spec plus the strategy code bytes."""
        hasher = hashlib.sha256()
        hasher.update(json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode())
        hasher.update(self.code_bytes(base_dir))
        return hasher.hexdigest()

    def specification(self, base_dir: str | Path | None = None) -> dict[str, Any]:
        from ..templates.registry import template_ids

        return {
            "spec": self.to_dict(),
            "content_hash": self.content_hash(base_dir),
            "template_catalog": template_ids() if self.template else [],
        }

    # -- schemas ----------------------------------------------------------
    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return cls.model_json_schema()


def template_catalog() -> list[dict[str, Any]]:
    """JSON schemas for every built-in template (used by docs/UI banners)."""
    from ..templates.registry import list_templates

    return list_templates()


def load_spec(path: str | Path) -> StrategySpec:
    return StrategySpec.from_yaml(Path(path))


def save_spec(spec: StrategySpec, path: str | Path) -> None:
    Path(path).write_text(spec.to_yaml(), encoding="utf-8")
