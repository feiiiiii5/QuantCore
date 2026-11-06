import { useMemo, useState } from "react";
import type { CompareResult, ComparisonStatus, Metrics } from "../api/types";
import { comparisonSeries, comparisonValue, metricDelta, type ComparisonView } from "../lib/experimentComparison";
import { dateInt, money, num, pct } from "../lib/format";
import { chartToken } from "../lib/tokens";
import { Badge, Button, Callout, Chart, ChartCard, EmptyState, Field, Segmented, Select } from "./index";

const COLORS = ["--accent", "--warn", "--ok", "--up"];
const STATUS: Record<ComparisonStatus, { label: string; tone: "ok" | "warn" | "neutral" }> = {
  matched: { label: "条件一致", tone: "ok" },
  different: { label: "条件有差异", tone: "warn" },
  unknown: { label: "记录不完整", tone: "neutral" },
};
const METRICS: Array<{ key: keyof Metrics; label: string; unit: "ratio" | "number" }> = [
  { key: "total_return", label: "总收益", unit: "ratio" },
  { key: "annualized_return", label: "年化收益", unit: "ratio" },
  { key: "max_drawdown", label: "最大回撤", unit: "ratio" },
  { key: "sharpe", label: "Sharpe", unit: "number" },
  { key: "volatility", label: "年化波动", unit: "ratio" },
  { key: "turnover", label: "换手率", unit: "ratio" },
  { key: "trade_count", label: "交易次数", unit: "number" },
];

export default function ExperimentComparison({ result, onOpenRun }: { result: CompareResult; onOpenRun: (runId: string) => void }) {
  const [view, setView] = useState<ComparisonView>("equity");
  const [baseline, setBaseline] = useState(result.ids[0]);
  const activeBaseline = result.ids.includes(baseline) ? baseline : result.ids[0];
  const baselineMetrics = result.metrics[activeBaseline];
  const status = STATUS[result.comparison.status];
  const series = useMemo(() => comparisonSeries(result, view, COLORS.map((color) => chartToken(color, "#0071e3"))), [result, view]);
  const unavailable = result.equity.filter((run) => run.initial_cash == null);
  const different = result.comparison.dimensions.filter((dimension) => dimension.status !== "matched");

  return (
    <div className="stack exp-comparison">
      {result.equity.some((run) => run.provenance.synthetic === true) ? <div className="row"><Badge tone="info">SYNTHETIC · 含合成数据</Badge><span className="page-note-sm">演示研究流程，不能作为真实市场结论。</span></div> : null}
      <Callout tone={result.comparison.status === "matched" ? "info" : "warn"} title={status.label}>
        <p>{result.comparison.status === "matched" ? "已记录的数据、区间与撮合条件一致。下方差值以所选实验为参照，供逐项核对。" : "先核对差异，再解释收益变化。归一化曲线消除了金额单位差异，资金规模仍会影响手数、最低佣金与成交。"}</p>
      </Callout>
      {result.comparison.warnings.length ? (
        <ul className="exp-warnings">{result.comparison.warnings.map((warning, index) => <li key={`${warning.code}-${index}`}>{warning.message}</li>)}</ul>
      ) : null}

      <ChartCard
        title={view === "equity" ? "归一化净值" : "回撤路径"}
        subtitle={view === "equity" ? "权益 ÷ 各自记录的初始资金；初始资金对应 1，不重设首日值。" : "相对历史权益峰值的跌幅，初始资金有记录时纳入峰值；0% 表示未低于此前峰值。"}
        height={300}
        actions={<Segmented ariaLabel="对比曲线" value={view} onChange={(value) => setView(value as ComparisonView)} items={[{ value: "equity", label: "净值" }, { value: "drawdown", label: "回撤" }]} />}
      >
        {series.length ? <Chart series={series} height={300} ariaLabel={view === "equity" ? "归一化实验对比曲线" : "实验回撤对比曲线"} valueFormatter={(value) => view === "equity" ? value.toFixed(3) : `${value.toFixed(2)}%`} /> : <EmptyState compact title="缺少可比较的曲线" hint="需要完整权益序列与已记录的初始资金。" />}
      </ChartCard>
      {unavailable.length ? <p className="page-note">{unavailable.map((run) => run.label).join("、")}未记录有效初始资金。{view === "equity" ? "未绘制归一化净值。" : "回撤从首个已保存权益点计算，无法还原此前的损益。"}</p> : null}

      <div className="row-between">
        <div><h3 className="exp-section-title">指标与差值</h3><p className="page-note-sm">差值 = 本实验 − 参照实验；仅是历史结果差异。</p></div>
        <Field label="参照实验" htmlFor="exp-baseline">
          <Select id="exp-baseline" value={activeBaseline} onChange={(event) => setBaseline(event.target.value)} options={result.equity.map((run, index) => ({ value: run.run_id, label: `${index + 1}. ${run.label}` }))} />
        </Field>
      </div>
      <div className="table-wrap exp-comparison-table" tabIndex={0} aria-label="实验指标对比，可横向滚动">
        <table>
          <caption className="sr-only">各实验指标及相对参照实验的差值</caption>
          <thead><tr><th scope="col">指标</th>{result.equity.map((run, index) => <th scope="col" key={run.run_id}><span className="exp-run-label">{index + 1}. {run.label}</span>{run.run_id === activeBaseline ? <Badge tone="info">参照</Badge> : null}</th>)}</tr></thead>
          <tbody>{METRICS.map((metric) => (
            <tr key={metric.key}>
              <th scope="row">{metric.label}</th>
              {result.ids.map((id) => {
                const value = result.metrics[id]?.[metric.key];
                return <td key={id} className="num"><strong>{metric.unit === "ratio" ? pct(value) : num(value, metric.key === "trade_count" ? 0 : 2)}</strong>{id !== activeBaseline ? <small className="exp-delta">{metricDelta(value ?? undefined, baselineMetrics?.[metric.key] ?? undefined, metric.unit)}</small> : null}</td>;
              })}
            </tr>
          ))}</tbody>
        </table>
      </div>

      <section className="stack-tight" aria-label="实验条件核对">
        <div className="row-between"><h3 className="exp-section-title">条件核对</h3><Badge tone={status.tone}>{different.length ? `${different.length} 项待核对` : "已记录条件一致"}</Badge></div>
        <details open={different.length > 0} className="exp-assumptions">
          <summary>查看数据、区间、资金与撮合条件</summary>
          <div className="table-wrap" tabIndex={0} aria-label="实验条件对比，可横向滚动">
            <table>
              <thead><tr><th scope="col">条件</th>{result.equity.map((run, index) => <th scope="col" key={run.run_id}>{index + 1}. {run.label}</th>)}</tr></thead>
              <tbody>{result.comparison.dimensions.map((dimension) => (
                <tr key={dimension.key}><th scope="row">{dimension.label}<Badge tone={STATUS[dimension.status].tone}>{STATUS[dimension.status].label}</Badge></th>{result.ids.map((id) => <td key={id}><pre className="exp-value">{comparisonValue(dimension.values[id])}</pre></td>)}</tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      </section>

      <div className="exp-run-sources">
        {result.equity.map((run, index) => (
          <article key={run.run_id} className="exp-run-source">
            <div className="row-between"><strong>{index + 1}. {run.label}</strong><Button variant="ghost" size="sm" onClick={() => onOpenRun(run.run_id)}>查看实验</Button></div>
            <dl className="exp-source-list">
              <div><dt>实际区间</dt><dd>{dateInt(run.dates[0])} → {dateInt(run.dates.at(-1))}</dd></div>
              <div><dt>初始资金</dt><dd>{money(run.initial_cash)}</dd></div>
              <div><dt>数据来源</dt><dd>{run.provenance.source || "未记录"}{run.provenance.synthetic === true ? " · SYNTHETIC" : ""}</dd></div>
              <div><dt>快照指纹</dt><dd className="mono" title={run.provenance.content_hash ?? undefined}>{run.provenance.content_hash || "未记录"}</dd></div>
              <div><dt>策略参数</dt><dd><pre className="exp-value">{comparisonValue(run.provenance.params)}</pre></dd></div>
              <div><dt>策略指纹</dt><dd className="mono">{run.provenance.strategy_hash || "未记录"}</dd></div>
              <div><dt>引擎</dt><dd>{run.provenance.engine_backend || "未记录"} {run.provenance.engine_version}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
