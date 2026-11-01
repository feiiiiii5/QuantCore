"""Strategy layer: templates, declarative expressions, interfaces, specs and sandbox."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quantcore.errors import StrategyValidationError
from quantcore.strategy import (
    DeclarativeStrategy,
    EventState,
    EventStrategy,
    PanelView,
    PanelWeightStrategy,
    Strategy,
    UniverseFilter,
    check_lookahead,
    compile_expression,
    load_strategy_module,
    universe_mask,
    validate_weights,
)
from quantcore.strategy.spec import StrategySpec
from quantcore.templates import create_template, list_templates, template_ids

EXPECTED_TEMPLATES = {
    "buy_and_hold",
    "dual_ma",
    "momentum",
    "low_vol",
    "dividend_quality",
    "small_cap_liquidity",
    "multi_factor",
}


def test_seven_templates_contract(small_panel) -> None:
    assert set(template_ids()) == EXPECTED_TEMPLATES
    assert len(list_templates()) == 7
    for template_id in template_ids():
        strategy = create_template(template_id, {})
        weights = strategy.generate_targets(small_panel)
        problems = validate_weights(weights, small_panel.n_time, small_panel.n_sec)
        assert problems == [], f"{template_id}: {problems}"
        rebalance_rows = ~np.isnan(weights).all(axis=1)
        assert rebalance_rows.any(), f"{template_id} produced no rebalances"
        assert not np.isnan(weights[rebalance_rows]).any()
        row_sums = np.nansum(weights[rebalance_rows], axis=1)
        assert (row_sums <= 1.0 + 1e-9).all()
        assert (row_sums > 0).any()
        assert set(strategy.metadata()) >= {"name", "class", "template"}


def test_template_parameter_validation() -> None:
    with pytest.raises(StrategyValidationError):
        create_template("dual_ma", {"short": 20, "long": 5})
    with pytest.raises(StrategyValidationError):
        create_template("momentum", {"unknown_param": 1})
    with pytest.raises(StrategyValidationError):
        create_template("does_not_exist", {})
    strategy = create_template("momentum", {"top_n": 3})
    assert strategy.metadata()["params"]["top_n"] == 3


def test_momentum_top_n(small_panel) -> None:
    strategy = create_template("momentum", {"top_n": 3, "lookback": 60, "skip": 5})
    weights = strategy.generate_targets(small_panel)
    for row in weights:
        if np.isnan(row).all():
            continue
        assert int((row > 0).sum()) <= 3


def test_declarative_strategy(small_panel) -> None:
    strategy = DeclarativeStrategy(
        "close > ma(close, 20) and rank(ret(close, 60)) > 0.6",
        top_n=5,
        rebalance="monthly",
    )
    weights = strategy.generate_targets(small_panel)
    assert validate_weights(weights, small_panel.n_time, small_panel.n_sec) == []
    assert (~np.isnan(weights).all(axis=1)).any()
    expression = compile_expression("rank(zscore(ret(close, 60))) > 0")
    assert "close" in str(expression.explain())


def test_expression_validation_errors() -> None:
    with pytest.raises(StrategyValidationError):
        compile_expression("unknown_field > 1")
    with pytest.raises(StrategyValidationError):
        compile_expression("eval(close)")
    with pytest.raises(StrategyValidationError):
        compile_expression("ma(close)")
    with pytest.raises(StrategyValidationError):
        compile_expression("close >")


def test_panel_weight_strategy(small_panel) -> None:
    matrix = np.full((small_panel.n_time, small_panel.n_sec), np.nan)
    matrix[:, :4] = 0.25
    strategy = PanelWeightStrategy(matrix, name="fixed")
    assert np.array_equal(strategy.generate_targets(small_panel), matrix, equal_nan=True)
    broken = PanelWeightStrategy(np.zeros((3, 3)))
    with pytest.raises((StrategyValidationError, AssertionError)):
        broken.generate_targets(small_panel)


class _MonthlyTopStrategy(EventStrategy):
    """Event strategy used to verify the on_bar seam and causal view."""

    def __init__(self) -> None:
        super().__init__(name="event_top", rebalance="monthly")
        self.view_lengths: list[int] = []

    def on_bar(self, view: PanelView, state: EventState) -> dict[str, float] | None:
        self.view_lengths.append(view.n_time)
        assert view.last_date <= int(view.dates[-1])
        close = view.field("close")
        row = close[-1]
        finite = np.flatnonzero(np.isfinite(row))
        if finite.size == 0:
            return {}
        chosen = finite[:3]
        return {view.sec_ids[index]: 1.0 / len(chosen) for index in chosen}


def test_event_strategy_view_is_causal(small_panel) -> None:
    strategy = _MonthlyTopStrategy()
    weights = strategy.generate_targets(small_panel)
    assert validate_weights(weights, small_panel.n_time, small_panel.n_sec) == []
    assert strategy.view_lengths
    rebalances = np.flatnonzero(~np.isnan(weights).all(axis=1))
    assert len(strategy.view_lengths) == len(rebalances)


def test_universe_filter(small_panel) -> None:
    view = PanelView(small_panel)
    mask = universe_mask(view, UniverseFilter(exclude_st=True, exclude_suspended=True))
    assert mask.shape == (small_panel.n_time, small_panel.n_sec)
    st = view.field("st") > 0.5
    assert not (mask & st).any()
    boards = universe_mask(view, UniverseFilter(boards=("MAIN",)))
    board_by_sec = {
        str(sec): str(board)
        for sec, board in zip(
            small_panel.securities["sec_id"], small_panel.securities["board"], strict=False
        )
    }
    for index, sec in enumerate(view.sec_ids):
        if board_by_sec[sec] != "MAIN":
            assert not boards[:, index].any()


def test_spec_yaml_roundtrip_and_hash() -> None:
    spec = StrategySpec(name="mom", template="momentum", params={"top_n": 5})
    yaml_text = spec.to_yaml()
    loaded = StrategySpec.from_yaml(yaml_text)
    assert loaded.to_dict() == spec.to_dict()
    assert loaded.content_hash() == spec.content_hash()
    changed = StrategySpec(name="mom", template="momentum", params={"top_n": 10})
    assert changed.content_hash() != spec.content_hash()
    schema = StrategySpec.json_schema()
    assert "template" in schema["properties"]
    with pytest.raises(StrategyValidationError):
        StrategySpec.from_yaml("name: bad\ntemplate: momentum\nmodule: x.py\n")


def test_spec_loads_template(small_panel) -> None:
    spec = StrategySpec(name="m", template="low_vol", params={"top_n": 4})
    strategy = spec.load()
    weights = strategy.generate_targets(small_panel)
    assert (~np.isnan(weights).all(axis=1)).any()


def test_spec_loads_sandboxed_module(small_panel, tmp_path: Path) -> None:
    module_path = tmp_path / "custom_strategy.py"
    module_path.write_text(
        "import numpy as np\n"
        "from quantcore.strategy.base import PanelWeightStrategy\n"
        "\n"
        "def weights(panel):\n"
        "    matrix = np.full((panel.n_time, panel.n_sec), np.nan)\n"
        "    matrix[:, :2] = 0.5\n"
        "    return matrix\n"
        "\n"
        "STRATEGY = PanelWeightStrategy(weights, name='custom')\n",
        encoding="utf-8",
    )
    spec = StrategySpec(name="custom", module=str(module_path))
    strategy = spec.load()
    weights = strategy.generate_targets(small_panel)
    assert (~np.isnan(weights).all(axis=1)).all()
    assert spec.content_hash() and spec.content_hash() == spec.content_hash()


def test_sandbox_rejects_forbidden_imports(tmp_path: Path) -> None:
    bad_module = tmp_path / "bad_strategy.py"
    bad_module.write_text(
        "import os\n"
        "from quantcore.strategy.base import PanelWeightStrategy\n"
        "STRATEGY = PanelWeightStrategy(lambda panel: None)\n",
        encoding="utf-8",
    )
    with pytest.raises(StrategyValidationError):
        load_strategy_module(bad_module)


def test_lookahead_templates_pass(small_panel) -> None:
    for template_id in ("dual_ma", "momentum", "low_vol"):
        strategy = create_template(template_id, {})
        report = check_lookahead(strategy, small_panel, n_cuts=3)
        assert report.passed, (template_id, report.to_dict())


def _leaky_weights(panel) -> np.ndarray:
    """A strategy that normalises by the full-sample column maximum (future leak)."""
    close = panel.matrix("close")
    column_max = np.nanmax(close, axis=0, keepdims=True)
    scale = np.where(column_max > 0, close / column_max, 0.0)
    return np.nan_to_num(scale, nan=0.0) * 0.5 / max(1, panel.n_sec)


def test_lookahead_detects_leak(small_panel) -> None:
    strategy = PanelWeightStrategy(_leaky_weights, name="leaky")
    report = check_lookahead(strategy, small_panel, n_cuts=3)
    assert not report.passed
    assert report.mismatches


def test_static_audit_flags_negative_shift(small_panel, tmp_path: Path) -> None:
    module_path = tmp_path / "shift_strategy.py"
    module_path.write_text(
        "import numpy as np\n"
        "from quantcore.strategy.base import PanelWeightStrategy\n"
        "\n"
        "def _unused(close):\n"
        "    return close.shift(-1)\n"
        "\n"
        "def weights(panel):\n"
        "    return np.full((panel.n_time, panel.n_sec), 1.0 / max(1, panel.n_sec))\n"
        "\n"
        "STRATEGY = PanelWeightStrategy(weights, name='shift')\n",
        encoding="utf-8",
    )
    strategy = load_strategy_module(module_path)
    report = check_lookahead(strategy, small_panel, n_cuts=2, source_path=module_path)
    assert report.static_issues
    assert not report.passed


def test_strategy_base_metadata() -> None:
    class Empty(Strategy):
        def generate_weights(self, panel):  # pragma: no cover - not generated here
            return np.zeros((panel.n_time, panel.n_sec))

    strategy = Empty()
    assert strategy.metadata()["class"].endswith("Empty")
    assert strategy.content_hash()
