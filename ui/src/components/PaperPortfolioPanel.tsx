import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { usePaperPortfolio } from "../api/queries";
import type { PaperSessionSummary } from "../api/types";
import Chart from "./Chart";
import { chartToken } from "../lib/tokens";
import StatePanel from "./StatePanel";

const pct = (value: number | undefined) => `${((value ?? 0) * 100).toFixed(2)}%`;
const money = (value: number | undefined) => `¥${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function PaperPortfolioPanel({ sessions }: { sessions: PaperSessionSummary[] }) {
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const portfolio = usePaperPortfolio();
  const pickedIds = Object.keys(picked).filter((id) => picked[id] !== "" && Number.isFinite(Number(picked[id])) && Number(picked[id]) > 0);
  const totalWeight = pickedIds.reduce((sum, id) => sum + Number(picked[id] || 0), 0);

  const toggle = (id: string) => {
    setPicked((current) => {
      const next = { ...current };
      if (id in next) delete next[id];
      else next[id] = (1 / Math.max(sessions.length, 2)).toFixed(2);
      return next;
    });
  };
  const run = () => {
    setError("");
    if (pickedIds.length < 2) { setError("至少选择两个模拟会话"); return; }
    if (Math.abs(totalWeight - 1) > 1e-6) { setError(`权重之和必须为 1（当前 ${totalWeight.toFixed(4)}）`); return; }
    portfolio.mutate(
      { allocations: pickedIds.map((id) => ({ session_id: id, weight: Number(picked[id]) })) },
      { onError: (reason) => setError(reason.message) },
    );
  };
  const result = portfolio.data;
  const option = useMemo<EChartsOption | null>(() => {
    if (!result?.equity.length) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 70, right: 20, top: 24, bottom: 32 },
      xAxis: { type: "category", data: result.dates.map((date) => String(date)), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
      series: [{ type: "line", data: result.equity, showSymbol: false, lineStyle: { width: 1.8, color: chartToken("--primary", "#2563eb") }, areaStyle: { opacity: 0.07 } }],
    };
  }, [result]);

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="card-head"><h3>多策略组合视图</h3><span className="muted small">只读聚合 · 归一化净值 · 不写回账户</span></div>
      <p className="muted small">选择多个模拟会话并分配权重（总和=1），聚合为组合权益曲线，用于比较不同策略/模拟账户；不产生新委托，不构成投资建议。</p>
      <div className="grid two-col">
        <div>
          <div className="pbo-list">
            {sessions.map((session) => (
              <label key={session.id} className="check-row">
                <input type="checkbox" checked={session.id in picked} onChange={() => toggle(session.id)} />
                <span className="truncate">{session.name}</span>
                {session.id in picked ? <input className="input compact" style={{ width: 80 }} value={picked[session.id]} onChange={(event) => setPicked((current) => ({ ...current, [session.id]: event.target.value }))} inputMode="decimal" aria-label={`${session.name} 权重`} /> : null}
              </label>
            ))}
          </div>
          <div className="button-row">
            <button className="btn primary" disabled={portfolio.isPending || sessions.length < 2} onClick={run}>计算组合</button>
            <span className="muted small">权重合计 {totalWeight.toFixed(4)}</span>
          </div>
          {error ? <p className="error">{error}</p> : null}
          {portfolio.error ? <p className="error">{portfolio.error.message}</p> : null}
          {result?.contributions.length ? (
            <div className="table-wrap" style={{ marginTop: 8 }}><table><thead><tr><th>会话</th><th className="num">权重</th><th className="num">收益</th><th className="num">贡献</th></tr></thead><tbody>{result.contributions.map((row) => <tr key={row.session_id}><td>{row.name}</td><td className="num">{pct(row.weight)}</td><td className={`num ${row.total_return >= 0 ? "up" : "down"}`}>{pct(row.total_return)}</td><td className={`num ${row.contribution >= 0 ? "up" : "down"}`}>{pct(row.contribution)}</td></tr>)}</tbody></table></div>
          ) : null}
        </div>
        <div>
          {!result ? <StatePanel empty emptyHint="至少两个已推进的模拟会话才能组合。" /> : (
            <>
              <div className="grid kpis">
                <div><h3>组合收益</h3><div className={`kpi ${result.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(result.metrics.total_return)}</div></div>
                <div><h3>年化</h3><div className="kpi">{pct(result.metrics.annualized_return)}</div></div>
                <div><h3>Sharpe</h3><div className="kpi">{result.metrics.sharpe.toFixed(2)}</div></div>
                <div><h3>最大回撤</h3><div className="kpi down">{pct(result.metrics.max_drawdown)}</div></div>
                <div><h3>终值</h3><div className="kpi">{money(result.equity[result.equity.length - 1])}</div></div>
              </div>
              {option ? <Chart option={option} height={260} /> : null}
              <p className="muted small">{result.note}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
