"""Local strategy plugins: discovery, static audit and spec construction.

Plugins are ordinary ``.py`` files that a local user places under
``<data_root>/strategies/``.  This module only reads/audits them and builds a
:class:`~quantcore.strategy.spec.StrategySpec`; execution happens through the existing
sandboxed loader and backtest job queue.  The static AST audit is an interface/validation
layer, **not** a security boundary: never point it at code you do not trust.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .sandbox import SandboxIssue, audit_source, sandbox_policy
from .spec import StrategySpec

PLUGIN_SUFFIX = ".py"
PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
INTERFACE_BY_BASE: dict[str, str] = {
    "Strategy": "strategy",
    "PanelWeightStrategy": "panel_weight",
    "EventStrategy": "event",
    "DeclarativeStrategy": "declarative",
}


@dataclass(frozen=True)
class PluginInfo:
    """Static metadata for one local plugin file."""

    name: str
    path: Path
    size_bytes: int
    updated_at: str
    valid: bool
    issues: list[dict[str, Any]] = field(default_factory=list)
    interface: str = "unknown"
    description: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "bytes": self.size_bytes,
            "updated_at": self.updated_at,
            "valid": self.valid,
            "issues": list(self.issues),
            "interface": self.interface,
            "description": self.description,
            "version": self.version,
        }


def plugins_root(data_root: str | Path) -> Path:
    return Path(data_root) / "strategies"


def plugin_policy() -> dict[str, Any]:
    """Machine-readable execution/security policy for local plugins."""
    policy = dict(sandbox_policy())
    policy.update(
        {
            "execution": "local user plugins only; explicit opt-in by placing files in data_root/strategies",
            "network": False,
            "real_orders": False,
            "security_boundary": False,
            "note": (
                "static AST audit only; subprocess isolation/resource limits are TODO. "
                "Only run plugin code you placed yourself. No network or order routing is exposed."
            ),
        }
    )
    return policy


def inspect_plugin(path: str | Path, *, name: str | None = None) -> PluginInfo:
    """Read and audit one plugin file without importing it."""
    target = Path(path).resolve()
    plugin_name = (name or target.stem).strip()
    try:
        stat = target.stat()
        source = target.read_text(encoding="utf-8")
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        size = stat.st_size
    except (OSError, UnicodeError) as exc:
        return PluginInfo(
            name=plugin_name,
            path=target,
            size_bytes=0,
            updated_at="",
            valid=False,
            issues=[SandboxIssue("error", f"cannot read plugin: {exc}", 0).to_dict()],
        )
    issues = audit_source(source, origin=str(target))
    probe = _probe_source(source)
    if probe["interface"] == "unknown" and not any(issue.severity == "error" for issue in issues):
        issues.append(
            SandboxIssue(
                "error",
                "no strategy interface detected: define PLUGIN_INFO, a STRATEGY "
                "variable, create_strategy(), or exactly one Strategy subclass",
                0,
            )
        )
    valid = not any(issue.severity == "error" for issue in issues)
    return PluginInfo(
        name=plugin_name,
        path=target,
        size_bytes=size,
        updated_at=updated_at,
        valid=valid,
        issues=[issue.to_dict() for issue in issues],
        interface=probe["interface"],
        description=probe["description"],
        version=probe["version"],
    )


def list_plugins(root: str | Path) -> list[PluginInfo]:
    """Discover ``*.py`` plugins; one broken file must not fail the whole listing."""
    directory = Path(root)
    if not directory.exists() or not directory.is_dir():
        return []
    rows: list[PluginInfo] = []
    for path in sorted(directory.glob(f"*{PLUGIN_SUFFIX}")):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            rows.append(inspect_plugin(path))
        except Exception as exc:  # never 500 the listing because of one plugin
            rows.append(
                PluginInfo(
                    name=path.stem,
                    path=path.resolve(),
                    size_bytes=0,
                    updated_at="",
                    valid=False,
                    issues=[SandboxIssue("error", f"plugin inspection failed: {exc}", 0).to_dict()],
                )
            )
    return rows


def resolve_plugin_path(root: str | Path, name: str) -> Path:
    """Resolve a plugin stem safely; traversal/absolute/non-.py names raise FileNotFoundError."""
    directory = Path(root).resolve()
    candidate = str(name).strip()
    if candidate.lower().endswith(PLUGIN_SUFFIX):
        candidate = candidate[: -len(PLUGIN_SUFFIX)]
    if (
        not candidate
        or candidate.startswith(".")
        or ".." in candidate
        or "/" in candidate
        or "\\" in candidate
        or not PLUGIN_NAME_RE.fullmatch(candidate)
    ):
        raise FileNotFoundError(f"plugin not found: {name!r}")
    target = (directory / f"{candidate}{PLUGIN_SUFFIX}").resolve()
    if target.parent != directory or not target.is_file():
        raise FileNotFoundError(f"plugin not found: {name!r}")
    return target


def load_plugin_info(root: str | Path, name: str) -> PluginInfo:
    path = resolve_plugin_path(root, name)
    return inspect_plugin(path)


def validate_plugin(root: str | Path, name: str) -> dict[str, Any]:
    info = load_plugin_info(root, name)
    return {
        "name": info.name,
        "path": str(info.path),
        "valid": info.valid,
        "issues": list(info.issues),
        "interface": info.interface,
        "description": info.description,
        "version": info.version,
        "policy": plugin_policy(),
    }


def build_plugin_spec(
    root: str | Path, name: str, params: dict[str, Any] | None = None
) -> StrategySpec:
    """Build a module-backed :class:`StrategySpec` for a validated local plugin."""
    info = load_plugin_info(root, name)
    if not info.valid:
        details = "; ".join(
            f"{issue.get('message', '')} (line {issue.get('line', 0)})" for issue in info.issues[:3]
        )
        raise ValueError(f"plugin {info.name!r} failed static validation: {details}")
    return StrategySpec(
        name=info.name,
        module=str(info.path),
        params=dict(params or {}),
        description=info.description or "",
        version=info.version or "1",
    )


# --------------------------------------------------------------------------- probe
def _probe_source(source: str) -> dict[str, Any]:
    """Static, import-free interface/description/version probe."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"interface": "unknown", "description": None, "version": None}
    info: dict[str, Any] = {}
    has_strategy = False
    has_factory = False
    mapped_bases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "PLUGIN_INFO":
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    value = None
                if isinstance(value, dict):
                    info = {str(key): item for key, item in value.items()}
            elif isinstance(target, ast.Name) and target.id == "STRATEGY":
                has_strategy = True
        elif isinstance(node, ast.FunctionDef) and node.name == "create_strategy":
            has_factory = True
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = _last_name(base)
                if base_name in INTERFACE_BY_BASE:
                    mapped_bases.add(INTERFACE_BY_BASE[base_name])

    raw_interface = info.get("interface")
    interface = str(raw_interface).strip() if isinstance(raw_interface, str) else ""
    if not interface:
        if has_strategy:
            interface = "strategy"
        elif has_factory:
            interface = "factory"
        elif len(mapped_bases) == 1:
            interface = next(iter(mapped_bases))
        else:
            interface = "unknown"

    description: str | None = None
    if isinstance(info.get("description"), str) and str(info["description"]).strip():
        description = str(info["description"]).strip()
    else:
        docstring = ast.get_docstring(tree)
        if docstring:
            description = docstring.strip().splitlines()[0][:160]
    version = info.get("version")
    return {
        "interface": interface,
        "description": description,
        "version": str(version).strip() if isinstance(version, (str, int, float)) else None,
    }


def _last_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _last_name(node.value)
    return ""


__all__ = [
    "INTERFACE_BY_BASE",
    "PLUGIN_SUFFIX",
    "PluginInfo",
    "build_plugin_spec",
    "inspect_plugin",
    "list_plugins",
    "load_plugin_info",
    "plugin_policy",
    "plugins_root",
    "resolve_plugin_path",
    "validate_plugin",
]
