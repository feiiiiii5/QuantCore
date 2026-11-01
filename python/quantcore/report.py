"""Self-contained HTML report (inline CSS/SVG, no CDN or external fonts).

The report carries the mandatory disclaimers: synthetic datasets are labelled
``SYNTHETIC`` and historical performance is not investment advice.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment
from markupsafe import Markup

from . import INVESTMENT_DISCLAIMER
from .backtest.result import BacktestResult

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{{ title }}</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 24px 32px; color: #17202a; background: #fbfbfd; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 16px; margin: 24px 0 8px; border-bottom: 1px solid #e3e6eb; padding-bottom: 4px; }
  .meta { color: #5b6573; font-size: 12px; line-height: 1.7; }
  .banner { margin: 16px 0; padding: 10px 14px; border-radius: 6px;
            background: #fff4e5; border: 1px solid #f0c36d; font-size: 13px; }
  .banner.ok { background: #e9f7ef; border-color: #a9d7b8; }
  table { border-collapse: collapse; font-size: 13px; margin-top: 6px; }
  th, td { border: 1px solid #e1e5ea; padding: 4px 10px; text-align: right; }
  th:first-child, td:first-child { text-align: left; }
  th { background: #f2f4f7; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .card { background: #fff; border: 1px solid #e6e9ee; border-radius: 8px; padding: 12px; }
  .disclaimer { margin-top: 28px; padding: 12px 16px; color: #6b7280; font-size: 12px;
                border-top: 1px solid #e3e6eb; }
  svg { width: 100%; height: auto; display: block; }
  .num { font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="meta">
  Run: {{ run_label }} · Engine: {{ engine_version }} ({{ engine_backend }}) · Seed: {{ seed }}<br/>
  Data: {{ data_label }} · Generated: {{ generated_at }}
</div>
{% if synthetic %}
<div class="banner">SYNTHETIC DATA: every price, rule and accounting value in this report is
fabricated for development/testing. This is not real market performance.</div>
{% endif %}
{% if warnings %}
<div class="banner">{{ warnings | join(" · ") }}</div>
{% endif %}

<h2>Performance</h2>
<div class="grid">
  <div class="card"><div class="meta">Net value (CNY)</div>{{ equity_svg }}</div>
  <div class="card"><div class="meta">Drawdown</div>{{ drawdown_svg }}</div>
</div>

<h2>Metrics</h2>
<table>
  <tr><th>metric</th><th>value</th></tr>
  {% for key, value in metric_rows %}<tr><td>{{ key }}</td><td class="num">{{ value }}</td></tr>{% endfor %}
</table>

<h2>Trades</h2>
<div class="meta">Fills: {{ trade_count }} · Rejections: {{ rejection_count }}</div>
<table>
  <tr><th>date</th><th>sec</th><th>side</th><th>price</th><th>qty</th><th>fees</th><th>reason</th></tr>
  {% for trade in trades %}<tr><td>{{ trade.date }}</td><td>{{ trade.sec_id }}</td>
  <td>{{ trade.side_name }}</td><td class="num">{{ "%.2f" | format(trade.px_yuan) }}</td>
  <td class="num">{{ trade.qty }}</td><td class="num">{{ "%.2f" | format(trade.fee_yuan) }}</td>
  <td>{{ trade.reason_name }}</td></tr>{% endfor %}
  {% if not trades %}<tr><td colspan="7">no fills</td></tr>{% endif %}
</table>

<h2>Provenance</h2>
<table>
  <tr><th>item</th><th>value</th></tr>
  {% for key, value in provenance_rows %}<tr><td>{{ key }}</td><td>{{ value }}</td></tr>{% endfor %}
</table>

<div class="disclaimer">
  {{ investment_disclaimer }}<br/>
  {{ synthetic_disclaimer }}
</div>
</body>
</html>
"""


def _svg_path(
    values: list[float],
    width: int = 640,
    height: int = 220,
    color: str = "#2f6fed",
    fill: str = "#eaf0ff",
) -> Markup:
    """Render a line chart as inline SVG (no external assets)."""
    if not values:
        values = [0.0]
    finite = [value for value in values if isinstance(value, (int, float)) and value == value]
    if not finite:
        finite = [0.0]
    low, high = min(finite), max(finite)
    if high == low:
        high = low + 1.0
    padding = 8
    inner_w = width - 2 * padding
    inner_h = height - 2 * padding
    step = inner_w / max(1, len(values) - 1)
    points = []
    for index, value in enumerate(values):
        if value != value:  # NaN
            continue
        x = padding + index * step
        y = padding + (1.0 - (value - low) / (high - low)) * inner_h
        points.append(f"{x:.1f},{y:.1f}")
    if not points:
        points = [f"{padding},{height - padding}"]
    path = " ".join(points)
    area = f"{padding},{height - padding} {path} {width - padding},{height - padding}"
    return Markup(
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="chart">'
        f'<polygon points="{area}" fill="{fill}" stroke="none"/>'
        f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.6"/>'
        f"</svg>"
    )


def _metric_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key in (
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
    ):
        if key not in metrics:
            continue
        value = metrics[key]
        if key in {"total_return", "annualized_return", "volatility", "max_drawdown", "win_rate"}:
            rows.append((key, f"{float(value):.4%}"))
        elif key in {"sharpe", "sortino", "calmar", "profit_factor", "turnover"}:
            rows.append((key, f"{float(value):.4f}"))
        elif key == "total_fees":
            rows.append((key, f"{float(value) / 10000.0:.2f} CNY"))
        else:
            rows.append((key, str(value)))
    return rows


def render_html_report(
    result: BacktestResult,
    *,
    output_path: str | Path,
    title: str = "QuantCore backtest report",
    strategy_metadata: dict[str, Any] | None = None,
    snapshot_metadata: dict[str, Any] | None = None,
    run_label: str = "",
) -> Path:
    """Render a self-contained HTML report and return its path."""
    equity = result.equity_yuan
    drawdown = result.drawdown * 100.0
    frames = result.equity_frame()
    metric_rows = _metric_rows(result.metrics)
    trades = []
    for row in result.trades.head(200).to_dict(orient="records"):
        trades.append(
            {
                **row,
                "fee_yuan": float(row.get("fee_total", 0)) / 10000.0,
            }
        )
    rejection_count = int(
        sum(int(value) for key, value in result.reasons.items() if key not in {"0", "9"})
    )
    provenance_rows: list[tuple[str, str]] = []
    for key in (
        "snapshot_id",
        "content_hash",
        "source",
        "synthetic",
        "n_sec",
        "n_time",
        "start",
        "end",
    ):
        if snapshot_metadata and key in snapshot_metadata:
            provenance_rows.append((f"snapshot.{key}", str(snapshot_metadata[key])))
    if strategy_metadata:
        provenance_rows.append(("strategy", str(strategy_metadata.get("name", "unknown"))))
        provenance_rows.append(
            ("strategy_hash", str(strategy_metadata.get("content_hash", ""))[:16])
        )
    provenance_rows.append(("engine_backend", result.engine_backend))
    provenance_rows.append(("engine_version", result.engine_version))
    provenance_rows.append(("seed", str(result.seed)))
    provenance_rows.append(("start_equity_yuan", f"{equity[0]:.2f}" if len(equity) else "0"))
    provenance_rows.append(("end_equity_yuan", f"{equity[-1]:.2f}" if len(equity) else "0"))
    warnings: list[str] = []
    if snapshot_metadata and not snapshot_metadata.get("synthetic", False):
        warnings.append("Data is user supplied; verify provenance before drawing conclusions.")
    environment = Environment(autoescape=True)
    template = environment.from_string(REPORT_TEMPLATE)
    html = template.render(
        title=title,
        run_label=run_label or (snapshot_metadata or {}).get("snapshot_id", "in-memory"),
        engine_version=result.engine_version,
        engine_backend=result.engine_backend,
        seed=result.seed,
        data_label=str((snapshot_metadata or {}).get("source", "unknown")),
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        synthetic=bool((snapshot_metadata or {}).get("synthetic", False)),
        warnings=warnings,
        equity_svg=_svg_path(equity.tolist()),
        drawdown_svg=_svg_path(drawdown.tolist(), color="#c0392b", fill="#fdecea"),
        metric_rows=metric_rows,
        trades=trades,
        trade_count=len(result.trades),
        rejection_count=rejection_count,
        provenance_rows=provenance_rows,
        investment_disclaimer=INVESTMENT_DISCLAIMER,
        synthetic_disclaimer=(
            "SYNTHETIC DATA: not a real market result."
            if (snapshot_metadata or {}).get("synthetic")
            else ""
        ),
        frames=len(frames),
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def report_metadata(result: BacktestResult) -> dict[str, Any]:
    """Small JSON summary of a report-ready result."""
    return {
        "engine_backend": result.engine_backend,
        "engine_version": result.engine_version,
        "metrics": result.metrics,
        "trade_count": len(result.trades),
        "reasons": result.reasons,
        "dates": [int(result.dates[0]), int(result.dates[-1])] if len(result.dates) else [],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def write_json_report(result: BacktestResult, path: str | Path) -> Path:
    target = Path(path)
    target.write_text(
        json.dumps(report_metadata(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
