import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Grid3X3, Layers, PieChart, Play, ShieldCheck, Sigma } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { isApiError } from "../api/client";
import { useAttribution, useExperiments, useFactor, useFactorCorrelation, useSweep, useWalkForward } from "../api/queries";
import {
  Badge, Button, Chart, ChartCard, EmptyState, Field, Input, PageHeader, Panel, Select, Skeleton,
  StatTile, Tabs, Textarea, type ChartSeries,
} from "../components";
import RobustnessPanel from "../components/RobustnessPanel";
import { useChartPalette } from "../theme";
import { useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

type Tab = "factor" | "sweep" | "walk" | "attribution" | "robust";
const TABS = [
  { id: "factor", label: "因子诊断", icon: Sigma },
  { id: "sweep", label: "参数扫描", icon: Grid3X3 },
  { id: "walk", label: "滚动验证", icon: Layers },
  { id: "attribution", label: "归因", icon: PieChart },
  { id: "robust", label: "稳健性", icon: ShieldCheck },
];
const TEMPLATE_OPTIONS = [
  { value: "momentum", label: "动量" },
  { value: "dual_ma", label: "双均线" },
  { value: "low_vol", label: "低波动" },
  { value: "multi_factor", label: "多因子" },
];
const dateText = (value: number) => {
  const text = String(value);
  return text.length === 8 ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}` : text;
};
const pct = (value: number) => `${(value * 100).toFixed(2)}%`;

function BarList({ rows, valueFormatter }: { rows: Array<{ label: string; value: number | null; hint?: string }>; valueFormatter: (value: number) => string }) {
  const finite = rows.map((row) => row.value).filter((value): value is number => value != null && Number.isFinite(value));
  const max = Math.max(...finite.map((value) => Math.abs(value)), 1e-9);
  return (
    <div className="bar-list">
      {rows.map((row) => {
        const value = row.value;
        const ratio = value == null || !Number.isFinite(value) ? 0 : Math.abs(value) / max;
        return (
          <div className="bar-row" key={row.label}>
            <span className="bar-label" title={row.label}>{row.label}</span>
            <span className="bar-track"><span className={`bar-fill ${(value ?? 0) >= 0 ? "up-bg" : "down-bg"}`} style={{ width: `${Math.max(ratio * 100, value == null ? 0 : 2)}%` }} /></span>
            <span className={`bar-value ${(value ?? 0) >= 0 ? "up" : "down"}`}>{value == null ? "—" : valueFormatter(value)}{row.hint ? <small>{row.hint}</small> : null}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ResearchPage() {
  const [searchParams] = useSearchParams();
  const requestedRun = searchParams.get("run") || "";
  const palette = useChartPalette();
  const beginner = useBeginner();
  const [tab, setTab] = useState<Tab>(requestedRun ? "robust" : "factor");
  const [formError, setFormError] = useState("");

  const [expression, setExpression] = useState("rank(ret(close,20))");
  const [forwardDays, setForwardDays] = useState("5");
  const [quantiles, setQuantiles] = useState("5");
  const factorMutation = useFactor();
  const factor = factorMutation.data ?? null;
  const [correlationText, setCorrelationText] = useState("rank(ret(close,20))\nrank(std(ret(close,20),20))");
  const [correlationMethod, setCorrelationMethod] = useState<"pearson" | "spearman">("pearson");
  const correlationMutation = useFactorCorrelation();
  const correlation = correlationMutation.data ?? null;

  const [sweepTemplate, setSweepTemplate] = useState("momentum");
  const [gridText, setGridText] = useState('{"top_n": [5, 10, 20], "lookback": [20, 60, 120]}');
  const [sweepMode, setSweepMode] = useState<"grid" | "random">("grid");
  const [sampleSize, setSampleSize] = useState("24");
  const [sweepSeed, setSweepSeed] = useState("42");
  const sweepMutation = useSweep();
  const sweep = sweepMutation.data ?? null;

  const [walkTemplate, setWalkTemplate] = useState("momentum");
  const [walkParams, setWalkParams] = useState('{"top_n": 10, "lookback": 60}');
  const [folds, setFolds] = useState("4");
  const walkMutation = useWalkForward();
  const walk = walkMutation.data ?? null;

  const experimentsQuery = useExperiments();
  const experiments = experimentsQuery.data ?? [];
  const [runId, setRunId] = useState(requestedRun);
  const attributionMutation = useAttribution();
  const resetAttribution = attributionMutation.reset;
  const attribution = attributionMutation.data ?? null;
  const busy = factorMutation.isPending || correlationMutation.isPending || sweepMutation.isPending || walkMutation.isPending || attributionMutation.isPending;
  const activeError = tab === "factor" ? factorMutation.error || correlationMutation.error : tab === "sweep" ? sweepMutation.error : tab === "walk" ? walkMutation.error : attributionMutation.error;
  const unimplemented = isApiError(activeError) && activeError.status === 404;
  const errorText = formError || (activeError && !unimplemented ? activeError.message : "");

  useEffect(() => {
    resetAttribution();
  }, [runId, resetAttribution]);
  useEffect(() => {
    if (!requestedRun) return;
    setRunId(requestedRun);
    setTab("robust");
  }, [requestedRun]);
  useEffect(() => {
    if (tab !== "attribution" || runId || !experiments.length) return;
    setRunId(experiments[0].run_id);
  }, [tab, runId, experiments]);

  const runFactor = () => { setFormError(""); factorMutation.mutate({ expression, forward_days: Number(forwardDays), quantiles: Number(quantiles) }); };
  const runSweep = () => {
    setFormError("");
    try {
      sweepMutation.mutate({ template: sweepTemplate, param_grid: JSON.parse(gridText) as Record<string, unknown>, mode: sweepMode, sample_size: sweepMode === "random" ? Number(sampleSize) : 0, seed: Number(sweepSeed), workers: 2 });
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : "参数网格 JSON 无效"); }
  };
  const runCorrelation = () => {
    setFormError("");
    const expressions = correlationText.split("\n").map((line) => line.trim()).filter(Boolean);
    if (expressions.length < 2) { setFormError("因子相关性至少需要两行表达式"); return; }
    correlationMutation.mutate({ expressions, method: correlationMethod });
  };
  const runWalk = () => {
    setFormError("");
    try { walkMutation.mutate({ template: walkTemplate, params: JSON.parse(walkParams) as Record<string, unknown>, folds: Number(folds) }); }
    catch (reason) { setFormError(reason instanceof Error ? reason.message : "参数 JSON 无效"); }
  };
  const runAttribution = () => {
    setFormError("");
    if (!runId) { setFormError("请选择实验"); return; }
    attributionMutation.mutate(runId);
  };

  const icSeries = useMemo<ChartSeries[]>(() => {
    if (!factor) return [];
    const rows = factor.ic_series;
    return [
      { kind: "line", title: "IC", color: palette.accent, data: rows.flatMap((row) => row.ic == null ? [] : [{ time: row.date, value: row.ic }]) },
      { kind: "line", title: "RankIC", color: palette.up, data: rows.flatMap((row) => row.rank_ic == null ? [] : [{ time: row.date, value: row.rank_ic }]) },
    ];
  }, [factor, palette]);
  const sweepKeys = useMemo(() => {
    if (!sweep?.points.length) return [] as string[];
    return Object.keys(sweep.points[0].params);
  }, [sweep]);
  const sweepHeatmap = useMemo(() => {
    if (!sweep?.points.length || sweepKeys.length !== 2) return null;
    const xValues = [...new Set(sweep.points.map((point) => String(point.params[sweepKeys[0]])))];
    const yValues = [...new Set(sweep.points.map((point) => String(point.params[sweepKeys[1]])))];
    const sharpes = sweep.points.map((point) => point.metrics.sharpe);
    const min = Math.min(...sharpes);
    const max = Math.max(...sharpes);
    const span = max - min || 1;
    const cells = sweep.points.map((point) => ({
      x: String(point.params[sweepKeys[0]]),
      y: String(point.params[sweepKeys[1]]),
      sharpe: point.metrics.sharpe,
      ratio: (point.metrics.sharpe - min) / span,
      params: point.params,
    }));
    return { xValues, yValues, cells };
  }, [sweep, sweepKeys]);

  const factorVerdict = useMemo(() => {
    if (!factor) return null;
    const strength = Math.abs(factor.rank_ic_mean);
    const tone = strength >= 0.03 && factor.coverage >= 0.8 ? "ok" : strength >= 0.01 ? "warn" : "danger";
    const verdict = strength >= 0.03 ? "有一定预测力，但仍需样本外验证" : strength >= 0.01 ? "预测力偏弱，谨慎使用" : "基本没有稳定预测力";
    return { tone, verdict, text: `RankIC 均值 ${factor.rank_ic_mean.toFixed(4)}，ICIR ${factor.icir?.toFixed(2) ?? "—"}，覆盖率 ${pct(factor.coverage)}：${verdict}。${factor.coverage < 0.8 ? "覆盖率不足 80%，结论可信度下降。" : ""}IC 只用未来收益做评价，不参与建仓。` };
  }, [factor]);
  const sweepVerdict = useMemo(() => {
    if (!sweep?.best) return null;
    return `网格内最佳 Sharpe ${sweep.best.metrics.sharpe.toFixed(2)}（${JSON.stringify(sweep.best.params)}），总收益 ${pct(sweep.best.metrics.total_return)}。网格最优不等于未来最优，参数越极端越要警惕过拟合。`;
  }, [sweep]);
  const walkVerdict = useMemo(() => {
    if (!walk?.folds.length) return null;
    const positive = walk.folds.filter((fold) => fold.metrics.total_return > 0).length;
    return `${positive} / ${walk.folds.length} 折为正收益；折间表现越一致，策略越可能稳健（样本外近似，不构成保证）。`;
  }, [walk]);
  const attributionVerdict = useMemo(() => {
    if (!attribution?.industries.length) return null;
    const top = [...attribution.industries].sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))[0];
    return `贡献最大的行业是「${top.industry}」（盈亏 ${top.pnl.toFixed(2)}）；按 FIFO 已实现 + 未实现盈亏归因，含费用，属近似研究口径。`;
  }, [attribution]);

  return (
    <div className="page">
      <PageHeader title="研究" subtitle="先看结论：这个因子/参数到底有没有用；再展开图表与明细。" actions={<Badge tone="info">仅研究 · 不构成投资建议</Badge>} />
      <Tabs items={TABS} value={tab} onChange={(id) => { setTab(id as Tab); setFormError(""); }} ariaLabel="研究视图" />
      {errorText ? <p className="error-text" role="alert">{errorText}</p> : null}
      {unimplemented ? <EmptyState title="该研究接口未实现（404）" hint="当前后端版本没有这个能力；页面不会崩溃，请升级后端或使用已有能力。" /> : null}

      {tab === "factor" ? (
        <div className="stack">
          {factorVerdict ? (
            <div className={`conclusion tone-${factorVerdict.tone}`}>
              <div className="conclusion-head"><h2 className="conclusion-title">结论：{factorVerdict.verdict}</h2></div>
              <p className="conclusion-text">{factorVerdict.text}</p>
            </div>
          ) : null}
          <div className="grid grid-2">
            <Panel title="因子诊断" subtitle="输入因子表达式与预测期；IC 用未来收益评价，不参与建仓">
              <div className="stack">
                <Field label="因子表达式" htmlFor="factor-expression">
                  <Textarea id="factor-expression" rows={4} value={expression} onChange={(event) => setExpression(event.target.value)} spellCheck={false} style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }} />
                </Field>
                <div className="grid grid-2">
                  <Field label="预测期（交易日）"><Input value={forwardDays} onChange={(event) => setForwardDays(event.target.value)} inputMode="numeric" aria-label="预测期（交易日）" /></Field>
                  <Field label="分层数"><Input value={quantiles} onChange={(event) => setQuantiles(event.target.value)} inputMode="numeric" aria-label="分层数" /></Field>
                </div>
                <div><Button variant="primary" icon={Play} loading={factorMutation.isPending} disabled={busy} onClick={runFactor}>{factorMutation.isPending ? "计算中…" : "运行诊断"}</Button></div>
                {!beginner ? (
                  <div className="stack">
                    <div className="hairline" />
                    <div className="switch-title">因子相关性</div>
                    <Textarea rows={3} value={correlationText} onChange={(event) => setCorrelationText(event.target.value)} spellCheck={false} aria-label="因子相关性表达式" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }} />
                    <div className="grid grid-2">
                      <Field label="相关方法">
                        <Select value={correlationMethod} onChange={(event) => setCorrelationMethod(event.target.value as "pearson" | "spearman")} options={[{ value: "pearson", label: "Pearson" }, { value: "spearman", label: "Spearman" }]} aria-label="相关方法" />
                      </Field>
                      <div style={{ display: "flex", alignItems: "flex-end" }}><Button variant="secondary" disabled={busy} onClick={runCorrelation}>计算相关性</Button></div>
                    </div>
                  </div>
                ) : <p className="page-note-sm">高级：因子相关性与批量矩阵在专业模式显示。</p>}
              </div>
            </Panel>
            <Panel title="因子结果" subtitle={factor ? `${factor.observations} 个观测 · ${factor.forward_days ?? forwardDays} 日预测期` : "运行后显示 IC/分层/衰减"}>
              {factorMutation.isPending ? <Skeleton rows={4} /> : !factor ? <EmptyState title="还没有因子结果" hint="填写表达式后点「运行诊断」，这里先给 IC 结论再给图表。" /> : (
                <div className="grid grid-2">
                  <StatTile label="IC 均值" value={factor.ic_mean.toFixed(4)} tone={factor.ic_mean >= 0 ? "up" : "down"} />
                  <StatTile label="RankIC 均值" value={factor.rank_ic_mean.toFixed(4)} tone={factor.rank_ic_mean >= 0 ? "up" : "down"} />
                  <StatTile label="ICIR" value={factor.icir?.toFixed(3) ?? "—"} hint={`RankICIR ${factor.rank_icir?.toFixed(3) ?? "—"}`} />
                  <StatTile label="覆盖率" value={pct(factor.coverage)} hint={`${factor.observations} 个观测`} />
                </div>
              )}
            </Panel>
          </div>
          {factor ? (
            <>
              <ChartCard title="IC 时间序列" subtitle="IC 与 RankIC" height={260}>{icSeries.length ? <Chart series={icSeries} height={260} ariaLabel="IC 时间序列" /> : null}</ChartCard>
              <div className="chart-row">
                <Panel title="分层平均收益" subtitle={`${factor.quantiles ?? quantiles} 分层`}>
                  <BarList rows={factor.quantile_returns.map((row) => ({ label: `Q${row.bucket}`, value: row.mean_return == null ? null : row.mean_return * 100, hint: `${row.observations} 样本` }))} valueFormatter={(value) => `${value.toFixed(3)}%`} />
                </Panel>
                <Panel title="因子衰减（RankIC）" subtitle="预测期越长，IC 衰减越快说明信号越短命">
                  <BarList rows={factor.decay.map((row) => ({ label: `${row.days}D`, value: row.rank_ic }))} valueFormatter={(value) => value.toFixed(3)} />
                </Panel>
              </div>
              <Panel title="分层明细" subtitle="各分层平均远期收益与样本数">
                <div className="table-wrap">
                  <table><thead><tr><th>分层</th><th className="num">平均收益</th><th className="num">样本</th></tr></thead>
                    <tbody>{factor.quantile_returns.map((row) => <tr key={row.bucket}><td>Q{row.bucket}</td><td className="num">{row.mean_return == null ? "—" : `${(row.mean_return * 100).toFixed(3)}%`}</td><td className="num">{row.observations}</td></tr>)}</tbody>
                  </table>
                </div>
              </Panel>
            </>
          ) : null}
          {correlation ? (
            <Panel title="因子相关性矩阵" subtitle={`平均 |ρ| ${correlation.average_abs_correlation.toFixed(3)} · ${correlation.periods} 日`}>
              <div className="table-wrap matrix-table">
                <table>
                  <thead><tr><th>因子</th>{correlation.labels.map((label, index) => <th key={index} title={label}>F{index + 1}</th>)}</tr></thead>
                  <tbody>{correlation.matrix.map((row, rowIndex) => <tr key={rowIndex}><td className="mono" title={correlation.labels[rowIndex]}>F{rowIndex + 1}</td>{row.map((value, colIndex) => <td key={colIndex} className={`num ${Math.abs(value) > 0.7 && rowIndex !== colIndex ? "hot" : ""}`}>{value.toFixed(3)}</td>)}</tr>)}</tbody>
                </table>
              </div>
              <p className="corr-note">{correlation.note}。标签：{correlation.labels.map((label, index) => `F${index + 1}=${label}`).join("；")}</p>
            </Panel>
          ) : null}
        </div>
      ) : null}

      {tab === "sweep" ? (
        <div className="stack">
          {sweepVerdict ? <div className="conclusion tone-warn"><div className="conclusion-head"><h2 className="conclusion-title">结论：参数网格已完成</h2></div><p className="conclusion-text">{sweepVerdict}</p></div> : null}
          <div className="grid grid-2">
            <Panel title="参数扫描" subtitle="服务端限制最多 200 个组合；用于研究，不代表未来收益">
              <div className="stack">
                <Field label="模板"><Select value={sweepTemplate} onChange={(event) => setSweepTemplate(event.target.value)} options={TEMPLATE_OPTIONS} aria-label="模板" /></Field>
                <Field label="参数网格 JSON">
                  <Textarea rows={5} value={gridText} onChange={(event) => setGridText(event.target.value)} spellCheck={false} aria-label="参数网格 JSON" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }} />
                </Field>
                <div className="grid grid-2">
                  <Field label="模式"><Select value={sweepMode} onChange={(event) => setSweepMode(event.target.value as "grid" | "random")} options={[{ value: "grid", label: "全网格" }, { value: "random", label: "随机抽样" }]} aria-label="模式" /></Field>
                  {sweepMode === "random"
                    ? <Field label="抽样数"><Input value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} inputMode="numeric" aria-label="抽样数" /></Field>
                    : <Field label="种子"><Input value={sweepSeed} onChange={(event) => setSweepSeed(event.target.value)} inputMode="numeric" aria-label="种子" /></Field>}
                </div>
                <div><Button variant="primary" icon={Play} loading={sweepMutation.isPending} disabled={busy} onClick={runSweep}>{sweepMutation.isPending ? "扫描中…" : "运行扫描"}</Button></div>
              </div>
            </Panel>
            <Panel title="扫描结果" subtitle={sweep ? `${sweep.points.length} 组` : "运行后显示"} actions={sweep?.best ? <Badge tone="ok">最佳 Sharpe {sweep.best.metrics.sharpe.toFixed(2)}</Badge> : null}>
              {sweepMutation.isPending ? <Skeleton rows={5} /> : !sweep ? <EmptyState title="还没有扫描结果" hint="填好参数网格后点「运行扫描」；结果会给出最佳参数和热力图。" /> : (
                <div className="stack">
                  <div className="row">{sweep.sampling ? <Badge tone="neutral">{sweep.sampling.mode === "random" ? `随机 ${sweep.sampling.returned}/${sweep.sampling.requested} seed=${sweep.sampling.seed}` : "全网格"}</Badge> : null}</div>
                  {sweepHeatmap ? (
                    <div className="heatmap">
                      <div className="heatmap-grid" style={{ gridTemplateColumns: `minmax(56px, auto) repeat(${sweepHeatmap.xValues.length}, minmax(44px, 1fr))` }}>
                        <div />
                        {sweepHeatmap.xValues.map((x) => <div className="heatmap-label" key={`x-${x}`} style={{ justifyContent: "center" }}>{x}</div>)}
                        {sweepHeatmap.yValues.map((y) => (
                          <div key={`y-${y}`} style={{ display: "contents" }}>
                            <div className="heatmap-label" key={`label-${y}`}>{y}</div>
                            {sweepHeatmap.xValues.map((x) => {
                              const cell = sweepHeatmap.cells.find((item) => item.x === x && item.y === y);
                              return (
                                <div
                                  key={`${x}-${y}`}
                                  className={`heatmap-cell ${(cell?.sharpe ?? 0) >= 0 ? "positive" : "negative"}`}
                                  style={{ "--heat": cell ? Math.max(0.05, cell.ratio) : 0 } as CSSProperties}
                                  title={cell ? `${JSON.stringify(cell.params)} · Sharpe ${cell.sharpe.toFixed(2)}` : "无数据"}
                                >
                                  {cell ? cell.sharpe.toFixed(2) : "—"}
                                </div>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <BarList rows={sweep.points.slice(0, 20).map((point, index) => ({ label: `#${index + 1} ${JSON.stringify(point.params)}`, value: point.metrics.sharpe }))} valueFormatter={(value) => value.toFixed(2)} />
                  )}
                  <div className="table-wrap">
                    <table><thead><tr><th>参数</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th><th className="num">交易</th></tr></thead>
                      <tbody>{sweep.points.slice(0, 60).map((point, index) => <tr key={index}><td className="mono">{JSON.stringify(point.params)}</td><td className={`num ${point.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(point.metrics.total_return)}</td><td className="num">{point.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(point.metrics.max_drawdown)}</td><td className="num">{point.metrics.trade_count ?? "—"}</td></tr>)}</tbody>
                    </table>
                  </div>
                </div>
              )}
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === "walk" ? (
        <div className="stack">
          {walkVerdict ? <div className="conclusion tone-info"><div className="conclusion-head"><h2 className="conclusion-title">结论：滚动验证完成</h2></div><p className="conclusion-text">{walkVerdict}</p></div> : null}
          <div className="grid grid-2">
            <Panel title="滚动验证" subtitle="把区间切成多折，逐折独立回测，近似样本外表现">
              <div className="stack">
                <Field label="模板"><Select value={walkTemplate} onChange={(event) => setWalkTemplate(event.target.value)} options={TEMPLATE_OPTIONS} aria-label="模板" /></Field>
                <Field label="参数 JSON"><Textarea rows={3} value={walkParams} onChange={(event) => setWalkParams(event.target.value)} spellCheck={false} aria-label="参数 JSON" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }} /></Field>
                <Field label="折数"><Input value={folds} onChange={(event) => setFolds(event.target.value)} inputMode="numeric" aria-label="折数" /></Field>
                <div><Button variant="primary" icon={Play} loading={walkMutation.isPending} disabled={busy} onClick={runWalk}>{walkMutation.isPending ? "验证中…" : "运行滚动验证"}</Button></div>
              </div>
            </Panel>
            <Panel title={walk ? `${walk.template} · ${walk.folds.length} 折` : "滚动验证结果"} subtitle={walk?.aggregate ? `汇总收益 ${pct(walk.aggregate.total_return)} · Sharpe ${walk.aggregate.sharpe.toFixed(2)}` : "运行后显示各折表现"}>
              {walkMutation.isPending ? <Skeleton rows={4} /> : !walk ? <EmptyState title="还没有滚动验证结果" hint="选择模板与折数后点「运行滚动验证」。" /> : (
                <div className="stack">
                  <BarList rows={walk.folds.map((fold) => ({ label: `F${fold.fold}`, value: fold.metrics.total_return * 100 }))} valueFormatter={(value) => `${value.toFixed(2)}%`} />
                  <div className="table-wrap">
                    <table><thead><tr><th>折</th><th>区间</th><th className="num">收益</th><th className="num">Sharpe</th><th className="num">回撤</th><th className="num">交易</th></tr></thead>
                      <tbody>{walk.folds.map((fold) => <tr key={fold.fold}><td>F{fold.fold}</td><td>{dateText(fold.start)} – {dateText(fold.end)}</td><td className={`num ${fold.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(fold.metrics.total_return)}</td><td className="num">{fold.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(fold.metrics.max_drawdown)}</td><td className="num">{fold.trade_count}</td></tr>)}</tbody>
                    </table>
                  </div>
                </div>
              )}
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === "robust" ? <RobustnessPanel experiments={experiments} initialRunId={requestedRun} /> : null}

      {tab === "attribution" ? (
        <div className="stack">
          {attributionVerdict ? <div className="conclusion tone-info"><div className="conclusion-head"><h2 className="conclusion-title">结论：归因完成</h2></div><p className="conclusion-text">{attributionVerdict}</p></div> : null}
          <div className="grid grid-2">
            <Panel title="行业归因" subtitle="按 FIFO 已实现 + 未实现盈亏归因，含费用，近似研究口径">
              <div className="stack">
                <Field label="实验">
                  <Select value={runId} onChange={(event) => setRunId(event.target.value)} options={experiments.map((item) => ({ value: item.run_id, label: `${item.strategy_name || item.template} · ${item.run_id.slice(-8)}` }))} aria-label="实验" />
                </Field>
                <div><Button variant="primary" icon={Play} loading={attributionMutation.isPending} disabled={busy || !runId || experimentsQuery.isLoading} onClick={runAttribution}>{attributionMutation.isPending ? "归因中…" : "运行行业归因"}</Button></div>
                {!experiments.length ? <p className="page-note-sm">还没有实验；先跑一次回测。</p> : null}
              </div>
            </Panel>
            <Panel title={attribution ? `行业贡献 · ${attribution.strategy_name ?? ""}` : "行业贡献"} subtitle={attribution ? `${attribution.industries.length} 个行业` : "选择实验运行归因"}>
              {attributionMutation.isPending ? <Skeleton rows={4} /> : !attribution ? <EmptyState title="还没有归因结果" hint="选择一个实验后点「运行行业归因」。" /> : (
                <div className="stack">
                  <BarList rows={attribution.industries.map((row) => ({ label: row.industry, value: row.pnl }))} valueFormatter={(value) => value.toFixed(2)} />
                  <div className="table-wrap">
                    <table><thead><tr><th>行业</th><th className="num">盈亏</th><th className="num">已实现</th><th className="num">证券数</th></tr></thead>
                      <tbody>{attribution.industries.map((row) => <tr key={row.industry}><td>{row.industry}</td><td className={`num ${row.pnl >= 0 ? "up" : "down"}`}>{row.pnl.toFixed(2)}</td><td className="num">{row.realized.toFixed(2)}</td><td className="num">{row.securities ?? "—"}</td></tr>)}</tbody>
                    </table>
                  </div>
                </div>
              )}
            </Panel>
          </div>
        </div>
      ) : null}
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
