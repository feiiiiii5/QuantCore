import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Download, GitCompare, Play, RotateCcw, SlidersHorizontal, Square } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  useBars, useCancelJob, useDataIntegrity, useDataStatus, useExperimentDetail, useExperimentResult,
  useOnboardingPresets, useReplayExperiment, useSecurities, useSubmitBacktest, useTemplates,
} from "../api/queries";
import { downloadWithAuth, isApiError } from "../api/client";
import type { StrategyPreset, Trade } from "../api/types";
import {
  Badge, Button, Callout, Chart, ChartCard, EmptyState, Field, Input, KLineChart, PageHeader, Panel, ProgressBar,
  Select, Skeleton, StatTile, Tabs, Textarea, VirtualTable, defaultsFromSchema, type ChartSeries,
} from "../components";
import { useJobProgress } from "../hooks/useJobProgress";
import { dateInt, fixedToYuan, money, num, pct } from "../lib/format";
import { drawdowns, monthlyReturns } from "../lib/backtestAnalysis";
import { configFromDraft, restoreDraft } from "../lib/backtestDraft";
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

export default function BacktestPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const palette = useChartPalette();
  const beginner = useBeginner();
  const templates = useTemplates();
  const presets = useOnboardingPresets();
  const submit = useSubmitBacktest();
  const cancel = useCancelJob();
  const replay = useReplayExperiment();
  const securities = useSecurities("", 1000);
  const dataStatus = useDataStatus();
  const sourceId = searchParams.get("source");
  const sourceQuery = useExperimentDetail(sourceId);
  const restoredSource = useRef<string | null>(null);
  const stored = useWorkspace.getState().backtestDraft;
  const [draft, setDraft] = useState<BacktestDraft>(() => ({
    ...DEFAULTS,
    ...stored,
    template: searchParams.get("template") || stored.template || DEFAULTS.template,
    paramsText: searchParams.get("params") || stored.paramsText || DEFAULTS.paramsText,
  }));
  const [snapshot, setSnapshot] = useState("");
  const integrity = useDataIntegrity(snapshot && !snapshot.startsWith("source:") ? snapshot : undefined);
  const [jobId, setJobId] = useState<string | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("equity");
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [replayMessage, setReplayMessage] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const setDraftStore = useWorkspace((state) => state.setBacktestDraft);
  const progress = useJobProgress(jobId);
  const resetSubmit = submit.reset;
  const resultQuery = useExperimentResult(experimentId || null);
  const result = resultQuery.data ?? null;
  const screenerNote = searchParams.get("screener") || "";

  useEffect(() => { setDraftStore(draft); }, [draft, setDraftStore]);
  useEffect(() => {
    if (!sourceId || !sourceQuery.data || restoredSource.current === sourceId) return;
    try {
      setDraft(restoreDraft(sourceQuery.data, DEFAULTS));
      setSnapshot(`source:${sourceId}`);
      restoredSource.current = sourceId;
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法载入原实验"); }
  }, [sourceId, sourceQuery.data]);
  useEffect(() => {
    const job = progress.job;
    if (!job || job.id !== jobId) return;
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
  }, [progress.job, jobId, resetSubmit]);
  useEffect(() => { setSelectedTrade(null); setTab("equity"); }, [experimentId]);

  const update = (key: keyof BacktestDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const selectTemplate = (id: string) => {
    const found = templates.data?.find((item) => item.id === id);
    const defaults = found ? defaultsFromSchema(found.params_schema) : {};
    setSelectedPreset("");
    setDraft((current) => ({ ...current, template: id, paramsText: JSON.stringify(defaults) }));
  };
  const applyPreset = (preset: StrategyPreset) => {
    setSelectedPreset(preset.id);
    setDraft((current) => ({ ...current, template: preset.template, paramsText: JSON.stringify(preset.params ?? {}) }));
  };
  const run = () => {
    if (running) return;
    setError(""); setNotice(""); setReplayMessage(""); setExperimentId("");
    setJobId(null);
    try {
      if (sourceId && (sourceQuery.isPending || sourceQuery.error || restoredSource.current !== sourceId)) throw new Error(sourceQuery.error?.message || "请等待原实验载入后再运行");
      const params: unknown = JSON.parse(draft.paramsText);
      if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("参数必须是 JSON 对象");
      const config = configFromDraft(draft, sourceQuery.data);
      const data = snapshot.startsWith("source:") ? { source_run_id: snapshot.slice(7) } : { snapshot: snapshot || undefined };
      submit.mutate({ template: draft.template, params, ...data, config }, {
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

  const equitySeries = useMemo<ChartSeries[]>(() => {
    if (!result) return [];
    const initial = result.config?.initial_cash;
    const drawdown = drawdowns(result.equity, typeof initial === "number" ? initial : undefined);
    const series: ChartSeries[] = [
      { kind: "area", title: "净值", data: result.dates.map((date, index) => ({ time: date, value: result.equity[index] })) },
      { kind: "area", title: "回撤（%）", pane: 1, color: palette.down, data: result.dates.map((date, index) => ({ time: date, value: drawdown[index] * 100 })) },
    ];
    if (result.benchmark?.equity) {
      const benchmark = result.benchmark.equity;
      series.push({
        kind: "line", title: "基准", color: palette.text, lineWidth: 1,
        data: result.dates.flatMap((date, index) => benchmark[index] == null ? [] : [{ time: date, value: benchmark[index] as number }]),
      });
    }
    return series;
  }, [result, palette]);
  const monthlySeries = useMemo<ChartSeries[]>(() => {
    if (!result) return [];
    const initial = result.config?.initial_cash;
    const monthly = monthlyReturns(result.dates, result.equity, typeof initial === "number" ? initial : undefined).slice(-36);
    return [{
      kind: "histogram", title: "月度收益（%）",
      data: monthly.map((item) => ({ time: item.month + "-01", value: item.value * 100, color: item.value >= 0 ? palette.up : palette.down })),
    }];
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
  const running = submit.isPending || Boolean(jobId && (!progress.job || progress.job.id !== jobId || ["pending", "running"].includes(progress.job.status)));
  const phase = result || running ? 3 : draft.template ? 2 : 1;
  const dataLabel = snapshot.startsWith("source:") ? "原实验的已保存数据" : snapshot || "内置 SYNTHETIC";
  const integrityBadge = snapshot.startsWith("source:")
    ? { tone: "neutral" as const, text: "沿用原实验数据 · 未重新体检" }
    : !snapshot ? { tone: "info" as const, text: "SYNTHETIC · 仅演示" } : integrity.isError
    ? { tone: "warn" as const, text: isApiError(integrity.error) && integrity.error.status === 404 ? "数据体检：后端未就绪" : "数据体检：暂不可用" }
    : integrity.data
      ? { tone: integrity.data.status === "ok" ? "ok" as const : integrity.data.status === "warn" ? "warn" as const : "danger" as const, text: `数据体检 ${integrity.data.status === "ok" ? "通过" : integrity.data.status === "warn" ? "有警告" : "未通过"} · 覆盖 ${integrity.data.coverage.coverage_pct.toFixed(1)}%` }
      : { tone: "neutral" as const, text: "数据体检：加载中" };
  const conclusionTone = result && result.metrics.total_return >= 0 ? "tone-ok" : "tone-danger";
  const benchmarkDiff = useMemo(() => {
    if (!result?.benchmark) return null;
    const total = result.benchmark.total_return;
    if (Number.isFinite(total)) return result.metrics.total_return - total;
    const equity = (result.benchmark.equity ?? []).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (equity.length > 1 && equity[0] > 0) return result.metrics.total_return - (equity[equity.length - 1] / equity[0] - 1);
    return null;
  }, [result]);
  const presetCards = presets.data ?? [];

  return (
    <div className="page">
      <PageHeader
        title="回测"
        subtitle="三步跑一次可复现、带数据体检的回测；结果先给结论，再展开细节。"
        actions={(
          <>
            <Button variant="secondary" icon={RotateCcw} onClick={() => void onReplay()} disabled={!experimentId}>复现</Button>
            <Button variant="secondary" icon={Download} onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report`, `${experimentId}.html`)} disabled={!experimentId}>报告</Button>
            <Button variant="ghost" onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report.pdf`, `${experimentId}.pdf`)} disabled={!experimentId}>PDF</Button>
            {running
              ? <Button variant="danger" icon={Square} onClick={() => void onCancel()}>取消</Button>
              : <Button variant="primary" icon={Play} loading={submit.isPending} onClick={run}>运行回测</Button>}
          </>
        )}
      />
      {sourceId ? <Callout tone={sourceQuery.error ? "danger" : "info"} title={sourceQuery.error ? "原实验加载失败" : sourceQuery.isPending ? "正在载入原实验" : "沿用原实验开展新研究"}>{sourceQuery.error?.message || `保留数据、策略和费用假设；改动参数后会保存为新实验，原记录保留。来源：${sourceId}`}</Callout> : null}
      {screenerNote ? <Callout tone="info" title="来自选股的条件">「{screenerNote}」——当前回测按策略模板在全市场选股，该条件仅作研究记录，不改变回测股票池。</Callout> : null}

      <div className="wizard" id="bt-wizard">
        <section className={`wizard-step ${phase === 1 ? "active" : "done"}`}>
          <div className="wizard-head">
            <span className="wizard-num">1</span>
            <div className="wizard-head-main"><h2 className="wizard-title">选策略</h2><p className="wizard-sub">白话模板默认参数即可运行；先用默认跑通，再调参。</p></div>
            <div className="wizard-head-actions"><Badge tone="neutral">{draft.template}</Badge></div>
          </div>
          {presets.isLoading || templates.isLoading ? <Skeleton rows={3} /> : templates.error ? (
            <EmptyState title="策略模板加载失败" hint={templates.error.message} action={<Button variant="secondary" onClick={() => void templates.refetch()}>重试</Button>} />
          ) : presetCards.length ? (
            <div className="grid grid-3">
              {presetCards.map((preset) => (
                <button key={preset.id} type="button" className="template-card" aria-pressed={selectedPreset === preset.id} onClick={() => applyPreset(preset)}>
                  <span className="template-name">{preset.name}</span>
                  <span className="template-desc">{preset.tagline}</span>
                  <span className="template-meta">适合：{preset.suitable_for} · 周期 {preset.horizon}</span>
                  <span className="template-foot"><Badge tone={selectedPreset === preset.id ? "info" : "neutral"}>{selectedPreset === preset.id ? "已选择" : preset.template}</Badge></span>
                  <span className="template-risk">风险：{preset.risk_note}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="grid grid-3">
              {(templates.data ?? []).map((item) => (
                <button key={item.id} type="button" className="template-card" aria-pressed={draft.template === item.id} onClick={() => selectTemplate(item.id)}>
                  <span className="template-name">{item.name || item.id}</span>
                  <span className="template-desc">{item.description}</span>
                  <span className="template-foot"><Badge tone="neutral">{item.id}</Badge></span>
                </button>
              ))}
            </div>
          )}
          {!beginner ? (
            <Field label="模板参数 JSON" hint="参数经后端 JSON Schema 校验；非法值会在运行时报错。">
              <Textarea rows={4} value={draft.paramsText} onChange={(event) => update("paramsText", event.target.value)} spellCheck={false} aria-label="模板参数 JSON" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }} />
            </Field>
          ) : <p className="page-note-sm">参数：<span className="mono">{draft.paramsText}</span> · 切换到专业模式可编辑。</p>}
        </section>

        <section className={`wizard-step ${phase === 2 ? "active" : phase > 2 ? "done" : ""}`}>
          <div className="wizard-head">
            <span className="wizard-num">2</span>
            <div className="wizard-head-main"><h2 className="wizard-title">选数据与区间</h2><p className="wizard-sub">快照决定用哪份历史数据；区间越短跑得越快。</p></div>
          </div>
          <div className="grid grid-3">
            <Field label="数据快照" hint="默认内置 SYNTHETIC，无需导入">
              <Select value={snapshot} onChange={(event) => setSnapshot(event.target.value)} options={[...(sourceId && sourceQuery.data ? [{ value: `source:${sourceId}`, label: "沿用原实验的已保存数据" }] : []), { value: "", label: "内置 SYNTHETIC" }, ...(dataStatus.data?.snapshots ?? []).map((item) => ({ value: item.id, label: `${item.id.slice(0, 18)} · ${item.n_sec} 券 · ${dateInt(item.start)}–${dateInt(item.end)}${item.synthetic ? " · SYNTHETIC" : ""}` }))]} />
            </Field>
            <Field label="开始日期"><Input value={draft.start} onChange={(event) => update("start", event.target.value)} placeholder="YYYY-MM-DD" aria-label="开始日期" /></Field>
            <Field label="结束日期"><Input value={draft.end} onChange={(event) => update("end", event.target.value)} placeholder="YYYY-MM-DD" aria-label="结束日期" /></Field>
            <Field label="初始资金（元）"><Input value={draft.cash} onChange={(event) => update("cash", event.target.value)} inputMode="decimal" aria-label="初始资金（元）" /></Field>
            {!beginner ? (
              <>
                <Field label="成交规则">
                  <Select value={draft.exec} onChange={(event) => update("exec", event.target.value)} options={[{ value: "next_open", label: "次日开盘" }, { value: "next_close", label: "次日收盘" }, { value: "next_vwap", label: "次日 VWAP" }, { value: "after_hours_fixed", label: "盘后固定价" }]} />
                </Field>
                <Field label="滑点（bp）"><Input value={draft.slippageBps} onChange={(event) => update("slippageBps", event.target.value)} inputMode="decimal" /></Field>
              </>
            ) : null}
          </div>
          {!beginner ? (
            <details>
              <summary className="row" style={{ cursor: "pointer", color: "var(--text-2)" }}><ChevronDown size={15} /> 专业：费用 / 成交 / 风险 / 调试</summary>
              <div className="grid grid-3" style={{ marginTop: "var(--sp-5)" }}>
                <Field label="佣金率（%）"><Input value={draft.commissionRate} onChange={(event) => update("commissionRate", event.target.value)} inputMode="decimal" /></Field>
                <Field label="最低佣金（元）"><Input value={draft.minCommission} onChange={(event) => update("minCommission", event.target.value)} inputMode="decimal" /></Field>
                <Field label="印花税（%）"><Input value={draft.stampDutyRate} onChange={(event) => update("stampDutyRate", event.target.value)} inputMode="decimal" /></Field>
                <Field label="最大参与率"><Input value={draft.maxParticipation} onChange={(event) => update("maxParticipation", event.target.value)} inputMode="decimal" /></Field>
                <Field label="最小调仓额（元）"><Input value={draft.minRebalanceValue} onChange={(event) => update("minRebalanceValue", event.target.value)} inputMode="decimal" /></Field>
                <Field label="trace"><Select value={draft.trace} onChange={(event) => update("trace", event.target.value)} options={[{ value: "off", label: "off" }, { value: "summary", label: "summary" }, { value: "full", label: "full" }]} /></Field>
                <Field label="seed"><Input value={draft.seed} onChange={(event) => update("seed", event.target.value)} inputMode="numeric" /></Field>
                <Field label="基准代码" hint="后端未支持时不生效"><Input value={draft.benchmarkCode} onChange={(event) => update("benchmarkCode", event.target.value)} placeholder="如 000300" /></Field>
                <Field label="最大持仓数"><Input value={draft.maxPositions} onChange={(event) => update("maxPositions", event.target.value)} inputMode="numeric" placeholder="不限" /></Field>
                <Field label="单票最大权重"><Input value={draft.maxWeight} onChange={(event) => update("maxWeight", event.target.value)} inputMode="decimal" placeholder="0-1，如 0.1" /></Field>
              </div>
              <p className="page-note-sm" style={{ marginTop: "var(--sp-4)" }}>费用按百分比输入并换算为小数；风险限制在目标权重生成后应用（long-only、最大持仓、单票最大权重）。</p>
            </details>
          ) : null}
          <div className="wizard-summary">
            <span>区间 <strong>{draft.start} → {draft.end}</strong></span>
            <span>资金 <strong>{money(Number(draft.cash))}</strong></span>
            <span>数据 <strong>{dataLabel}</strong></span>
            <Badge tone={integrityBadge.tone}>{integrityBadge.text}</Badge>
          </div>
        </section>

        <section className={`wizard-step ${phase === 3 ? "active" : ""}`}>
          <div className="wizard-head">
            <span className="wizard-num">3</span>
            <div className="wizard-head-main"><h2 className="wizard-title">运行</h2><p className="wizard-sub">提交本地任务；进度通过 WS 推送，失败或太慢可随时取消。</p></div>
          </div>
          <div className="wizard-summary">
            <span>策略 <strong>{draft.template}</strong></span>
            <span>快照 <strong>{dataLabel}</strong></span>
            <span>区间 <strong>{draft.start} → {draft.end}</strong></span>
            <span>初始资金 <strong>{money(Number(draft.cash))}</strong></span>
          </div>
          <div className="run-bar">
            {running ? <Button variant="danger" icon={Square} onClick={() => void onCancel()}>取消任务</Button> : <Button variant="primary" icon={Play} loading={submit.isPending} onClick={run}>运行回测</Button>}
            {progress.job ? <ProgressBar className="spacer" value={Math.round(progress.job.progress * 100)} label={`${progress.job.status} · ${progress.transport ?? "等待"}`} /> : <span className="page-note-sm">实验会自动保存到 experiments/；结果仅用于研究。</span>}
          </div>
          {error ? <Callout tone="danger" title={error} /> : null}
          {notice ? <Callout tone="success" title={notice} /> : null}
          {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error-text"}>{replayMessage}</p> : null}
        </section>
      </div>

      {!result && !experimentId && !running ? <Panel><EmptyState title="还没有回测结果" hint="上面三步填好后点「运行回测」；完成后这里会先给结论和 4 个关键数字，再给图表与交易明细。" action={<Button variant="primary" icon={SlidersHorizontal} onClick={scrollToWizard}>回到三步向导</Button>} /></Panel> : null}
      {experimentId && resultQuery.isLoading ? <Panel><Skeleton rows={6} /></Panel> : null}
      {experimentId && resultQuery.error ? <Panel><EmptyState title="结果加载失败" hint={resultQuery.error.message} action={<Button variant="secondary" onClick={() => void resultQuery.refetch()}>重试</Button>} /></Panel> : null}
      {result ? (
        <>
          <div className={`conclusion ${conclusionTone}`}>
            <div className="conclusion-head"><h2 className="conclusion-title">结论：{result.metrics.total_return >= 0 ? "本次回测取得正收益" : "本次回测亏损"}，最大回撤 {pct(result.metrics.max_drawdown)}</h2></div>
            <p className="conclusion-text">总收益 <strong>{pct(result.metrics.total_return)}</strong>（年化 {pct(result.metrics.annualized_return)}），Sharpe <strong>{num(result.metrics.sharpe)}</strong>，交易 <strong>{result.trades.length}</strong> 笔，已扣成本 <strong>{money(fixedToYuan(result.metrics.total_fees))}</strong>。{benchmarkDiff == null ? "未设置基准。" : benchmarkDiff >= 0 ? `跑赢基准 ${pct(benchmarkDiff)}。` : `跑输基准 ${pct(Math.abs(benchmarkDiff))}。`}</p>
            <div className="row">
              <Badge tone={result.synthetic ? "info" : "neutral"}>{result.synthetic ? "SYNTHETIC · 仅演示" : result.snapshot?.source ? `来源 ${String(result.snapshot.source)}` : "来源未记录"}</Badge>
              <Badge tone="ok">成本后口径 · 已扣费用</Badge>
              <Badge tone="warn">样本内 · 未做样本外验证</Badge>
              <Badge tone="neutral">引擎 {result.engine_backend} {result.engine_version}</Badge>
            </div>
            <div className="conclusion-actions">
              <Button variant="primary" icon={SlidersHorizontal} onClick={scrollToWizard}>改参数再跑</Button>
              <Button variant="secondary" icon={GitCompare} disabled={!experimentId} onClick={() => experimentId && navigate(`/experiments?run=${encodeURIComponent(experimentId)}`)}>加入对比</Button>
              <Button variant="secondary" icon={Download} disabled={!experimentId} onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report`, `${experimentId}.html`)}>查看报告</Button>
              <Button variant="ghost" disabled={!experimentId} onClick={() => experimentId && navigate(`/research?run=${encodeURIComponent(experimentId)}`)}>检查稳健性</Button>
            </div>
          </div>
          <div className="metric-grid">
            <StatTile label="总收益" value={pct(result.metrics.total_return)} trend={result.metrics.total_return >= 0 ? "up" : "down"} tone={result.metrics.total_return >= 0 ? "up" : "down"} hint={`年化 ${pct(result.metrics.annualized_return)} · 胜率 ${pct(result.metrics.win_rate)}`} />
            <StatTile label="最大回撤" value={pct(result.metrics.max_drawdown)} tone="down" hint={`Calmar ${num(result.metrics.calmar ?? 0)}`} />
            <StatTile label="夏普" value={num(result.metrics.sharpe)} hint={`波动 ${pct(result.metrics.volatility ?? 0)} · Sortino ${num(result.metrics.sortino ?? 0)}`} />
            <StatTile label="交易次数" value={num(result.metrics.trade_count, 0)} hint={`换手 ${pct(result.metrics.turnover)} · 费用 ${money(fixedToYuan(result.metrics.total_fees))}`} />
          </div>
          <Tabs items={TAB_ITEMS.map((item) => item.id === "trades" ? { ...item, badge: result.trades.length } : item)} value={tab} onChange={setTab} ariaLabel="回测结果视图" />
          {tab === "equity" ? (
            <ChartCard title="净值与回撤" subtitle="上方净值（含基准，如后端返回），下方回撤" height={400}>
              {equitySeries.length ? <Chart series={equitySeries} height={400} ariaLabel="净值与回撤曲线" valueFormatter={(value) => value.toFixed(2)} /> : null}
            </ChartCard>
          ) : null}
          {tab === "monthly" ? (
            <div className="chart-row">
              <ChartCard title="月度收益" subtitle="最近 36 个月" height={300}>
                {monthlySeries.length ? <Chart series={monthlySeries} height={300} ariaLabel="月度收益柱状图" valueFormatter={(value) => `${value.toFixed(2)}%`} /> : null}
              </ChartCard>
              <Panel title="费用构成" subtitle="逐笔交易费用汇总">
                <div className="stack-tight">
                  <div className="kv"><span>佣金</span><strong>{money(fees.commission)}</strong></div>
                  <div className="kv"><span>印花税</span><strong>{money(fees.stamp)}</strong></div>
                  <div className="kv"><span>过户费</span><strong>{money(fees.transfer)}</strong></div>
                  <div className="kv"><span>其他</span><strong>{money(fees.other)}</strong></div>
                  <div className="kv"><span>合计</span><strong>{money(fees.total)}</strong></div>
                  <div className="row" style={{ marginTop: "var(--sp-5)" }}>
                    {Object.entries(result.reasons).length ? Object.entries(result.reasons).map(([key, value]) => <Badge key={key} tone="neutral">{key}: {value}</Badge>) : <span className="page-note-sm">无 trace 原因码</span>}
                  </div>
                  <p className="page-note-sm">期末：现金 {money(result.cash.at(-1))} · 持仓市值 {money(result.market_value.at(-1))} · 总权益 {money(result.equity.at(-1))}。后端不返回逐证券持仓明细，这里不生成假持仓。</p>
                </div>
              </Panel>
            </div>
          ) : null}
          {tab === "trades" ? (
            <Panel title="逐笔交易" subtitle={`${result.trades.length} 笔 · ${result.engine_backend} ${result.engine_version}`} actions={<span className="page-note-sm">点击行查看交易解释与 K 线</span>}>
              <VirtualTable data={result.trades} columns={tradeColumns} rowKey={(trade) => `${trade.date}-${trade.sec_id ?? trade.sec_index ?? ""}-${trade.side}-${trade.qty}`} height={320} onRowClick={(trade) => { setSelectedTrade(trade); setTab("explain"); }} initialSorting={[{ id: "date", desc: true }]} ariaLabel="逐笔交易" empty={<span className="text-3">该回测没有成交。</span>} />
            </Panel>
          ) : null}
          {tab === "explain" ? (
            <Panel title="交易解释" subtitle={selectedTrade ? "费用拆分与原因码；K 线定位买卖点" : "从「交易明细」选择一笔交易"} actions={selectedTrade ? <Button variant="ghost" size="sm" onClick={() => setSelectedTrade(null)}>关闭</Button> : null}>
              {!selectedTrade ? <EmptyState title="还没有选择交易" hint="在「交易明细」点任意一行，这里会显示费用拆分、原因码和该证券的 K 线。" /> : (
                <div className="stack">
                  <div className="grid grid-4">
                    <div className="kv"><span>日期</span><strong>{dateInt(selectedTrade.date)}</strong></div>
                    <div className="kv"><span>证券</span><strong>{selectedTrade.sec_id || selectedTrade.sec_index}</strong></div>
                    <div className="kv"><span>方向</span><strong className={selectedTrade.side === 0 ? "up" : "down"}>{selectedTrade.side === 0 ? "买入" : "卖出"}</strong></div>
                    <div className="kv"><span>价格</span><strong>{money(selectedTrade.px_yuan)}</strong></div>
                    <div className="kv"><span>数量</span><strong>{num(selectedTrade.qty, 0)}</strong></div>
                    <div className="kv"><span>成交额</span><strong>{money(selectedTrade.amount_yuan)}</strong></div>
                    <div className="kv"><span>费用</span><strong>{money(fixedToYuan(selectedTrade.fee_total))}</strong></div>
                    <div className="kv"><span>方向现金流</span><strong>{money((selectedTrade.side === 1 ? 1 : -1) * (selectedTrade.amount_yuan ?? 0))}</strong></div>
                  </div>
                  <p className="page-note-sm">费用：佣金 {money(fixedToYuan(selectedTrade.commission))} · 印花税 {money(fixedToYuan(selectedTrade.stamp_duty))} · 过户费 {money(fixedToYuan(selectedTrade.transfer_fee))} · 其他 {money(fixedToYuan(selectedTrade.other_fee))}。原因码 {selectedTrade.reason}（{selectedTrade.reason_name || "—"}）。</p>
                  <p className="page-note-sm">后端逐笔结果没有已实现盈亏字段，因此不伪造「收益贡献」；方向现金流只是买卖成交额的符号，不是盈亏。</p>
                  {tradeCode ? (tradeBars.data ? <KLineChart bars={tradeBars.data} palette={palette} height={280} /> : tradeBars.error ? <EmptyState title="K 线加载失败" hint={tradeBars.error.message} /> : <Skeleton rows={3} />) : <p className="page-note-sm">无法从证券列表定位该交易代码（sec_id={selectedTrade.sec_id}）。</p>}
                </div>
              )}
            </Panel>
          ) : null}
          <p className="page-note-sm">实验 {experimentId || "—"} · 引擎 {result.engine_backend} · seed {result.seed}。{t.disclaimer}</p>
        </>
      ) : null}
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
