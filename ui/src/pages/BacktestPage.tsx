import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Download, Play, RotateCcw, Square } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { useBars, useCancelJob, useExperimentResult, useReplayExperiment, useSecurities, useSubmitBacktest, useTemplates } from "../api/queries";
import { downloadWithAuth } from "../api/client";
import type { BacktestResultPayload, Trade } from "../api/types";
import Chart from "../components/Chart";
import KLineChart from "../components/KLineChart";
import { MetricCard } from "../components/MetricCard";
import StatePanel from "../components/StatePanel";
import { useJobProgress } from "../hooks/useJobProgress";
import { dateInt, fixedToYuan, money, monthKey, num, pct } from "../lib/format";
import { useChartPalette } from "../theme";
import { useWorkspace, type BacktestDraft } from "../store/workspace";
import type { ColumnDef } from "@tanstack/react-table";
import VirtualTable from "../components/VirtualTable";
import { zhCN as t } from "../i18n/zh-CN";

const DEFAULTS: BacktestDraft = {
  template: "momentum", paramsText: '{"top_n": 10, "lookback": 60}', start: "2022-01-04", end: "2024-12-31", cash: "1000000",
  exec: "next_open", commissionRate: "0.03", minCommission: "5", stampDutyRate: "0.05", slippageBps: "0", maxParticipation: "1",
  minRebalanceValue: "0", trace: "summary", seed: "42",
};

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
  const palette = useChartPalette();
  const templates = useTemplates();
  const submit = useSubmitBacktest();
  const cancel = useCancelJob();
  const replay = useReplayExperiment();
  const securities = useSecurities("", 1000);
  const stored = useWorkspace.getState().backtestDraft;
  const [draft, setDraft] = useState<BacktestDraft>(() => ({
    ...DEFAULTS,
    ...stored,
    template: searchParams.get("template") || stored.template || DEFAULTS.template,
    paramsText: searchParams.get("params") || stored.paramsText || DEFAULTS.paramsText,
  }));
  const [jobId, setJobId] = useState<string | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [error, setError] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [replayMessage, setReplayMessage] = useState("");
  const [notice, setNotice] = useState("");
  const setDraftStore = useWorkspace((state) => state.setBacktestDraft);
  const progress = useJobProgress(jobId);
  const resetSubmit = submit.reset;
  const resultQuery = useExperimentResult(experimentId || null);
  const result = resultQuery.data ?? null;

  useEffect(() => { setDraftStore(draft); }, [draft, setDraftStore]);
  useEffect(() => {
    const job = progress.job;
    if (!job) return;
    if (job.status === "done") {
      const runId = typeof job.result?.run_id === "string" ? job.result.run_id : "";
      if (runId) { setExperimentId(runId); setNotice(`实验已保存：${runId}`); }
      else setError("任务完成但没有返回 run_id；请检查后端实验存储。");
      resetSubmit();
    } else if (job.status === "failed" || job.status === "cancelled") {
      setError(job.error || (job.status === "cancelled" ? "已取消" : "回测失败"));
      resetSubmit();
    }
  }, [progress.job, resetSubmit]);
  useEffect(() => { setSelectedTrade(null); }, [experimentId]);

  const update = (key: keyof BacktestDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const run = () => {
    setError(""); setNotice(""); setReplayMessage(""); setExperimentId("");
    try {
      const params: unknown = JSON.parse(draft.paramsText);
      if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("参数必须是 JSON 对象");
      const config = {
        start: draft.start, end: draft.end, initial_cash: Number(draft.cash), trace: draft.trace, seed: Number(draft.seed),
        costs: {
          commission_rate: Number(draft.commissionRate) / 100, min_commission: Number(draft.minCommission),
          stamp_duty_rate: Number(draft.stampDutyRate) / 100, transfer_fee_rate: 0.00001, exchange_fee_rate: 0.00001, reg_fee_rate: 0.000002,
        },
        exec: { type: draft.exec, slippage_bps: Number(draft.slippageBps) || 0, max_participation: Number(draft.maxParticipation) || 1, min_rebalance_value: Number(draft.minRebalanceValue) || 0 },
      };
      submit.mutate({ template: draft.template, params, config }, {
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

  const equityOption = useMemo<EChartsOption | null>(() => {
    if (!result) return null;
    const drawdown = result.equity.map((value, index) => {
      const peak = Math.max(...result.equity.slice(0, index + 1));
      return peak > 0 ? (value / peak - 1) * 100 : 0;
    });
    return {
      animation: false, tooltip: { trigger: "axis" }, legend: { data: ["净值", "回撤"], top: 0, textStyle: { fontSize: 11 } },
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
  return (
    <>
      <div className="page-head">
        <div><h1>回测</h1><p>任务进度/取消 · 净值与回撤 · 指标 · 月度收益 · 费用 · 交易解释 · 实验复现</p></div>
        <div className="button-row">
          <button className="btn" onClick={() => void onReplay()} disabled={!experimentId}><RotateCcw size={15} /> 复现</button>
          <button className="btn" onClick={() => experimentId && void downloadWithAuth(`/api/experiments/${experimentId}/report`, `${experimentId}.html`)} disabled={!experimentId}><Download size={15} /> 报告</button>
          {running ? <button className="btn danger" onClick={() => void onCancel()}><Square size={15} /> 取消</button> : <button className="btn primary" onClick={run} disabled={submit.isPending}><Play size={15} /> 运行回测</button>}
        </div>
      </div>
      <div className="grid backtest-layout">
        <div className="card">
          <label className="field-label">模板</label>
          <select value={draft.template} onChange={(event) => update("template", event.target.value)}>
            {(templates.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}
            {!templates.data?.length ? <option value={draft.template}>{draft.template}</option> : null}
          </select>
          <label className="field-label">模板参数 JSON</label>
          <textarea className="code-input" rows={4} value={draft.paramsText} onChange={(event) => update("paramsText", event.target.value)} spellCheck={false} />
          <div className="form-grid two">
            <label>开始<input value={draft.start} onChange={(event) => update("start", event.target.value)} placeholder="YYYY-MM-DD" /></label>
            <label>结束<input value={draft.end} onChange={(event) => update("end", event.target.value)} placeholder="YYYY-MM-DD" /></label>
            <label>初始资金（元）<input value={draft.cash} onChange={(event) => update("cash", event.target.value)} inputMode="decimal" /></label>
            <label>成交规则<select value={draft.exec} onChange={(event) => update("exec", event.target.value)}><option value="next_open">次日开盘</option><option value="next_close">次日收盘</option><option value="next_vwap">次日 VWAP</option><option value="after_hours_fixed">盘后固定价</option></select></label>
            <label>基准<select disabled title="后端 BacktestConfig 暂未提供基准字段（契约偏差）；不发送。"><option>沪深 300（后端暂未支持）</option></select></label>
            <label>滑点（bp）<input value={draft.slippageBps} onChange={(event) => update("slippageBps", event.target.value)} inputMode="decimal" /></label>
          </div>
          <details className="advanced" open={advanced} onToggle={(event) => setAdvanced((event.target as HTMLDetailsElement).open)}>
            <summary><ChevronDown size={15} /> 高级：费用 / 成交 / 调试</summary>
            <div className="form-grid two">
              <label>佣金率（%）<input value={draft.commissionRate} onChange={(event) => update("commissionRate", event.target.value)} inputMode="decimal" /></label>
              <label>最低佣金（元）<input value={draft.minCommission} onChange={(event) => update("minCommission", event.target.value)} inputMode="decimal" /></label>
              <label>印花税（%）<input value={draft.stampDutyRate} onChange={(event) => update("stampDutyRate", event.target.value)} inputMode="decimal" /></label>
              <label>最大参与率<input value={draft.maxParticipation} onChange={(event) => update("maxParticipation", event.target.value)} inputMode="decimal" /></label>
              <label>最小调仓额（元）<input value={draft.minRebalanceValue} onChange={(event) => update("minRebalanceValue", event.target.value)} inputMode="decimal" /></label>
              <label>trace<select value={draft.trace} onChange={(event) => update("trace", event.target.value)}><option value="off">off</option><option value="summary">summary</option><option value="full">full</option></select></label>
              <label>seed<input value={draft.seed} onChange={(event) => update("seed", event.target.value)} inputMode="numeric" /></label>
            </div>
            <p className="muted small">费用按「百分比」输入并换算为小数传给后端；调仓频率当前由模板参数控制。基准字段后端未实现，已禁用而非伪造。</p>
          </details>
          {progress.job ? <div className="progress" role="status"><div className="progress-bar" style={{ width: `${Math.round(progress.job.progress * 100)}%` }} /><span>{progress.job.status} · {Math.round(progress.job.progress * 100)}% · {progress.transport ?? "等待"}</span></div> : null}
          {error ? <p className="error" role="alert">{error}</p> : null}
          {notice ? <p className="success-text">{notice}</p> : null}
          {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error"}>{replayMessage}</p> : null}
          <p className="muted small">实验会自动保存到 experiments/；结果仅用于研究，不构成投资建议。</p>
        </div>
        <div className="card result-card">
          {!result && !running && !resultQuery.isLoading ? <StatePanel empty emptyHint="填写参数并运行回测；任务会通过 WS 推送进度，完成后展示净值、交易与费用。" /> : null}
          {(running || resultQuery.isLoading) ? <StatePanel loading /> : null}
          {resultQuery.error ? <StatePanel error={resultQuery.error.message} onRetry={() => void resultQuery.refetch()} /> : null}
          {result ? (
            <>
              <div className="grid kpis">
                <MetricCard label="总收益" value={pct(result.metrics.total_return)} tone={result.metrics.total_return >= 0 ? "up" : "down"} />
                <MetricCard label="年化" value={pct(result.metrics.annualized_return)} tone={result.metrics.annualized_return >= 0 ? "up" : "down"} />
                <MetricCard label="Sharpe" value={num(result.metrics.sharpe)} />
                <MetricCard label="最大回撤" value={pct(result.metrics.max_drawdown)} tone="down" />
                <MetricCard label="胜率" value={pct(result.metrics.win_rate)} />
                <MetricCard label="费用" value={money(fixedToYuan(result.metrics.total_fees))} />
              </div>
              <div className="chart-block">{equityOption ? <Chart option={equityOption} height={360} /> : null}</div>
              <div className="grid two-col">
                <div className="card"><h3>月度收益</h3>{monthlyOption ? <Chart option={monthlyOption} height={220} /> : null}</div>
                <div className="card"><h3>费用构成</h3><div className="fee-list"><span>佣金 <strong>{money(fees.commission)}</strong></span><span>印花税 <strong>{money(fees.stamp)}</strong></span><span>过户费 <strong>{money(fees.transfer)}</strong></span><span>其他 <strong>{money(fees.other)}</strong></span><span>合计 <strong>{money(fees.total)}</strong></span></div><h3 style={{ marginTop: 12 }}>reasons</h3><div className="reason-list">{Object.entries(result.reasons).length ? Object.entries(result.reasons).map(([key, value]) => <span key={key} className="badge">{key}: {value}</span>) : <span className="muted small">无 trace 原因码</span>}</div></div>
              </div>
              <div className="card" style={{ marginTop: 12 }}><h3>组合状态（期末）</h3><div className="metric-inline"><span>现金 <strong>{money(result.cash.at(-1))}</strong></span><span>持仓市值 <strong>{money(result.market_value.at(-1))}</strong></span><span>总权益 <strong>{money(result.equity.at(-1))}</strong></span><span>交易笔数 <strong>{result.trades.length}</strong></span></div><p className="muted small">后端实验 result 当前只返回现金/持仓市值序列，没有逐证券持仓明细；这里不生成假持仓。逐笔交易见下表。</p></div>
              <div className="card-head"><h3>逐笔交易 <span className="muted small">{result.trades.length} 笔 · {result.engine_backend} {result.engine_version}</span></h3><span className="muted small">点击行查看解释与 K 线</span></div>
              <VirtualTable data={result.trades} columns={tradeColumns} rowKey={(trade) => `${trade.date}-${trade.sec_id ?? trade.sec_index ?? ""}-${trade.side}-${trade.qty}`} height={280} onRowClick={setSelectedTrade} initialSorting={[{ id: "date", desc: true }]} ariaLabel="逐笔交易" empty={<span className="muted">该回测没有成交。</span>} />
              {selectedTrade ? (
                <div className="trade-detail">
                  <div className="card-head"><h3>交易解释</h3><button className="btn ghost" onClick={() => setSelectedTrade(null)}>关闭</button></div>
                  <div className="trade-detail-grid">
                    <span>日期 <strong>{dateInt(selectedTrade.date)}</strong></span><span>证券 <strong>{selectedTrade.sec_id || selectedTrade.sec_index}</strong></span>
                    <span>方向 <strong className={selectedTrade.side === 0 ? "up" : "down"}>{selectedTrade.side === 0 ? "买入" : "卖出"}</strong></span>
                    <span>价格 <strong>{money(selectedTrade.px_yuan)}</strong></span><span>数量 <strong>{num(selectedTrade.qty, 0)}</strong></span>
                    <span>成交额 <strong>{money(selectedTrade.amount_yuan)}</strong></span><span>费用 <strong>{money(fixedToYuan(selectedTrade.fee_total))}</strong></span>
                    <span>方向现金流 <strong>{money((selectedTrade.side === 1 ? 1 : -1) * (selectedTrade.amount_yuan ?? 0))}</strong></span>
                  </div>
                  <p className="muted small">费用：佣金 {money(fixedToYuan(selectedTrade.commission))} · 印花税 {money(fixedToYuan(selectedTrade.stamp_duty))} · 过户费 {money(fixedToYuan(selectedTrade.transfer_fee))} · 其他 {money(fixedToYuan(selectedTrade.other_fee))}。</p>
                  <p className="muted small">原因码 {selectedTrade.reason}（{selectedTrade.reason_name || "—"}）。后端逐笔结果没有已实现盈亏字段，因此这里不伪造“收益贡献”；方向现金流显示买卖成交额的符号，不是盈亏。</p>
                  {tradeCode ? (tradeBars.data ? <KLineChart bars={tradeBars.data} palette={palette} height={260} /> : tradeBars.error ? <StatePanel error={tradeBars.error.message} /> : <StatePanel loading />) : <p className="muted small">无法从证券列表定位该交易代码（sec_id={selectedTrade.sec_id}）。</p>}
                </div>
              ) : null}
              <p className="muted small">实验 {experimentId || "—"} · 引擎 {result.engine_backend} · seed {result.seed}。历史表现不代表未来，不构成投资建议。</p>
            </>
          ) : null}
        </div>
      </div>
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
