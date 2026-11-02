import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Download, GitCompare, Play, RotateCcw, SlidersHorizontal, Square } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import {
  useBars, useCancelJob, useDataIntegrity, useDataStatus, useExperimentResult,
  useReplayExperiment, useSecurities, useSubmitBacktest, useTemplates,
} from "../api/queries";
import { downloadWithAuth, isApiError } from "../api/client";
import type { BacktestResultPayload, Trade } from "../api/types";
import { Badge, ChartCard, Chart, EmptyState, KLineChart, Panel, Skeleton, StatTile, Tabs, VirtualTable, defaultsFromSchema } from "../components";
import { useJobProgress } from "../hooks/useJobProgress";
import { dateInt, fixedToYuan, money, monthKey, num, pct } from "../lib/format";
import { notify } from "../lib/notify";
import { useChartPalette } from "../theme";
import { useBeginner } from "../store/ui";
import { useWorkspace, type BacktestDraft } from "../store/workspace";
import type { ColumnDef } from "@tanstack/react-table";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const DEFAULTS: BacktestDraft = {
  template: "momentum", paramsText: '{"top_n": 10, "lookback": 60}', start: "2022-01-04", end: "2024-12-31", cash: "1000000",
  exec: "next_open", commissionRate: "0.03", minCommission: "5", stampDutyRate: "0.05", slippageBps: "0", maxParticipation: "1",
  minRebalanceValue: "0", trace: "summary", seed: "42", benchmarkCode: "", maxPositions: "", maxWeight: "",
};
const TAB_ITEMS = [
  { id: "equity", label: "净值与回撤" },
  { id: "monthly", label: "月度收益" },
  { id: "trades", label: "交易明细" },
  { id: "explain", label: "交易解释" },
];

function monthlyReturns(result: BacktestResultPayload): Array<{ month: string; value: number }> {
  const buckets = new Map<string, { first: number; last: number }>();
  result.dates.forEach((date, index) => {
    const key = monthKey(date);
    const equity = result.equity[index];
    const bucket = buckets.get(key);
    if (!bucket) buckets.set(key, { first: equity, last: equity });
    else bucket.last = equity;
  });
  return [...buckets.entries()].map(([month, values]) => ({ month, value: values.first > 0 ? values.last / values.first - 1 : 0 }));
}

export default function BacktestPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const palette = useChartPalette();
  const beginner = useBeginner();
  const templates = useTemplates();
  const submit = useSubmitBacktest();
  const cancel = useCancelJob();
  const replay = useReplayExperiment();
  const securities = useSecurities("", 1000);
  const dataStatus = useDataStatus();
  const integrity = useDataIntegrity();
  const stored = useWorkspace.getState().backtestDraft;
  const [draft, setDraft] = useState<BacktestDraft>(() => ({
    ...DEFAULTS,
    ...stored,
    template: searchParams.get("template") || stored.template || DEFAULTS.template,
    paramsText: searchParams.get("params") || stored.paramsText || DEFAULTS.paramsText,
  }));
  const [snapshot, setSnapshot] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [error, setError] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [tab, setTab] = useState("equity");
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [replayMessage, setReplayMessage] = useState("");
  const [notice, setNotice] = useState("");
  const setDraftStore = useWorkspace((state) => state.setBacktestDraft);
  const progress = useJobProgress(jobId);
  const resetSubmit = submit.reset;
  const resultQuery = useExperimentResult(experimentId || null);
  const result = resultQuery.data ?? null;
  const screenerNote = searchParams.get("screener") || "";

  useEffect(() => { setDraftStore(draft); }, [draft, setDraftStore]);
  useEffect(() => {
    const job = progress.job;
    if (!job) return;
    if (job.status === "done") {
      const runId = typeof job.result?.run_id === "string" ? job.result.run_id : "";
      if (runId) {
        setExperimentId(runId);
        setNotice(`实验已保存：${runId}`);
        notify({ title: "回测完成", body: `结果已写入实验 ${runId.slice(-8)}`, kind: "success" });
      } else setError("任务完成但没有返回 run_id；请检查后端实验存储。");
      resetSubmit();
    } else if (job.status === "failed" || job.status === "cancelled") {
      setError(job.error || (job.status === "cancelled" ? "已取消" : "回测失败"));
      resetSubmit();
    }
  }, [progress.job, resetSubmit]);
  useEffect(() => { setSelectedTrade(null); setTab("equity"); }, [experimentId]);

  const update = (key: keyof BacktestDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const selectTemplate = (id: string) => {
    const found = templates.data?.find((item) => item.id === id);
    const defaults = found ? defaultsFromSchema(found.params_schema) : {};
    setDraft((current) => ({ ...current, template: id, paramsText: JSON.stringify(defaults) }));
  };
  const run = () => {
    setError(""); setNotice(""); setReplayMessage(""); setExperimentId("");
    try {
      const params: unknown = JSON.parse(draft.paramsText);
      if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("参数必须是 JSON 对象");
      const config = {
        start: draft.start, end: draft.end, initial_cash: Number(draft.cash), trace: draft.trace, seed: Number(draft.seed),
        benchmark_code: draft.benchmarkCode.trim() || undefined,
        costs: {
          commission_rate: Number(draft.commissionRate) / 100, min_commission: Number(draft.minCommission),
          stamp_duty_rate: Number(draft.stampDutyRate) / 100, transfer_fee_rate: 0.00001, exchange_fee_rate: 0.00001, reg_fee_rate: 0.000002,
        },
        exec: { type: draft.exec, slippage_bps: Number(draft.slippageBps) || 0, max_participation: Number(draft.maxParticipation) || 1, min_rebalance_value: Number(draft.minRebalanceValue) || 0 },
        risk: {
          max_positions: draft.maxPositions ? Number(draft.maxPositions) : undefined,
          max_weight: draft.maxWeight ? Number(draft.maxWeight) : undefined,
        },
      };
      submit.mutate({ template: draft.template, params, snapshot: snapshot || undefined, config }, {
        onSuccess: (response) => { setJobId(response.job_id); },
        onError: (reason) => setError(reason.message),
      });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "参数无效"); }
  };
  const onCancel = async () => { if (!jobId) return; try { await cancel.mutateAsync(jobId); setNotice("已请求取消"); } catch (reason) { setError(reason instanceof Error ? reason.message : "取消失败"); } };
  const onReplay = async () => {
    if (!experimentId) return;
    setReplayMessage("复现中…");
    try {
      const outcome = await replay.mutateAsync(experimentId);
      setReplayMessage(outcome.matched ? "复现一致：净值/交易/指标全部匹配" : `发现差异：${JSON.stringify(outcome.differences ?? outcome.diffs ?? outcome)}`);
    } catch (reason) { setReplayMessage(reason instanceof Error ? reason.message : "复现失败"); }
  };
  const scrollToWizard = () => document.getElementById("bt-wizard")?.scrollIntoView({ behavior: "smooth", block: "start" });

  const equityOption = useMemo<EChartsOption | null>(() => {
    if (!result) return null;
    const drawdown = result.equity.map((value, index) => {
      const peak = Math.max(...result.equity.slice(0, index + 1));
      return peak > 0 ? (value / peak - 1) * 100 : 0;
    });
    const benchmark = result.benchmark?.equity ?? null;
    return {
      animation: false, tooltip: { trigger: "axis" }, legend: { data: benchmark ? ["净值", "基准", "回撤"] : ["净值", "回撤"], top: 0, textStyle: { fontSize: 11 } },
      grid: [{ left: 70, right: 24, top: 30, height: "55%" }, { left: 70, right: 24, top: "76%", height: "15%" }],
      xAxis: [
        { type: "category", data: result.dates.map(dateInt), axisLabel: { fontSize: 10 } },
        { type: "category", data: result.dates.map(dateInt), gridIndex: 1, axisLabel: { show: false }, axisTick: { show: false } },
      ],
      yAxis: [
        { type: "value", scale: true, splitLine: { lineStyle: { color: palette.grid } } },
        { type: "value", gridIndex: 1, axisLabel: { formatter: "{value}%", fontSize: 10 }, splitNumber: 2 },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }, { type: "inside", xAxisIndex: [0, 1], orient: "vertical", yAxisIndex: [0] }],
      series: [
        { name: "净值", type: "line", data: result.equity, showSymbol: false, lineStyle: { width: 1.7, color: palette.accent }, areaStyle: { opacity: 0.06 } },
        ...(benchmark ? [{ name: "基准", type: "line" as const, data: benchmark, showSymbol: false, lineStyle: { width: 1.1, color: palette.text, opacity: 0.65 } }] : []),
        { name: "回撤", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: drawdown, showSymbol: false, lineStyle: { width: 1, color: palette.down }, areaStyle: { opacity: 0.16 } },
      ],
    };
  }, [result, palette]);
  const monthlyOption = useMemo<EChartsOption | null>(() => {
    if (!result) return null;
    const monthly = monthlyReturns(result).slice(-36);
    return {
      animation: false, tooltip: { trigger: "axis" }, grid: { left: 48, right: 16, top: 20, bottom: 40 },
      xAxis: { type: "category", data: monthly.map((item) => item.month), axisLabel: { fontSize: 10, rotate: 40 } },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [{ type: "bar", data: monthly.map((item) => ({ value: item.value * 100, itemStyle: { color: item.value >= 0 ? palette.up : palette.down } })) }],
    };
  }, [result, palette]);
  const tradeCode = useMemo(() => selectedTrade ? securities.data?.find((item) => item.sec_id === selectedTrade.sec_id)?.code ?? "" : "", [selectedTrade, securities.data]);
  const tradeBars = useBars(tradeCode || null);
  const tradeColumns = useMemo<ColumnDef<Trade, unknown>[]>(() => [
    { accessorKey: "date", header: "日期", size: 108, cell: ({ row }) => <span className="mono">{dateInt(row.original.date)}</span> },
    { accessorKey: "sec_id", header: "证券", size: 100, cell: ({ row }) => <span className="mono truncate" title={row.original.sec_id}>{row.original.sec_id || row.original.sec_index}</span> },
    { accessorKey: "side", header: "方向", size: 64, cell: ({ row }) => <span className={row.original.side === 0 ? "up" : "down"}>{row.original.side === 0 ? "买入" : "卖出"}</span> },
    { accessorKey: "px_yuan", header: "价格", size: 82, cell: ({ row }) => <span className="num">{num(row.original.px_yuan)}</span> },
    { accessorKey: "qty", header: "数量", size: 78, cell: ({ row }) => <span className="num">{num(row.original.qty, 0)}</span> },
    { accessorKey: "fee_total", header: "费用", size: 90, cell: ({ row }) => <span className="num">{money(fixedToYuan(row.original.fee_total))}</span> },
    { accessorKey: "reason", header: "原因", size: 130, cell: ({ row }) => <span className="truncate" title={row.original.reason_name}>{row.original.reason_name === "none" ? "调仓" : row.original.reason_name || "—"}</span> },
  ], []);
  const fees = useMemo(() => {
    const list = result?.trades ?? [];
    const sum = (key: keyof Trade) => list.reduce((total, trade) => total + fixedToYuan(typeof trade[key] === "number" ? trade[key] as number : 0), 0);
    return { commission: sum("commission"), stamp: sum("stamp_duty"), transfer: sum("transfer_fee"), other: sum("other_fee"), total: sum("fee_total") };
  }, [result]);
  const running = Boolean(jobId && progress.job && ["pending", "running"].includes(progress.job.status));
  const phase = result || running ? 3 : draft.template ? 2 : 1;
  const integrityBadge = integrity.isError
    ? { tone: "warn" as const, text: isApiError(integrity.error) && integrity.error.status === 404 ? "数据体检：后端未就绪" : "数据体检：暂不可用" }
    : integrity.data
      ? { tone: integrity.data.status === "ok" ? "ok" as const : integrity.data.status === "warn" ? "warn" as const : "danger" as const, text: `数据体检 ${integrity.data.status === "ok" ? "通过" : integrity.data.status === "warn" ? "有警告" : "未通过"} · 覆盖 ${integrity.data.coverage.coverage_pct.toFixed(1)}%` }
      : { tone: "neutral" as const, text: "数据体检：加载中" };
  const conclusionTone = result && result.metrics.total_return >= 0 ? "tone-ok" : "tone-danger";
  const benchmarkDiff = result?.benchmark ? result.metrics.total_return - result.benchmark.total_return : null;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>回测</h1><p className="page-lead">三步跑一次可复现、带数据体检的回测；结果先给结论，再展开细节。</p></div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => void onReplay()} disabled={!experimentId}><RotateCcw size={15} /> 复现</button>
          <button className="btn" onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report`, `${experimentId}.html`)} disabled={!experimentId}><Download size={15} /> 报告</button>
          <button className="btn ghost" onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report.pdf`, `${experimentId}.pdf`)} disabled={!experimentId} title="需要本机 Chrome/Chromium；无可用浏览器时后端返回 503">PDF</button>
          {running ? <button className="btn danger" onClick={() => void onCancel()}><Square size={15} /> 取消</button> : <button className="btn primary" onClick={run} disabled={submit.isPending}><Play size={15} /> 运行回测</button>}
        </div>
      </header>
      {screenerNote ? <Panel dense tone="info"><span className="muted small">来自选股的条件：<span className="mono">{screenerNote}</span>（当前回测按策略模板在全市场选股；该条件仅作研究记录，不改变回测股票池。）</span></Panel> : null}

      <div className="bt-wizard" id="bt-wizard">
        <section className={`bt-step ${phase === 1 ? "active" : "done"}`}>
          <div className="bt-step-head"><span className="bt-step-num">1</span><div><h2>选策略</h2><p>内置模板都有白话说明；先用默认参数跑通，再调参。</p></div><div className="bt-step-head-actions"><Badge tone="neutral">{draft.template}</Badge></div></div>
          {templates.isLoading ? <Skeleton rows={3} /> : templates.error ? (
            <EmptyState title="策略模板加载失败" hint={templates.error.message} action={<button className="btn" onClick={() => void templates.refetch()}>重试</button>} />
          ) : (
            <div className="tpl-grid">
              {(templates.data ?? []).map((item) => (
                <button key={item.id} type="button" className={`tpl-card ${draft.template === item.id ? "active" : ""}`} onClick={() => selectTemplate(item.id)}>
                  <strong>{item.name || item.id}</strong>
                  <small>{item.description}</small>
                  <span className="tpl-foot">{beginner ? <Badge tone="info">默认参数即可运行</Badge> : <Badge tone="neutral">{item.id}</Badge>}</span>
                </button>
              ))}
            </div>
          )}
          {!beginner ? (
            <details className="advanced">
              <summary><ChevronDown size={15} /> 专业：模板参数 JSON</summary>
              <textarea className="code-input" rows={4} value={draft.paramsText} onChange={(event) => update("paramsText", event.target.value)} spellCheck={false} aria-label="模板参数 JSON" />
              <p className="muted small">参数经后端 JSON Schema 校验；非法值会在运行时报错。</p>
            </details>
          ) : <p className="muted small">参数：<span className="mono">{draft.paramsText}</span> · 切换到专业模式可编辑。</p>}
        </section>

        <section className={`bt-step ${phase === 2 ? "active" : phase > 2 ? "done" : ""}`}>
          <div className="bt-step-head"><span className="bt-step-num">2</span><div><h2>选数据与区间</h2><p>快照决定用哪份历史数据；区间越短跑得越快。</p></div></div>
          <div className="form-grid">
            <label>数据快照<select value={snapshot} onChange={(event) => setSnapshot(event.target.value)}>
              <option value="">内置 SYNTHETIC（无需导入）</option>
              {(dataStatus.data?.snapshots ?? []).map((item) => <option key={item.id} value={item.id}>{item.id.slice(0, 18)} · {item.n_sec} 券 · {dateInt(item.start)}–{dateInt(item.end)}{item.synthetic ? " · SYNTHETIC" : ""}</option>)}
            </select></label>
            <label>开始<input value={draft.start} onChange={(event) => update("start", event.target.value)} placeholder="YYYY-MM-DD" /></label>
            <label>结束<input value={draft.end} onChange={(event) => update("end", event.target.value)} placeholder="YYYY-MM-DD" /></label>
            <label>初始资金（元）<input value={draft.cash} onChange={(event) => update("cash", event.target.value)} inputMode="decimal" /></label>
            {!beginner ? <label>成交规则<select value={draft.exec} onChange={(event) => update("exec", event.target.value)}><option value="next_open">次日开盘</option><option value="next_close">次日收盘</option><option value="next_vwap">次日 VWAP</option><option value="after_hours_fixed">盘后固定价</option></select></label> : null}
            {!beginner ? <label>滑点（bp）<input value={draft.slippageBps} onChange={(event) => update("slippageBps", event.target.value)} inputMode="decimal" /></label> : null}
          </div>
          {!beginner ? (
            <details className="advanced" open={advanced} onToggle={(event) => setAdvanced((event.target as HTMLDetailsElement).open)}>
              <summary><ChevronDown size={15} /> 专业：费用 / 成交 / 风险 / 调试</summary>
              <div className="form-grid two">
                <label>佣金率（%）<input value={draft.commissionRate} onChange={(event) => update("commissionRate", event.target.value)} inputMode="decimal" /></label>
                <label>最低佣金（元）<input value={draft.minCommission} onChange={(event) => update("minCommission", event.target.value)} inputMode="decimal" /></label>
                <label>印花税（%）<input value={draft.stampDutyRate} onChange={(event) => update("stampDutyRate", event.target.value)} inputMode="decimal" /></label>
                <label>最大参与率<input value={draft.maxParticipation} onChange={(event) => update("maxParticipation", event.target.value)} inputMode="decimal" /></label>
                <label>最小调仓额（元）<input value={draft.minRebalanceValue} onChange={(event) => update("minRebalanceValue", event.target.value)} inputMode="decimal" /></label>
                <label>trace<select value={draft.trace} onChange={(event) => update("trace", event.target.value)}><option value="off">off</option><option value="summary">summary</option><option value="full">full</option></select></label>
                <label>seed<input value={draft.seed} onChange={(event) => update("seed", event.target.value)} inputMode="numeric" /></label>
                <label>基准代码<input value={draft.benchmarkCode} onChange={(event) => update("benchmarkCode", event.target.value)} placeholder="如 000300（后端未支持时不生效）" /></label>
                <label>最大持仓数<input value={draft.maxPositions} onChange={(event) => update("maxPositions", event.target.value)} inputMode="numeric" placeholder="不限" /></label>
                <label>单票最大权重<input value={draft.maxWeight} onChange={(event) => update("maxWeight", event.target.value)} inputMode="decimal" placeholder="0-1，如 0.1" /></label>
              </div>
              <p className="muted small">费用按百分比输入并换算为小数；风险限制在目标权重生成后应用（long-only、最大持仓、单票最大权重）。</p>
            </details>
          ) : null}
          <div className="bt-summary"><span>区间 <strong>{draft.start} → {draft.end}</strong></span><span>资金 <strong>{money(Number(draft.cash))}</strong></span><span>数据 <strong>{snapshot ? snapshot.slice(0, 18) : "内置 SYNTHETIC"}</strong></span><Badge tone={integrityBadge.tone}>{integrityBadge.text}</Badge></div>
        </section>

        <section className={`bt-step ${phase === 3 ? "active" : ""}`}>
          <div className="bt-step-head"><span className="bt-step-num">3</span><div><h2>运行</h2><p>提交本地任务；进度通过 WS 推送，失败或太慢可随时取消。</p></div></div>
          <div className="bt-summary"><span>策略 <strong>{draft.template}</strong></span><span>快照 <strong>{snapshot || "内置 SYNTHETIC"}</strong></span><span>区间 <strong>{draft.start} → {draft.end}</strong></span><span>初始资金 <strong>{money(Number(draft.cash))}</strong></span></div>
          <div className="bt-progress-actions">
            {running ? <button className="btn danger" onClick={() => void onCancel()}><Square size={15} /> 取消任务</button> : <button className="btn primary" onClick={run} disabled={submit.isPending}><Play size={15} /> 运行回测</button>}
            {progress.job ? <div className="progress" role="status" style={{ flex: 1, margin: 0 }}><div className="progress-bar" style={{ width: `${Math.round(progress.job.progress * 100)}%` }} /><span>{progress.job.status} · {Math.round(progress.job.progress * 100)}% · {progress.transport ?? "等待"}</span></div> : <span className="muted small">实验会自动保存到 experiments/；结果仅用于研究。</span>}
          </div>
          {error ? <p className="error" role="alert">{error}</p> : null}
          {notice ? <p className="success-text">{notice}</p> : null}
          {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error"}>{replayMessage}</p> : null}
        </section>
      </div>

      {!result && !experimentId && !running ? <Panel><EmptyState title="还没有回测结果" hint="上面三步填好后点「运行回测」；完成后这里会先给结论和 4 个关键数字，再给图表与交易明细。" action={<button className="btn primary" onClick={scrollToWizard}><SlidersHorizontal size={15} /> 回到三步向导</button>} /></Panel> : null}
      {experimentId && resultQuery.isLoading ? <Panel><Skeleton rows={6} /></Panel> : null}
      {experimentId && resultQuery.error ? <Panel><EmptyState title="结果加载失败" hint={resultQuery.error.message} action={<button className="btn" onClick={() => void resultQuery.refetch()}>重试</button>} /></Panel> : null}
      {result ? (
        <>
          <div className={`conclusion ${conclusionTone}`}>
            <h2>结论：{result.metrics.total_return >= 0 ? "本次回测取得正收益" : "本次回测亏损"}，最大回撤 {pct(result.metrics.max_drawdown)}</h2>
            <p>总收益 <strong>{pct(result.metrics.total_return)}</strong>（年化 {pct(result.metrics.annualized_return)}），Sharpe <strong>{num(result.metrics.sharpe)}</strong>，交易 <strong>{result.trades.length}</strong> 笔，已扣成本 <strong>{money(fixedToYuan(result.metrics.total_fees))}</strong>。{benchmarkDiff == null ? "未设置基准。" : benchmarkDiff >= 0 ? `跑赢基准 ${pct(benchmarkDiff)}。` : `跑输基准 ${pct(Math.abs(benchmarkDiff))}。`}</p>
            <div className="row" style={{ marginTop: 8, gap: 6 }}>
              <Badge tone={integrityBadge.tone}>{integrityBadge.text}</Badge>
              <Badge tone="ok">成本后口径 · 已扣费用</Badge>
              <Badge tone="warn">样本内 · 未做样本外验证</Badge>
              <Badge tone="neutral">引擎 {result.engine_backend} {result.engine_version}</Badge>
            </div>
            <div className="conclusion-actions">
              <button className="btn primary" onClick={scrollToWizard}><SlidersHorizontal size={15} /> 改参数再跑</button>
              <button className="btn" onClick={() => experimentId && navigate(`/experiments?run=${encodeURIComponent(experimentId)}`)} disabled={!experimentId}><GitCompare size={15} /> 加入对比</button>
              <button className="btn" onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report`, `${experimentId}.html`)} disabled={!experimentId}><Download size={15} /> 查看报告</button>
              <button className="btn ghost" onClick={() => experimentId && navigate(`/research?run=${encodeURIComponent(experimentId)}`)} disabled={!experimentId}>做样本外验证</button>
            </div>
          </div>
          <div className="stat-grid">
            <StatTile label="总收益" value={pct(result.metrics.total_return)} trend={result.metrics.total_return >= 0 ? "up" : "down"} tone={result.metrics.total_return >= 0 ? "up" : "down"} hint={`年化 ${pct(result.metrics.annualized_return)} · 胜率 ${pct(result.metrics.win_rate)}`} />
            <StatTile label="最大回撤" value={pct(result.metrics.max_drawdown)} tone="down" hint={`Calmar ${num(result.metrics.calmar ?? 0)}`} />
            <StatTile label="夏普" value={num(result.metrics.sharpe)} hint={`波动 ${pct(result.metrics.volatility ?? 0)} · Sortino ${num(result.metrics.sortino ?? 0)}`} />
            <StatTile label="交易次数" value={num(result.metrics.trade_count, 0)} hint={`换手 ${pct(result.metrics.turnover)} · 费用 ${money(fixedToYuan(result.metrics.total_fees))}`} />
          </div>
          <Tabs items={TAB_ITEMS.map((item) => item.id === "trades" ? { ...item, badge: result.trades.length } : item)} value={tab} onChange={setTab} ariaLabel="回测结果视图" />
          {tab === "equity" ? <ChartCard title="净值与回撤" subtitle="上方净值（含基准，如后端返回），下方回撤" height={380}>{equityOption ? <Chart option={equityOption} height={380} /> : null}</ChartCard> : null}
          {tab === "monthly" ? (
            <div className="grid two-col">
              <ChartCard title="月度收益" subtitle="最近 36 个月" height={280}>{monthlyOption ? <Chart option={monthlyOption} height={280} /> : null}</ChartCard>
              <Panel title="费用构成" subtitle="逐笔交易费用汇总"><div className="fee-list"><span>佣金 <strong>{money(fees.commission)}</strong></span><span>印花税 <strong>{money(fees.stamp)}</strong></span><span>过户费 <strong>{money(fees.transfer)}</strong></span><span>其他 <strong>{money(fees.other)}</strong></span><span>合计 <strong>{money(fees.total)}</strong></span></div><h3 style={{ marginTop: 12 }}>原因码</h3><div className="reason-list">{Object.entries(result.reasons).length ? Object.entries(result.reasons).map(([key, value]) => <span key={key} className="badge">{key}: {value}</span>) : <span className="muted small">无 trace 原因码</span>}</div><p className="muted small">期末：现金 {money(result.cash.at(-1))} · 持仓市值 {money(result.market_value.at(-1))} · 总权益 {money(result.equity.at(-1))}。后端不返回逐证券持仓明细，这里不生成假持仓。</p></Panel>
            </div>
          ) : null}
          {tab === "trades" ? <Panel title="逐笔交易" subtitle={`${result.trades.length} 笔 · ${result.engine_backend} ${result.engine_version}`} actions={<span className="muted small">点击行查看交易解释与 K 线</span>}><VirtualTable data={result.trades} columns={tradeColumns} rowKey={(trade) => `${trade.date}-${trade.sec_id ?? trade.sec_index ?? ""}-${trade.side}-${trade.qty}`} height={320} onRowClick={(trade) => { setSelectedTrade(trade); setTab("explain"); }} initialSorting={[{ id: "date", desc: true }]} ariaLabel="逐笔交易" empty={<span className="muted">该回测没有成交。</span>} /></Panel> : null}
          {tab === "explain" ? (
            <Panel title="交易解释" subtitle={selectedTrade ? "费用拆分与原因码；K 线定位买卖点" : "从「交易明细」选择一笔交易"} actions={selectedTrade ? <button className="btn ghost" onClick={() => setSelectedTrade(null)}>关闭</button> : null}>
              {!selectedTrade ? <EmptyState title="还没有选择交易" hint="在「交易明细」点任意一行，这里会显示费用拆分、原因码和该证券的 K 线。" /> : (
                <>
                  <div className="trade-detail-grid">
                    <span>日期 <strong>{dateInt(selectedTrade.date)}</strong></span><span>证券 <strong>{selectedTrade.sec_id || selectedTrade.sec_index}</strong></span>
                    <span>方向 <strong className={selectedTrade.side === 0 ? "up" : "down"}>{selectedTrade.side === 0 ? "买入" : "卖出"}</strong></span>
                    <span>价格 <strong>{money(selectedTrade.px_yuan)}</strong></span><span>数量 <strong>{num(selectedTrade.qty, 0)}</strong></span>
                    <span>成交额 <strong>{money(selectedTrade.amount_yuan)}</strong></span><span>费用 <strong>{money(fixedToYuan(selectedTrade.fee_total))}</strong></span>
                    <span>方向现金流 <strong>{money((selectedTrade.side === 1 ? 1 : -1) * (selectedTrade.amount_yuan ?? 0))}</strong></span>
                  </div>
                  <p className="muted small">费用：佣金 {money(fixedToYuan(selectedTrade.commission))} · 印花税 {money(fixedToYuan(selectedTrade.stamp_duty))} · 过户费 {money(fixedToYuan(selectedTrade.transfer_fee))} · 其他 {money(fixedToYuan(selectedTrade.other_fee))}。原因码 {selectedTrade.reason}（{selectedTrade.reason_name || "—"}）。</p>
                  <p className="muted small">后端逐笔结果没有已实现盈亏字段，因此不伪造「收益贡献」；方向现金流只是买卖成交额的符号，不是盈亏。</p>
                  {tradeCode ? (tradeBars.data ? <KLineChart bars={tradeBars.data} palette={palette} height={280} /> : tradeBars.error ? <EmptyState title="K 线加载失败" hint={tradeBars.error.message} /> : <Skeleton rows={3} />) : <p className="muted small">无法从证券列表定位该交易代码（sec_id={selectedTrade.sec_id}）。</p>}
                </>
              )}
            </Panel>
          ) : null}
          <p className="muted small">实验 {experimentId || "—"} · 引擎 {result.engine_backend} · seed {result.seed}。{t.disclaimer}</p>
        </>
      ) : null}
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
