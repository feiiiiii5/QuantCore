"""Static sandbox audit and restricted loader for custom strategy modules.

This is a *interface and validation* layer: custom strategy code must pass an AST audit
before it is imported.  It is not a hard security boundary (a subprocess sandbox with
resource limits is a documented TODO for M4/M5), and it must not be used to run
untrusted third-party code.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import StrategyValidationError
from .base import Strategy, UniverseFilter

ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "math",
        "statistics",
        "dataclasses",
        "typing",
        "collections",
        "json",
        "datetime",
        "numpy",
        "pandas",
        "quantcore",
        "quantcore.strategy",
        "quantcore.templates",
        "quantcore.data",
    }
)

FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "memoryview",
        "exit",
        "quit",
    }
)

SUSPICIOUS_CALLS: frozenset[str] = frozenset({"os.system", "subprocess.run", "socket.socket"})


@dataclass(frozen=True)
class SandboxIssue:
    severity: str
    message: str
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "message": self.message, "line": self.line}


def _module_allowed(module: str) -> bool:
    root = module.split(".")[0]
    if module in ALLOWED_MODULES or root in ALLOWED_MODULES:
        return True
    return any(module.startswith(f"{allowed}.") for allowed in ALLOWED_MODULES)


def audit_source(source: str, origin: str = "<string>") -> list[SandboxIssue]:
    """Audit strategy source; returns issues (empty means the source passed)."""
    try:
        tree = ast.parse(source, filename=origin)
    except SyntaxError as exc:
        return [SandboxIssue("error", f"syntax error: {exc}", int(exc.lineno or 0))]
    issues: list[SandboxIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _module_allowed(alias.name):
                    issues.append(
                        SandboxIssue("error", f"import not allowed: {alias.name}", node.lineno)
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not _module_allowed(module):
                issues.append(SandboxIssue("error", f"import not allowed: {module}", node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_NAMES:
                issues.append(
                    SandboxIssue("error", f"call to forbidden builtin: {node.func.id}", node.lineno)
                )
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            issues.append(
                SandboxIssue("error", f"dunder attribute access: {node.attr}", node.lineno)
            )
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id != "__name__":
            issues.append(SandboxIssue("error", f"dunder name access: {node.id}", node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            dotted = _dotted_name(node.func)
            if dotted in SUSPICIOUS_CALLS:
                issues.append(SandboxIssue("error", f"call not allowed: {dotted}", node.lineno))
    return issues


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def assert_safe(source: str, origin: str = "<string>") -> None:
    issues = audit_source(source, origin)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        details = "; ".join(f"{issue.message} (line {issue.line})" for issue in errors[:5])
        raise StrategyValidationError(
            f"strategy module {origin} failed the sandbox audit: {details}"
        )


def audit_file(path: str | Path) -> list[SandboxIssue]:
    target = Path(path)
    if not target.exists():
        raise StrategyValidationError(f"strategy module not found: {target}")
    return audit_source(target.read_text(encoding="utf-8"), origin=str(target))


def load_strategy_module(
    path: str | Path,
    *,
    universe: UniverseFilter | None = None,
    name: str | None = None,
) -> Strategy:
    """Audit and import a custom strategy module, returning a :class:`Strategy` instance.

    Supported module conventions (first match wins):

    - a module-level ``STRATEGY`` attribute that is a :class:`Strategy` instance/class;
    - a ``create_strategy(universe=None)`` factory function;
    - exactly one :class:`Strategy` subclass defined in the module (instantiated with no
      arguments).
    """
    target = Path(path).resolve()
    source = target.read_text(encoding="utf-8")
    assert_safe(source, str(target))
    module_name = f"_qc_user_strategy_{hashlib.sha256(source.encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise StrategyValidationError(f"cannot import strategy module: {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise StrategyValidationError(f"strategy module raised during import: {exc}") from exc
    strategy = _instantiate(module, universe, name)
    if strategy is None:
        raise StrategyValidationError(
            f"strategy module {target} does not expose a Strategy (see docstring for conventions)"
        )
    return strategy


def _instantiate(module: Any, universe: UniverseFilter | None, name: str | None) -> Strategy | None:
    candidate = getattr(module, "STRATEGY", None)
    if isinstance(candidate, Strategy):
        return candidate
    if isinstance(candidate, type) and issubclass(candidate, Strategy):
        return _construct(candidate, universe, name)
    factory = getattr(module, "create_strategy", None)
    if callable(factory):
        produced = factory(universe=universe) if universe is not None else factory()
        if not isinstance(produced, Strategy):
            raise StrategyValidationError("create_strategy() must return a Strategy")
        return produced
    subclasses = [
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, Strategy)
        and value.__module__ == module.__name__
    ]
    if len(subclasses) == 1:
        return _construct(subclasses[0], universe, name)
    return None


def _construct(cls: type[Strategy], universe: UniverseFilter | None, name: str | None) -> Strategy:
    import inspect

    signature = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}
    if "universe" in signature.parameters and universe is not None:
        kwargs["universe"] = universe
    if "name" in signature.parameters and name is not None:
        kwargs["name"] = name
    instance = cls(**kwargs)
    assert isinstance(instance, Strategy)
    return instance


def sandbox_policy() -> dict[str, Any]:
    """Machine-readable description of the current sandbox policy."""
    return {
        "allowed_modules": sorted(ALLOWED_MODULES),
        "forbidden_names": sorted(FORBIDDEN_NAMES),
        "static_audit": True,
        "subprocess_isolation": False,
        "note": "static AST audit only; subprocess sandbox with resource limits is TODO(M4/M5)",
    }
