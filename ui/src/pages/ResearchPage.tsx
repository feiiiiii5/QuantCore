import { useEffect, useMemo, useState } from "react";
import { Grid3X3, Layers, PieChart, Play, ShieldCheck, Sigma } from "lucide-react";
import type { EChartsOption } from "echarts";
import { isApiError } from "../api/client";
import { useAttribution, useExperiments, useFactor, useFactorCorrelation, useSweep, useWalkForward } from "../api/queries";
import { Badge, Chart, ChartCard, EmptyState, Panel, Skeleton, StatTile, Tabs } from "../components";
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
const dateText = (value: number) => {
  const text = String(value);
  return text.length === 8 ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}` : text;
};
const pct = (value: number) => `${(value * 100).toFixed(2)}%`;

export default function ResearchPage() {
  const palette = useChartPalette();
  const beginner = useBeginner();
  const [tab, setTab] = useState<Tab>("factor");
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
  const [runId, setRunId] = useState("");
  const attributionMutation = useAttribution();
  const attribution = attributionMutation.data ?? null;
  const busy = factorMutation.isPending || correlationMutation.isPending || sweepMutation.isPending || walkMutation.isPending || attributionMutation.isPending;
  const activeError = tab === "factor" ? factorMutation.error || correlationMutation.error : tab === "sweep" ? sweepMutation.error : tab === "walk" ? walkMutation.error : attributionMutation.error;
  const unimplemented = isApiError(activeError) && activeError.status === 404;
  const errorText = formError || (activeError && !unimplemented ? activeError.message : "");

  useEffect(() => {
    if (tab !== "attribution" || runId || !experiments.length) return;
    setRunId(experiments[0].run_id);
  }, [tab, runId, experiments]);

  const runFactor = () => {
    setFormError("");
    factorMutation.mutate({ expression, forward_days: Number(forwardDays), quantiles: Number(quantiles) });
  };
  const runSweep = () => {
    setFormError("");
    try {
      sweepMutation.mutate({
        template: sweepTemplate,
        param_grid: JSON.parse(gridText) as Record<string, unknown>,
        mode: sweepMode,
        sample_size: sweepMode === "random" ? Number(sampleSize) : 0,
        seed: Number(sweepSeed),
        workers: 2,
      });
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

  const icOption = useMemo<EChartsOption | null>(() => {
    if (!factor) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, legend: { top: 0, data: ["IC", "RankIC"] },
      grid: { left: 48, right: 18, top: 30, bottom: 34 },
      xAxis: { type: "category", data: factor.ic_series.map((row) => dateText(row.date)), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: palette.grid } } },
      series: [
        { name: "IC", type: "line", data: factor.ic_series.map((row) => row.ic), showSymbol: false, lineStyle: { width: 1.2, color: palette.accent } },
        { name: "RankIC", type: "line", data: factor.ic_series.map((row) => row.rank_ic), showSymbol: false, lineStyle: { width: 1.2, color: palette.up } },
      ],
    };
  }, [factor, palette]);
  const quantileOption = useMemo<EChartsOption | null>(() => {
    if (!factor) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: factor.quantile_returns.map((row) => `Q${row.bucket}`) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ type: "bar", data: factor.quantile_returns.map((row) => row.mean_return == null ? null : row.mean_return * 100), itemStyle: { color: palette.accent } }],
    };
  }, [factor, palette]);
  const decayOption = useMemo<EChartsOption | null>(() => {
    if (!factor) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: factor.decay.map((row) => `${row.days}D`) },
      yAxis: { type: "value", scale: true },
      series: [{ type: "line", data: factor.decay.map((row) => row.rank_ic), showSymbol: true, lineStyle: { color: palette.accent } }],
    };
  }, [factor, palette]);
  const sweepKeys = useMemo(() => {
    if (!sweep?.points.length) return [] as string[];
    return Object.keys(sweep.points[0].params);
  }, [sweep]);
  const sweepOption = useMemo<EChartsOption | null>(() => {
    if (!sweep?.points.length) return null;
    if (sweepKeys.length === 1) {
      return {
        animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
        xAxis: { type: "category", data: sweep.points.map((point) => String(point.params[sweepKeys[0]])) },
        yAxis: { type: "value", scale: true },
        series: [{ type: "bar", data: sweep.points.map((point) => point.metrics.sharpe), itemStyle: { color: palette.accent } }],
      };
    }
    if (sweepKeys.length === 2) {
      const xValues = [...new Set(sweep.points.map((point) => String(point.params[sweepKeys[0]])))];
      const yValues = [...new Set(sweep.points.map((point) => String(point.params[sweepKeys[1]])))];
      const data = sweep.points.map((point) => [xValues.indexOf(String(point.params[sweepKeys[0]])), yValues.indexOf(String(point.params[sweepKeys[1]])), point.metrics.sharpe]);
      return {
        animation: false, tooltip: { position: "top" }, grid: { left: 56, right: 20, top: 20, bottom: 40 },
        xAxis: { type: "category", data: xValues }, yAxis: { type: "category", data: yValues },
        visualMap: { min: Math.min(...data.map((row) => Number(row[2]))), max: Math.max(...data.map((row) => Number(row[2]))), calculable: true, orient: "horizontal", left: "center", bottom: 0 },
        series: [{ type: "heatmap", data, label: { show: true, fontSize: 10, formatter: (params: unknown) => { const value = (params as { value?: unknown }).value; return Array.isArray(value) ? Number(value[2]).toFixed(2) : ""; } } }],
      };
    }
    return null;
  }, [sweep, sweepKeys, palette]);
  const walkOption = useMemo<EChartsOption | null>(() => {
    if (!walk?.folds.length) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: walk.folds.map((fold) => `F${fold.fold}`) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ type: "bar", data: walk.folds.map((fold) => fold.metrics.total_return * 100), itemStyle: { color: palette.accent } }],
    };
  }, [walk, palette]);
  const attributionOption = useMemo<EChartsOption | null>(() => {
    if (!attribution) return null;
    return {
      animation: false, tooltip: { trigger: "item" }, legend: { bottom: 0, type: "scroll", textStyle: { fontSize: 10 } },
      series: [{ type: "pie", radius: ["38%", "68%"], data: attribution.industries.map((row) => ({ name: row.industry, value: Math.abs(row.pnl) })) }],
    };
  }, [attribution]);

  const factorVerdict = useMemo(() => {
    if (!factor) return null;
    const strength = Math.abs(factor.rank_ic_mean);
    const tone = strength >= 0.03 && factor.coverage >= 0.8 ? "ok" as const : strength >= 0.01 ? "warn" as const : "danger" as const;
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
      <header className="page-head">
        <div><h1>研究</h1><p className="page-lead">先看结论：这个因子/参数到底有没有用；再展开图表与明细。</p></div>
        <div className="page-head-actions"><Badge tone="info">仅研究 · 不构成投资建议</Badge></div>
      </header>
      <Tabs items={TABS} value={tab} onChange={(id) => { setTab(id as Tab); setFormError(""); }} ariaLabel="研究视图" />
      {errorText ? <p className="error" role="alert">{errorText}</p> : null}
      {unimplemented ? <EmptyState title="该研究接口未实现（404）" hint="当前后端版本没有这个能力；页面不会崩溃，请升级后端或使用已有能力。" /> : null}

      {tab === "factor" ? (
        <>
          {factorVerdict ? <div className={`conclusion tone-${factorVerdict.tone}`}><h2>结论：{factorVerdict.verdict}</h2><p>{factorVerdict.text}</p></div> : null}
          <div className="grid two-col">
            <Panel title="因子诊断" subtitle="输入因子表达式与预测期；IC 用未来收益评价，不参与建仓">
              <label className="field-label" htmlFor="factor-expression">因子表达式</label>
              <textarea id="factor-expression" className="code-input" rows={4} value={expression} onChange={(event) => setExpression(event.target.value)} spellCheck={false} />
              <div className="form-grid two" style={{ marginTop: 10 }}>
                <label>预测期（交易日）<input value={forwardDays} onChange={(event) => setForwardDays(event.target.value)} inputMode="numeric" /></label>
                <label>分层数<input value={quantiles} onChange={(event) => setQuantiles(event.target.value)} inputMode="numeric" /></label>
              </div>
              <button className="btn primary" disabled={busy} onClick={runFactor}><Play size={15} /> {busy ? "计算中…" : "运行诊断"}</button>
              {!beginner ? (
                <>
                  <h3 style={{ marginTop: 16 }}>因子相关性</h3>
                  <textarea className="code-input" rows={3} value={correlationText} onChange={(event) => setCorrelationText(event.target.value)} spellCheck={false} aria-label="因子相关性表达式" />
                  <div className="form-grid two" style={{ marginTop: 8 }}>
                    <label>相关方法<select value={correlationMethod} onChange={(event) => setCorrelationMethod(event.target.value as "pearson" | "spearman")}><option value="pearson">Pearson</option><option value="spearman">Spearman</option></select></label>
                    <label>&nbsp;<button className="btn" disabled={busy} onClick={runCorrelation} aria-label="计算相关性">计算相关性</button></label>
                  </div>
                </>
              ) : <p className="muted small">高级：因子相关性与批量矩阵在专业模式显示。</p>}
            </Panel>
            <Panel title="因子结果" subtitle={factor ? `${factor.observations} 个观测 · ${factor.forward_days ?? forwardDays} 日预测期` : "运行后显示 IC/分层/衰减"}>
              {factorMutation.isPending ? <Skeleton rows={4} /> : !factor ? <EmptyState title="还没有因子结果" hint="填写表达式后点「运行诊断」，这里先给 IC 结论再给图表。" /> : (
                <div className="stat-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
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
              <div className="grid two-col">
                <ChartCard title="IC 时间序列" subtitle="IC 与 RankIC" height={260}>{icOption ? <Chart option={icOption} height={260} /> : null}</ChartCard>
                <ChartCard title="分层平均收益" subtitle={`${factor.quantiles ?? quantiles} 分层`} height={260}>{quantileOption ? <Chart option={quantileOption} height={260} /> : null}</ChartCard>
              </div>
              <div className="grid two-col">
                <ChartCard title="因子衰减（RankIC）" subtitle="预测期越长，IC 衰减越快说明信号越短命" height={240}>{decayOption ? <Chart option={decayOption} height={240} /> : null}</ChartCard>
                <Panel title="分层明细" subtitle="各分层平均远期收益与样本数">
                  <div className="table-wrap"><table><thead><tr><th>分层</th><th className="num">平均收益</th><th className="num">样本</th></tr></thead><tbody>{factor.quantile_returns.map((row) => <tr key={row.bucket}><td>Q{row.bucket}</td><td className="num">{row.mean_return == null ? "—" : `${(row.mean_return * 100).toFixed(3)}%`}</td><td className="num">{row.observations}</td></tr>)}</tbody></table></div>
                </Panel>
              </div>
            </>
          ) : null}
          {correlation ? (
            <Panel title="因子相关性矩阵" subtitle={<span>平均 |ρ| {correlation.average_abs_correlation.toFixed(3)} · {correlation.periods} 日</span>}>
              <div className="table-wrap"><table><thead><tr><th>因子</th>{correlation.labels.map((label, index) => <th key={index} title={label}>F{index + 1}</th>)}</tr></thead><tbody>{correlation.matrix.map((row, rowIndex) => <tr key={rowIndex}><td className="mono" title={correlation.labels[rowIndex]}>F{rowIndex + 1}</td>{row.map((value, colIndex) => <td key={colIndex} className={`num ${Math.abs(value) > 0.7 && rowIndex !== colIndex ? "down" : ""}`}>{value.toFixed(3)}</td>)}</tr>)}</tbody></table></div>
              <p className="muted small">{correlation.note}。标签：{correlation.labels.map((label, index) => `F${index + 1}=${label}`).join("；")}</p>
            </Panel>
          ) : null}
        </>
      ) : null}

      {tab === "sweep" ? (
        <>
          {sweepVerdict ? <div className="conclusion tone-warn"><h2>结论：参数网格已完成</h2><p>{sweepVerdict}</p></div> : null}
          <div className="grid two-col">
            <Panel title="参数扫描" subtitle="服务端限制最多 200 个组合；用于研究，不代表未来收益">
              <label className="field-label">模板</label>
              <select value={sweepTemplate} onChange={(event) => setSweepTemplate(event.target.value)}><option value="momentum">动量</option><option value="dual_ma">双均线</option><option value="low_vol">低波动</option><option value="multi_factor">多因子</option></select>
              <label className="field-label">参数网格 JSON</label>
              <textarea className="code-input" rows={5} value={gridText} onChange={(event) => setGridText(event.target.value)} spellCheck={false} />
              <div className="form-grid two" style={{ marginTop: 8 }}>
                <label>模式<select value={sweepMode} onChange={(event) => setSweepMode(event.target.value as "grid" | "random")}><option value="grid">全网格</option><option value="random">随机抽样</option></select></label>
                {sweepMode === "random" ? <label>抽样数<input value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} inputMode="numeric" /></label> : <label>种子<input value={sweepSeed} onChange={(event) => setSweepSeed(event.target.value)} inputMode="numeric" /></label>}
              </div>
              <button className="btn primary" disabled={busy} onClick={runSweep}><Play size={15} /> {busy ? "扫描中…" : "运行扫描"}</button>
            </Panel>
            <Panel title="扫描结果" subtitle={sweep ? `${sweep.points.length} 组` : "运行后显示"} actions={sweep?.best ? <Badge tone="ok">最佳 Sharpe {sweep.best.metrics.sharpe.toFixed(2)}</Badge> : null}>
              {sweepMutation.isPending ? <Skeleton rows={5} /> : !sweep ? <EmptyState title="还没有扫描结果" hint="填好参数网格后点「运行扫描」；结果会给出最佳参数和热力图。" /> : (
                <>
                  <div className="row" style={{ marginBottom: 8 }}>{sweep.sampling ? <Badge tone="neutral">{sweep.sampling.mode === "random" ? `随机 ${sweep.sampling.returned}/${sweep.sampling.requested} seed=${sweep.sampling.seed}` : "全网格"}</Badge> : null}</div>
                  {sweepOption ? <Chart option={sweepOption} height={300} /> : null}
                  <div className="table-wrap" style={{ marginTop: 8 }}><table><thead><tr><th>参数</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th><th className="num">交易</th></tr></thead><tbody>{sweep.points.slice(0, 60).map((point, index) => <tr key={index}><td className="mono">{JSON.stringify(point.params)}</td><td className={`num ${point.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(point.metrics.total_return)}</td><td className="num">{point.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(point.metrics.max_drawdown)}</td><td className="num">{point.metrics.trade_count ?? "—"}</td></tr>)}</tbody></table></div>
                </>
              )}
            </Panel>
          </div>
        </>
      ) : null}

      {tab === "walk" ? (
        <>
          {walkVerdict ? <div className="conclusion tone-info"><h2>结论：滚动验证完成</h2><p>{walkVerdict}</p></div> : null}
          <div className="grid two-col">
            <Panel title="滚动验证" subtitle="把区间切成多折，逐折独立回测，近似样本外表现">
              <label className="field-label">模板</label>
              <select value={walkTemplate} onChange={(event) => setWalkTemplate(event.target.value)}><option value="momentum">动量</option><option value="dual_ma">双均线</option><option value="low_vol">低波动</option><option value="multi_factor">多因子</option></select>
              <label className="field-label">参数 JSON</label>
              <textarea className="code-input" rows={3} value={walkParams} onChange={(event) => setWalkParams(event.target.value)} spellCheck={false} />
              <label className="field-label">折数<input value={folds} onChange={(event) => setFolds(event.target.value)} inputMode="numeric" /></label>
              <button className="btn primary" disabled={busy} onClick={runWalk}><Play size={15} /> {busy ? "验证中…" : "运行滚动验证"}</button>
            </Panel>
            <Panel title={walk ? `${walk.template} · ${walk.folds.length} 折` : "滚动验证结果"} subtitle={walk?.aggregate ? `汇总收益 ${pct(walk.aggregate.total_return)} · Sharpe ${walk.aggregate.sharpe.toFixed(2)}` : "运行后显示各折表现"}>
              {walkMutation.isPending ? <Skeleton rows={4} /> : !walk ? <EmptyState title="还没有滚动验证结果" hint="选择模板与折数后点「运行滚动验证」。" /> : (
                <>
                  {walkOption ? <Chart option={walkOption} height={260} /> : null}
                  <div className="table-wrap"><table><thead><tr><th>折</th><th>区间</th><th className="num">收益</th><th className="num">Sharpe</th><th className="num">回撤</th><th className="num">交易</th></tr></thead><tbody>{walk.folds.map((fold) => <tr key={fold.fold}><td>F{fold.fold}</td><td>{dateText(fold.start)} – {dateText(fold.end)}</td><td className={`num ${fold.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(fold.metrics.total_return)}</td><td className="num">{fold.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(fold.metrics.max_drawdown)}</td><td className="num">{fold.trade_count}</td></tr>)}</tbody></table></div>
                </>
              )}
            </Panel>
          </div>
        </>
      ) : null}

      {tab === "robust" ? <RobustnessPanel experiments={experiments} /> : null}

      {tab === "attribution" ? (
        <>
          {attributionVerdict ? <div className="conclusion tone-info"><h2>结论：归因完成</h2><p>{attributionVerdict}</p></div> : null}
          <div className="grid two-col">
            <Panel title="行业归因" subtitle="按 FIFO 已实现 + 未实现盈亏归因，含费用，近似研究口径">
              <label className="field-label">实验</label>
              <select value={runId} onChange={(event) => setRunId(event.target.value)}>{experiments.map((item) => <option key={item.run_id} value={item.run_id}>{item.strategy_name || item.template} · {item.run_id.slice(-8)}</option>)}</select>
              <button className="btn primary" style={{ marginTop: 12 }} disabled={busy || !runId || experimentsQuery.isLoading} onClick={runAttribution}><Play size={15} /> {busy ? "归因中…" : "运行行业归因"}</button>
              {!experiments.length ? <p className="muted small">还没有实验；先跑一次回测。</p> : null}
            </Panel>
            <Panel title={attribution ? `行业贡献 · ${attribution.strategy_name ?? ""}` : "行业贡献"} subtitle={attribution ? `${attribution.industries.length} 个行业` : "选择实验运行归因"}>
              {attributionMutation.isPending ? <Skeleton rows={4} /> : !attribution ? <EmptyState title="还没有归因结果" hint="选择一个实验后点「运行行业归因」。" /> : (
                <>
                  {attributionOption ? <Chart option={attributionOption} height={300} /> : null}
                  <div className="table-wrap"><table><thead><tr><th>行业</th><th className="num">盈亏</th><th className="num">已实现</th><th className="num">证券数</th></tr></thead><tbody>{attribution.industries.map((row) => <tr key={row.industry}><td>{row.industry}</td><td className={`num ${row.pnl >= 0 ? "up" : "down"}`}>{row.pnl.toFixed(2)}</td><td className="num">{row.realized.toFixed(2)}</td><td className="num">{row.securities ?? "—"}</td></tr>)}</tbody></table></div>
                </>
              )}
            </Panel>
          </div>
        </>
      ) : null}
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
