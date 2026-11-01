import { useEffect, useMemo, useState } from "react";
import { Grid3X3, Layers, PieChart, Play, ShieldCheck, Sigma } from "lucide-react";
import type { EChartsOption } from "echarts";
import { isApiError } from "../api/client";
import { useAttribution, useExperiments, useFactor, useFactorCorrelation, useSweep, useWalkForward } from "../api/queries";
import Chart from "../components/Chart";
import RobustnessPanel from "../components/RobustnessPanel";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

type Tab = "factor" | "sweep" | "walk" | "attribution" | "robust";
const TABS: Array<{ id: Tab; label: string; icon: typeof Sigma }> = [
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
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
      series: [
        { name: "IC", type: "line", data: factor.ic_series.map((row) => row.ic), showSymbol: false, lineStyle: { width: 1.2, color: "#2563eb" } },
        { name: "RankIC", type: "line", data: factor.ic_series.map((row) => row.rank_ic), showSymbol: false, lineStyle: { width: 1.2, color: "#eab308" } },
      ],
    };
  }, [factor]);
  const quantileOption = useMemo<EChartsOption | null>(() => {
    if (!factor) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: factor.quantile_returns.map((row) => `Q${row.bucket}`) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ type: "bar", data: factor.quantile_returns.map((row) => row.mean_return == null ? null : row.mean_return * 100), itemStyle: { color: "#2563eb" } }],
    };
  }, [factor]);
  const decayOption = useMemo<EChartsOption | null>(() => {
    if (!factor) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: factor.decay.map((row) => `${row.days}D`) },
      yAxis: { type: "value", scale: true },
      series: [{ type: "line", data: factor.decay.map((row) => row.rank_ic), showSymbol: true, lineStyle: { color: "#2563eb" } }],
    };
  }, [factor]);

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
        series: [{ type: "bar", data: sweep.points.map((point) => point.metrics.sharpe), itemStyle: { color: "#2563eb" } }],
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
  }, [sweep, sweepKeys]);

  const walkOption = useMemo<EChartsOption | null>(() => {
    if (!walk?.folds.length) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 18, top: 24, bottom: 30 },
      xAxis: { type: "category", data: walk.folds.map((fold) => `F${fold.fold}`) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ type: "bar", data: walk.folds.map((fold) => fold.metrics.total_return * 100), itemStyle: { color: "#2563eb" } }],
    };
  }, [walk]);

  const attributionOption = useMemo<EChartsOption | null>(() => {
    if (!attribution) return null;
    return {
      animation: false, tooltip: { trigger: "item" }, legend: { bottom: 0, type: "scroll", textStyle: { fontSize: 10 } },
      series: [{ type: "pie", radius: ["38%", "68%"], data: attribution.industries.map((row) => ({ name: row.industry, value: Math.abs(row.pnl) })) }],
    };
  }, [attribution]);

  return (
    <>
      <div className="page-head"><div><h1>研究</h1><p>因子 IC/分层/衰减 · 参数扫描与热力图 · 滚动验证 · 行业归因</p></div></div>
      <div className="tabs" role="tablist">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setFormError(""); }}><Icon size={15} /> {label}</button>)}
      </div>
      {errorText ? <p className="error" role="alert">{errorText}</p> : null}
      {unimplemented ? <StatePanel empty emptyHint="该研究接口在当前后端版本未实现（404）；页面不会崩溃。请升级后端或使用已有能力。" /> : null}
      {tab === "factor" ? (
        <div className="grid two-col">
          <div className="card">
            <label className="field-label">因子表达式</label>
            <textarea className="code-input" rows={4} value={expression} onChange={(e) => setExpression(e.target.value)} spellCheck={false} />
            <div className="form-grid two" style={{ marginTop: 10 }}>
              <label>预测期（交易日）<input value={forwardDays} onChange={(e) => setForwardDays(e.target.value)} inputMode="numeric" /></label>
              <label>分层数<input value={quantiles} onChange={(e) => setQuantiles(e.target.value)} inputMode="numeric" /></label>
            </div>
            <button className="btn primary" disabled={busy} onClick={runFactor}><Play size={15} /> {busy ? "计算中…" : "运行诊断"}</button>
            <p className="muted small">IC 使用未来收益做评价，不参与建仓，避免前视偏差。</p>
            <h3 style={{ marginTop: 16 }}>因子相关性</h3>
            <textarea className="code-input" rows={3} value={correlationText} onChange={(e) => setCorrelationText(e.target.value)} spellCheck={false} aria-label="因子相关性表达式" />
            <div className="form-grid two" style={{ marginTop: 8 }}>
              <label>相关方法<select value={correlationMethod} onChange={(e) => setCorrelationMethod(e.target.value as "pearson" | "spearman")}><option value="pearson">Pearson</option><option value="spearman">Spearman</option></select></label>
              <label>&nbsp;<button className="btn" disabled={busy} onClick={runCorrelation} aria-label="计算相关性">计算相关性</button></label>
            </div>
          </div>
          <div className="card">
            {!factor ? <StatePanel empty emptyHint="运行因子诊断查看 IC/分层/衰减" /> : (
              <div className="grid kpis">
                <div className="card"><h3>IC 均值</h3><div className={`kpi ${factor.ic_mean >= 0 ? "up" : "down"}`}>{factor.ic_mean.toFixed(4)}</div></div>
                <div className="card"><h3>RankIC 均值</h3><div className={`kpi ${factor.rank_ic_mean >= 0 ? "up" : "down"}`}>{factor.rank_ic_mean.toFixed(4)}</div></div>
                <div className="card"><h3>ICIR</h3><div className="kpi">{factor.icir?.toFixed(3) ?? "—"}</div></div>
                <div className="card"><h3>覆盖率</h3><div className="kpi">{pct(factor.coverage)}</div></div>
              </div>
            )}
          </div>
          {correlation ? (
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <div className="card-head"><h3>因子相关性矩阵</h3><span className="badge">平均 |ρ| {correlation.average_abs_correlation.toFixed(3)} · {correlation.periods} 日</span></div>
              <div className="table-wrap"><table><thead><tr><th>因子</th>{correlation.labels.map((label, index) => <th key={index} title={label}>F{index + 1}</th>)}</tr></thead><tbody>{correlation.matrix.map((row, rowIndex) => <tr key={rowIndex}><td className="mono" title={correlation.labels[rowIndex]}>F{rowIndex + 1}</td>{row.map((value, colIndex) => <td key={colIndex} className={`num ${Math.abs(value) > 0.7 && rowIndex !== colIndex ? "down" : ""}`}>{value.toFixed(3)}</td>)}</tr>)}</tbody></table></div>
              <p className="muted small">{correlation.note}。标签：{correlation.labels.map((label, index) => `F${index + 1}=${label}`).join("；")}</p>
            </div>
          ) : null}
          {factor ? (
            <>
              <div className="card"><h3>IC 时间序列</h3>{icOption ? <Chart option={icOption} height={260} /> : null}</div>
              <div className="card"><h3>分层平均收益</h3>{quantileOption ? <Chart option={quantileOption} height={260} /> : null}</div>
              <div className="card"><h3>因子衰减（RankIC）</h3>{decayOption ? <Chart option={decayOption} height={240} /> : null}</div>
              <div className="card"><h3>分层明细</h3><div className="table-wrap"><table><thead><tr><th>分层</th><th className="num">平均收益</th><th className="num">样本</th></tr></thead><tbody>{factor.quantile_returns.map((row) => <tr key={row.bucket}><td>Q{row.bucket}</td><td className="num">{row.mean_return == null ? "—" : `${(row.mean_return * 100).toFixed(3)}%`}</td><td className="num">{row.observations}</td></tr>)}</tbody></table></div></div>
            </>
          ) : null}
        </div>
      ) : null}
      {tab === "sweep" ? (
        <div className="grid two-col">
          <div className="card">
            <label className="field-label">模板</label>
            <select value={sweepTemplate} onChange={(e) => setSweepTemplate(e.target.value)}><option value="momentum">动量</option><option value="dual_ma">双均线</option><option value="low_vol">低波动</option><option value="multi_factor">多因子</option></select>
            <label className="field-label">参数网格 JSON</label>
            <textarea className="code-input" rows={5} value={gridText} onChange={(e) => setGridText(e.target.value)} spellCheck={false} />
            <div className="form-grid two" style={{ marginTop: 8 }}>
              <label>模式<select value={sweepMode} onChange={(e) => setSweepMode(e.target.value as "grid" | "random")}><option value="grid">全网格</option><option value="random">随机抽样</option></select></label>
              {sweepMode === "random" ? <label>抽样数<input value={sampleSize} onChange={(e) => setSampleSize(e.target.value)} inputMode="numeric" /></label> : <label>种子<input value={sweepSeed} onChange={(e) => setSweepSeed(e.target.value)} inputMode="numeric" /></label>}
            </div>
            {sweepMode === "random" ? <label className="field-label">随机种子<input value={sweepSeed} onChange={(e) => setSweepSeed(e.target.value)} inputMode="numeric" /></label> : null}
            <button className="btn primary" disabled={busy} onClick={runSweep}><Play size={15} /> {busy ? "扫描中…" : "运行扫描"}</button>
            <p className="muted small">服务端限制最多 200 个组合；结果用于研究，不代表未来收益。</p>
          </div>
          <div className="card">
            {!sweep ? <StatePanel empty emptyHint="运行参数扫描" /> : (
              <>
                <div className="card-head"><h3>扫描结果 <span className="muted small">{sweep.points.length} 组</span></h3><span className="button-row">{sweep.sampling ? <span className="badge">{sweep.sampling.mode === "random" ? `随机 ${sweep.sampling.returned}/${sweep.sampling.requested} seed=${sweep.sampling.seed}` : "全网格"}</span> : null}{sweep.best ? <span className="badge success">最佳 Sharpe {sweep.best.metrics.sharpe.toFixed(2)}</span> : null}</span></div>
                {sweepOption ? <Chart option={sweepOption} height={300} /> : null}
                <div className="table-wrap" style={{ marginTop: 8 }}><table><thead><tr><th>参数</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th><th className="num">交易</th></tr></thead><tbody>{sweep.points.slice(0, 60).map((point, index) => <tr key={index}><td className="mono">{JSON.stringify(point.params)}</td><td className={`num ${point.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(point.metrics.total_return)}</td><td className="num">{point.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(point.metrics.max_drawdown)}</td><td className="num">{point.metrics.trade_count ?? "—"}</td></tr>)}</tbody></table></div>
              </>
            )}
          </div>
        </div>
      ) : null}
      {tab === "walk" ? (
        <div className="grid two-col">
          <div className="card">
            <label className="field-label">模板</label>
            <select value={walkTemplate} onChange={(e) => setWalkTemplate(e.target.value)}><option value="momentum">动量</option><option value="dual_ma">双均线</option><option value="low_vol">低波动</option><option value="multi_factor">多因子</option></select>
            <label className="field-label">参数 JSON</label>
            <textarea className="code-input" rows={3} value={walkParams} onChange={(e) => setWalkParams(e.target.value)} spellCheck={false} />
            <label className="field-label">折数<input value={folds} onChange={(e) => setFolds(e.target.value)} inputMode="numeric" /></label>
            <button className="btn primary" disabled={busy} onClick={runWalk}><Play size={15} /> {busy ? "验证中…" : "运行滚动验证"}</button>
          </div>
          <div className="card">
            {!walk ? <StatePanel empty emptyHint="运行滚动验证查看各折表现" /> : (
              <>
                <div className="card-head"><h3>{walk.template} <span className="muted small">{walk.folds.length} 折</span></h3></div>
                {walkOption ? <Chart option={walkOption} height={260} /> : null}
                <div className="table-wrap"><table><thead><tr><th>折</th><th>区间</th><th className="num">收益</th><th className="num">Sharpe</th><th className="num">回撤</th><th className="num">交易</th></tr></thead><tbody>{walk.folds.map((fold) => <tr key={fold.fold}><td>F{fold.fold}</td><td>{dateText(fold.start)} – {dateText(fold.end)}</td><td className={`num ${fold.metrics.total_return >= 0 ? "up" : "down"}`}>{pct(fold.metrics.total_return)}</td><td className="num">{fold.metrics.sharpe.toFixed(2)}</td><td className="num">{pct(fold.metrics.max_drawdown)}</td><td className="num">{fold.trade_count}</td></tr>)}</tbody></table></div>
              </>
            )}
          </div>
        </div>
      ) : null}
      {tab === "robust" ? <RobustnessPanel experiments={experiments} /> : null}
      {tab === "attribution" ? (
        <div className="grid two-col">
          <div className="card">
            <label className="field-label">实验</label>
            <select value={runId} onChange={(e) => setRunId(e.target.value)}>{experiments.map((item) => <option key={item.run_id} value={item.run_id}>{item.strategy_name || item.template} · {item.run_id.slice(-8)}</option>)}</select>
            <button className="btn primary" style={{ marginTop: 12 }} disabled={busy || !runId || experimentsQuery.isLoading} onClick={runAttribution}><Play size={15} /> {busy ? "归因中…" : "运行行业归因"}</button>
            <p className="muted small">按 FIFO 已实现 + 未实现盈亏归因，含费用，近似研究口径。</p>
          </div>
          <div className="card">
            {!attribution ? <StatePanel empty emptyHint="选择实验运行归因" /> : (
              <>
                <div className="card-head"><h3>行业贡献 <span className="muted small">{attribution.strategy_name}</span></h3></div>
                {attributionOption ? <Chart option={attributionOption} height={300} /> : null}
                <div className="table-wrap"><table><thead><tr><th>行业</th><th className="num">盈亏</th><th className="num">已实现</th><th className="num">证券数</th></tr></thead><tbody>{attribution.industries.map((row) => <tr key={row.industry}><td>{row.industry}</td><td className={`num ${row.pnl >= 0 ? "up" : "down"}`}>{row.pnl.toFixed(2)}</td><td className="num">{row.realized.toFixed(2)}</td><td className="num">{row.securities ?? "—"}</td></tr>)}</tbody></table></div>
              </>
            )}
          </div>
        </div>
      ) : null}
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
