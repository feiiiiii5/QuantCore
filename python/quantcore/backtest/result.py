"""Normalised backtest result: trades, equity, metrics and rejection reasons."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import BacktestConfig

#: ``qc::RejectReason`` enum values (cpp/include/qcore/engine.h).
REASON_NAMES: dict[int, str] = {
    0: "none",
    1: "suspended",
    2: "limit_up",
    3: "limit_down",
    4: "lot_size",
    5: "t_plus_one",
    6: "insufficient_cash",
    7: "no_quote",
    8: "price_out_of_range",
    9: "min_rebalance",
    10: "canceled",
    11: "max_positions",
    12: "max_weight",
    13: "industry_limit",
    14: "stop_loss",
    15: "stop_take_profit",
    16: "corporate_action",
    255: "unknown",
}

SIDE_NAMES: dict[int, str] = {0: "buy", 1: "sell"}

TRADE_COLUMNS: tuple[str, ...] = (
    "date",
    "sec_index",
    "sec_id",
    "side",
    "side_name",
    "px",
    "px_yuan",
    "qty",
    "amount",
    "amount_yuan",
    "commission",
    "stamp_duty",
    "transfer_fee",
    "other_fee",
    "fee_total",
    "reason",
    "reason_name",
)

METRIC_KEYS: tuple[str, ...] = (
    "total_return",
    "annualized_return",
    "volatility",
    "sharpe",
    "sortino",
    "max_drawdown",
    "calmar",
    "win_rate",
    "profit_factor",
    "turnover",
    "total_fees",
    "trade_count",
    "trading_days",
)


def _as_dict(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    result: dict[str, Any] = {}
    for key in keys:
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result


def _trade_to_dict(trade: Any) -> dict[str, Any]:
    if isinstance(trade, dict):
        return dict(trade)
    names = (
        "date",
        "sec",
        "side",
        "px",
        "qty",
        "amount",
        "commission",
        "stamp_duty",
        "transfer_fee",
        "other_fee",
        "fee_total",
        "reason",
    )
    return {name: getattr(trade, name, 0) for name in names}


def _reasons_to_dict(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): int(v) for k, v in value.items()}
    result: dict[str, int] = {}
    for item in value:
        if isinstance(item, dict):
            reason = int(item.get("reason", 0))
            count = int(item.get("count", 0))
        else:
            reason = int(getattr(item, "reason", 0))
            count = int(getattr(item, "count", 0))
        result[str(reason)] = int(result.get(str(reason), 0)) + count
    return result


@dataclass
class BacktestResult:
    """Result of one C++ engine run, in fixed-point units plus convenient views."""

    dates: np.ndarray
    equity: np.ndarray
    cash: np.ndarray
    market_value: np.ndarray
    trades: pd.DataFrame
    metrics: dict[str, Any]
    reasons: dict[str, int]
    engine_version: str
    seed: int
    engine_backend: str = "cpp"
    config: dict[str, Any] = field(default_factory=dict)
    final_positions: pd.DataFrame = field(default_factory=pd.DataFrame)
    strategy: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, Any] = field(default_factory=dict)

    # -- derived views ----------------------------------------------------
    @property
    def equity_yuan(self) -> np.ndarray:
        return self.equity.astype(np.float64) / 10000.0

    @property
    def returns(self) -> np.ndarray:
        values = self.equity_yuan
        if values.size < 2:
            return np.zeros_like(values)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.zeros_like(values)
            out[1:] = values[1:] / values[:-1] - 1.0
        return out

    @property
    def drawdown(self) -> np.ndarray:
        values = self.equity_yuan
        if values.size == 0:
            return values
        peaks = np.maximum.accumulate(values)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(peaks > 0, values / peaks - 1.0, 0.0)

    def equity_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": self.dates.astype(np.int64),
                "equity": self.equity_yuan,
                "cash": self.cash.astype(np.float64) / 10000.0,
                "market_value": self.market_value.astype(np.float64) / 10000.0,
                "returns": self.returns,
                "drawdown": self.drawdown,
            }
        )

    def summary(self) -> dict[str, Any]:
        payload = {
            "engine_backend": self.engine_backend,
            "engine_version": self.engine_version,
            "seed": self.seed,
            "trading_days": len(self.dates),
            "start": int(self.dates[0]) if len(self.dates) else 0,
            "end": int(self.dates[-1]) if len(self.dates) else 0,
            "initial_cash": self.equity_yuan[0] if len(self.equity) else 0.0,
            "final_equity": self.equity_yuan[-1] if len(self.equity) else 0.0,
            "trade_count": len(self.trades),
            "synthetic": bool((self.snapshot or {}).get("synthetic", False)),
            "metrics": self.metrics,
            "reasons": self.reasons,
            "strategy": self.strategy,
            "snapshot": self.snapshot,
            "benchmark": self.benchmark,
        }
        return payload

    # -- construction -----------------------------------------------------
    @classmethod
    def from_cpp(
        cls,
        result: Any,
        config: BacktestConfig | dict[str, Any] | None = None,
        *,
        sec_ids: list[str] | None = None,
        strategy: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> BacktestResult:
        dates = np.asarray(
            result.dates if not isinstance(result, dict) else result["dates"], dtype=np.int64
        )
        equity = np.asarray(
            result.equity if not isinstance(result, dict) else result["equity"], dtype=np.int64
        )
        cash = np.asarray(
            result.cash if not isinstance(result, dict) else result["cash"], dtype=np.int64
        )
        market_value = np.asarray(
            result.market_value if not isinstance(result, dict) else result["market_value"],
            dtype=np.int64,
        )
        raw_trades = result.trades if not isinstance(result, dict) else result.get("trades", [])
        trade_rows: list[dict[str, Any]] = []
        for raw in raw_trades:
            trade = _trade_to_dict(raw)
            sec_index = int(trade.get("sec", -1))
            side = int(trade.get("side", 0))
            reason = int(trade.get("reason", 0))
            row = {
                "date": int(trade.get("date", 0)),
                "sec_index": sec_index,
                "sec_id": sec_ids[sec_index] if sec_ids and 0 <= sec_index < len(sec_ids) else "",
                "side": side,
                "side_name": SIDE_NAMES.get(side, "unknown"),
                "px": int(trade.get("px", 0)),
                "px_yuan": float(trade.get("px", 0)) / 10000.0,
                "qty": int(trade.get("qty", 0)),
                "amount": int(trade.get("amount", 0)),
                "amount_yuan": float(trade.get("amount", 0)) / 10000.0,
                "commission": int(trade.get("commission", 0)),
                "stamp_duty": int(trade.get("stamp_duty", 0)),
                "transfer_fee": int(trade.get("transfer_fee", 0)),
                "other_fee": int(trade.get("other_fee", 0)),
                "fee_total": int(trade.get("fee_total", 0)),
                "reason": reason,
                "reason_name": REASON_NAMES.get(reason, "unknown"),
            }
            trade_rows.append(row)
        trades = pd.DataFrame(trade_rows, columns=list(TRADE_COLUMNS))
        metrics = _as_dict(
            result.metrics if not isinstance(result, dict) else result.get("metrics"), METRIC_KEYS
        )
        reasons = _reasons_to_dict(
            result.reasons if not isinstance(result, dict) else result.get("reasons")
        )
        final_secs = (
            getattr(result, "final_position_secs", [])
            if not isinstance(result, dict)
            else result.get("final_position_secs", [])
        )
        final_qty = (
            getattr(result, "final_position_qty", [])
            if not isinstance(result, dict)
            else result.get("final_position_qty", [])
        )
        final_rows = []
        for sec, qty in zip(list(final_secs or []), list(final_qty or []), strict=False):
            final_rows.append(
                {
                    "sec_index": int(sec),
                    "sec_id": sec_ids[int(sec)] if sec_ids and 0 <= int(sec) < len(sec_ids) else "",
                    "qty": int(qty),
                    "weight": 0.0,
                }
            )
        final_positions = pd.DataFrame(final_rows)
        if isinstance(config, BacktestConfig):
            config_dict: dict[str, Any] = config.to_dict()
        elif config:
            config_dict = dict(config)
        else:
            config_dict = {}
        return cls(
            dates=dates,
            equity=equity,
            cash=cash,
            market_value=market_value,
            trades=trades,
            metrics=metrics,
            reasons=reasons,
            engine_version=str(
                getattr(result, "engine_version", "unknown")
                if not isinstance(result, dict)
                else result.get("engine_version", "unknown")
            ),
            seed=int(
                getattr(result, "seed", 0)
                if not isinstance(result, dict)
                else result.get("seed", 0)
            ),
            engine_backend="cpp",
            config=config_dict,
            final_positions=final_positions,
            strategy=strategy or {},
            snapshot=snapshot or {},
        )

    # -- persistence ------------------------------------------------------
    def to_parquet(self, directory: str | Path) -> Path:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        self.equity_frame().to_parquet(target / "equity.parquet", index=False)
        self.trades.to_parquet(target / "trades.parquet", index=False)
        if not self.final_positions.empty:
            self.final_positions.to_parquet(target / "positions.parquet", index=False)
        (target / "metrics.json").write_text(
            json.dumps(self.metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self.benchmark:
            (target / "benchmark.json").write_text(
                json.dumps(self.benchmark, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        (target / "provenance.json").write_text(
            json.dumps(
                {
                    "engine_backend": self.engine_backend,
                    "engine_version": self.engine_version,
                    "seed": self.seed,
                    "config": self.config,
                    "strategy": self.strategy,
                    "snapshot": self.snapshot,
                    "reasons": self.reasons,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    @classmethod
    def from_parquet(cls, directory: str | Path) -> BacktestResult:
        target = Path(directory)
        equity_frame = pd.read_parquet(target / "equity.parquet")
        trades = pd.read_parquet(target / "trades.parquet")
        positions_path = target / "positions.parquet"
        final_positions = (
            pd.read_parquet(positions_path) if positions_path.exists() else pd.DataFrame()
        )
        metrics = json.loads((target / "metrics.json").read_text(encoding="utf-8"))
        provenance = json.loads((target / "provenance.json").read_text(encoding="utf-8"))
        benchmark_path = target / "benchmark.json"
        benchmark = (
            json.loads(benchmark_path.read_text(encoding="utf-8"))
            if benchmark_path.exists()
            else {}
        )
        return cls(
            dates=equity_frame["date"].to_numpy(np.int64),
            equity=np.round(equity_frame["equity"].to_numpy(np.float64) * 10000).astype(np.int64),
            cash=np.round(equity_frame["cash"].to_numpy(np.float64) * 10000).astype(np.int64),
            market_value=np.round(equity_frame["market_value"].to_numpy(np.float64) * 10000).astype(
                np.int64
            ),
            trades=trades,
            metrics=metrics,
            reasons=provenance.get("reasons", {}),
            engine_version=provenance.get("engine_version", "unknown"),
            seed=int(provenance.get("seed", 0)),
            engine_backend=provenance.get("engine_backend", "cpp"),
            config=provenance.get("config", {}),
            final_positions=final_positions,
            strategy=provenance.get("strategy", {}),
            snapshot=provenance.get("snapshot", {}),
            benchmark=benchmark,
        )
