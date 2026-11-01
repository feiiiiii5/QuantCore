"""Strategy template and validation routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from ..errors import StrategyValidationError
from ..strategy.sandbox import audit_source
from ..strategy.spec import StrategySpec
from ..templates.registry import (
    get_template_entry,
    list_templates,
    template_param_model,
)
from .schemas import StrategyFileRequest, TemplateValidateRequest
from .workspace import Workspace, json_safe

TEMPLATE_NAMES: dict[str, str] = {
    "buy_and_hold": "买入持有",
    "dual_ma": "双均线",
    "momentum": "动量",
    "low_vol": "低波动",
    "dividend_quality": "红利质量",
    "small_cap_liquidity": "小市值+流动性",
    "multi_factor": "多因子打分",
}
ALLOWED_SUFFIXES = {".yaml": "yaml", ".yml": "yaml", ".py": "python"}


def _files_root(ctx: Workspace) -> Path:
    return ctx.settings.data_root / "strategies"


def _safe_name(name: str) -> str:
    candidate = name.strip()
    if not candidate or candidate != Path(candidate).name or candidate.startswith("."):
        raise HTTPException(status_code=400, detail=f"invalid strategy file name: {name!r}")
    if Path(candidate).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"strategy files must end with one of {sorted(ALLOWED_SUFFIXES)}",
        )
    return candidate


def _validate_content(name: str, content: str) -> None:
    suffix = Path(name).suffix.lower()
    try:
        if ALLOWED_SUFFIXES[suffix] == "yaml":
            StrategySpec.from_yaml(content)
        else:
            issues = audit_source(content, origin=name)
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise StrategyValidationError("; ".join(issue.message for issue in errors[:3]))
    except StrategyValidationError as exc:
        raise HTTPException(status_code=400, detail=f"invalid strategy file: {exc}") from exc


def register_strategy_routes(app: FastAPI, ctx: Workspace) -> None:
    @app.get("/api/strategies/templates")
    def templates() -> Any:
        rows = []
        for item in list_templates():
            row = dict(item)
            row["name"] = TEMPLATE_NAMES.get(str(item["id"]), str(item["id"]))
            rows.append(row)
        return json_safe(rows)

    @app.get("/api/strategies/templates/{template_id}")
    def template(template_id: str) -> Any:
        try:
            entry = get_template_entry(template_id)
        except StrategyValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return json_safe(
            {
                "id": entry.template_id,
                "name": TEMPLATE_NAMES.get(entry.template_id, entry.template_id),
                "description": entry.description,
                "params_schema": entry.params_model.model_json_schema(),
            }
        )

    @app.post("/api/strategies/validate")
    def validate(payload: TemplateValidateRequest) -> Any:
        try:
            model = template_param_model(payload.template)
            parsed = model.model_validate(payload.params)
        except ValidationError as exc:
            return {
                "valid": False,
                "errors": json_safe(exc.errors()),
                "defaults": model().model_dump(mode="json"),
            }
        except StrategyValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"valid": True, "errors": [], "defaults": parsed.model_dump(mode="json")}

    @app.get("/api/strategies/files")
    def list_files() -> Any:
        root = _files_root(ctx)
        rows = []
        if root.exists():
            for path in sorted(root.iterdir()):
                if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                    continue
                rows.append(
                    {
                        "name": path.name,
                        "kind": ALLOWED_SUFFIXES[path.suffix.lower()],
                        "bytes": path.stat().st_size,
                        "updated_at": datetime.fromtimestamp(
                            path.stat().st_mtime, tz=UTC
                        ).isoformat(),
                    }
                )
        return json_safe(rows)

    @app.get("/api/strategies/files/{name}")
    def read_file(name: str) -> Any:
        safe = _safe_name(name)
        path = _files_root(ctx) / safe
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"strategy file not found: {safe}")
        return {
            "name": safe,
            "kind": ALLOWED_SUFFIXES[path.suffix.lower()],
            "content": path.read_text(encoding="utf-8"),
        }

    @app.put("/api/strategies/files/{name}")
    def write_file(name: str, payload: StrategyFileRequest) -> Any:
        safe = _safe_name(name)
        _validate_content(safe, payload.content)
        root = _files_root(ctx)
        root.mkdir(parents=True, exist_ok=True)
        path = root / safe
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(payload.content, encoding="utf-8")
        temporary.replace(path)
        return {
            "name": safe,
            "kind": ALLOWED_SUFFIXES[path.suffix.lower()],
            "bytes": path.stat().st_size,
        }
