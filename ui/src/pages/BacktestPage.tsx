import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Play, Square } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api, getApiBase, getToken } from "../api/client";
import type { BacktestResultPayload, Job, Trade } from "../api/types";
import Chart from "../components/Chart";
import { MetricCard } from "../components/MetricCard";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

const pct = (value: number) => `${(value * 100).toFixed(2)}%`;
const money = (value: number) => `¥${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export default function BacktestPage() {
  const [searchParams] = useSearchParams();
  const [template, setTemplate] = useState(searchParams.get("template") || "momentum");
  const [paramsText, setParamsText] = useState(searchParams.get("params") || '{"top_n": 10, "lookback": 60}');
  const [start, setStart] = useState("2022-01-04");
  const [end, setEnd] = useState("2024-12-31");
  const [cash, setCash] = useState("1000000");
  const [exec, setExec] = useState("next_open");
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<BacktestResultPayload | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const timer = useRef<number | null>(null);

  const stopPoll = () => { if (timer.current !== null) { window.clearInterval(timer.current); timer.current = null; } };
  useEffect(() => stopPoll, []);

  const loadResult = useCallback(async (runId: string) => {
    const [summary, payload] = await Promise.all([api.experiment(runId), api.experimentResult(runId)]);
    setResult(payload);
    setSelectedTrade(null);
    setExperimentId(runId);
    const report = String((summary as { summary?: { report?: string } }).summary?.report || "");
    if (report) localStorage.setItem("qc_last_report", report);
  }, []);

  const poll = useCallback((jobId: string) => {
    stopPoll();
    timer.current = window.setInterval(async () => {
      try {
        const current = await api.job(jobId);
        setJob(current);
        if (current.status === "done") {
          stopPoll(); setBusy(false);
          const runId = String((current.result as { run_id?: string } | null)?.run_id || "");
          if (runId) await loadResult(runId);
        } else if (current.status === "failed" || current.status === "cancelled") {
          stopPoll(); setBusy(false); setError(current.error || current.status);
        }
      } catch (e) { stopPoll(); setBusy(false); setError(`${e}`); }
    }, 500);
  }, [loadResult]);

  const submit = async () => {
    setError(""); setResult(null); setExperimentId(""); setBusy(true); setJob(null);
    try {
      const params = JSON.parse(paramsText);
      const response = await api.submitBacktest({ template, params, config: { start, end, initial_cash: Number(cash), exec: { type: exec } } });
      poll(response.job_id);
    } catch (e) { setBusy(false); setError(`${e}`); }
  };
  const cancel = async () => { if (job) { await api.cancelJob(job.id); } };

  const equityOption = useMemo(() => {
    if (!result) return null;
    const equity = result.equity;
    const drawdown = equity.map((value, index) => {
      const peak = Math.max(...equity.slice(0, index + 1));
      return peak > 0 ? (value / peak - 1) * 100 : 0;
    });
    return {
      animation: false,
      tooltip: { trigger: "axis" as const },
      legend: { data: ["净值 (元)", "回撤 (%)"], top: 0, textStyle: { fontSize: 11 } },
      grid: [{ left: 70, right: 50, top: 30, height: "55%" }, { left: 70, right: 50, top: "75%", height: "16%" }],
      xAxis: [
        { type: "category" as const, data: result.dates.map((d) => String(d)), axisLabel: { fontSize: 10 } },
        { type: "category" as const, data: result.dates.map((d) => String(d)), gridIndex: 1, axisLabel: { show: false }, axisTick: { show: false } },
      ],
      yAxis: [
        { type: "value" as const, scale: true, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
        { type: "value" as const, gridIndex: 1, axisLabel: { formatter: "{value}%", fontSize: 10 }, splitNumber: 2 },
      ],
      dataZoom: [{ type: "inside" as const, xAxisIndex: [0, 1], start: 0, end: 100 }],
      series: [
        { name: "净值 (元)", type: "line" as const, data: equity, showSymbol: false, lineStyle: { width: 1.7, color: "#2563eb" }, areaStyle: { opacity: 0.05 } },
        { name: "回撤 (%)", type: "line" as const, xAxisIndex: 1, yAxisIndex: 1, data: drawdown, showSymbol: false, lineStyle: { width: 1, color: "#ef4444" }, areaStyle: { opacity: 0.18 } },
      ],
    };
  }, [result]);

  const downloadReport = async () => {
    if (!experimentId) return;
    const response = await fetch(`${getApiBase()}/api/experiments/${experimentId}/report`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  };

  return (
    <>
      <div className="page-head"><div><h1>回测</h1><p>净值/回撤 · 指标 · 逐笔交易 · 实验复现</p></div>
        <div className="button-row"><button className="btn" onClick={() => void downloadReport()} disabled={!experimentId}><Download size={15} /> HTML 报告</button>{busy ? <button className="btn danger" onClick={() => void cancel()}><Square size={15} /> 取消</button> : <button className="btn primary" onClick={() => void submit()} disabled={busy}><Play size={15} /> 运行回测</button>}</div>
      </div>
      <div className="grid backtest-layout">
        <div className="card">
          <label className="field-label">模板</label>
          <select value={template} onChange={(e) => setTemplate(e.target.value)}>
            <option value="buy_and_hold">买入持有</option><option value="dual_ma">双均线</option><option value="momentum">动量</option><option value="low_vol">低波动</option><option value="dividend_quality">红利质量</option><option value="small_cap_liquidity">小市值+流动性</option><option value="multi_factor">多因子</option>
          </select>
          <label className="field-label">参数 JSON</label>
          <textarea className="code-input" rows={4} value={paramsText} onChange={(e) => setParamsText(e.target.value)} spellCheck={false} />
          <div className="form-grid two">
            <label>开始<input value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <label>结束<input value={end} onChange={(e) => setEnd(e.target.value)} /></label>
            <label>初始资金<input value={cash} onChange={(e) => setCash(e.target.value)} inputMode="decimal" /></label>
            <label>成交<select value={exec} onChange={(e) => setExec(e.target.value)}><option value="next_open">次日开盘</option><option value="next_close">次日收盘</option><option value="next_vwap">次日 VWAP</option></select></label>
          </div>
          {job ? <div className="progress"><div className="progress-bar" style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /><span>{job.status} · {Math.round((job.progress || 0) * 100)}%</span></div> : null}
          {error ? <p className="error">{error}</p> : null}
          <p className="muted small">{t.disclaimer}</p>
        </div>
        <div className="card result-card">
          {busy && !result ? <StatePanel loading /> : null}
          {!busy && !result ? <StatePanel empty emptyHint="填写参数并运行回测；结果会写入实验。" /> : null}
          {result ? (
            <>
              <div className="grid kpis">
                <MetricCard label="总收益" value={pct(result.metrics.total_return)} tone={result.metrics.total_return >= 0 ? "up" : "down"} />
                <MetricCard label="年化" value={pct(result.metrics.annualized_return)} tone={result.metrics.annualized_return >= 0 ? "up" : "down"} />
                <MetricCard label="Sharpe" value={result.metrics.sharpe.toFixed(2)} />
                <MetricCard label="最大回撤" value={pct(result.metrics.max_drawdown)} tone="down" />
                <MetricCard label="换手" value={result.metrics.turnover.toFixed(2)} />
                <MetricCard label="费用" value={money(result.metrics.total_fees / 10000)} />
              </div>
              <div className="chart-block">{equityOption ? <Chart option={equityOption} height={360} /> : null}</div>
              <div className="card-head"><h3>逐笔交易 <span className="muted small">{result.trades.length} 笔 · 引擎 {result.engine_version}</span></h3></div>
              <div className="table-wrap trades">
                <table><thead><tr><th>日期</th><th>证券</th><th>方向</th><th className="num">价格</th><th className="num">数量</th><th className="num">费用</th><th>原因</th></tr></thead>
                  <tbody>{result.trades.slice(0, 200).map((trade, index) => <tr key={`${trade.date}-${index}`} className={selectedTrade === trade ? "selected" : ""} onClick={() => setSelectedTrade(trade)}><td>{trade.date}</td><td>{trade.sec_id || trade.sec_index}</td><td className={trade.side === 0 ? "up" : "down"}>{trade.side === 0 ? "买入" : "卖出"}</td><td className="num">{trade.px_yuan?.toFixed(2) ?? trade.px}</td><td className="num">{trade.qty}</td><td className="num">{money((trade.fee_total || 0) / 10000)}</td><td>{trade.reason_name === "none" ? "调仓" : trade.reason_name || trade.reason}</td></tr>)}</tbody>
                </table>
              </div>
              {selectedTrade ? (
                <div className="trade-detail">
                  <div className="card-head"><h3>交易解释</h3><button className="btn ghost" onClick={() => setSelectedTrade(null)}>关闭</button></div>
                  <div className="trade-detail-grid">
                    <span>日期 <strong>{selectedTrade.date}</strong></span>
                    <span>证券 <strong>{selectedTrade.sec_id || selectedTrade.sec_index}</strong></span>
                    <span>方向 <strong className={selectedTrade.side === 0 ? "up" : "down"}>{selectedTrade.side === 0 ? "买入" : "卖出"}</strong></span>
                    <span>价格 <strong>{money(selectedTrade.px_yuan ?? 0)}</strong></span>
                    <span>数量 <strong>{selectedTrade.qty.toLocaleString()}</strong></span>
                    <span>成交额 <strong>{money(selectedTrade.amount_yuan ?? 0)}</strong></span>
                  </div>
                  <p className="muted small">费用：佣金 {money((selectedTrade.commission || 0) / 10000)} · 印花税 {money((selectedTrade.stamp_duty || 0) / 10000)} · 过户费 {money((selectedTrade.transfer_fee || 0) / 10000)} · 其他 {money((selectedTrade.other_fee || 0) / 10000)} · 合计 {money((selectedTrade.fee_total || 0) / 10000)}</p>
                  <p className="muted small">触发原因：{selectedTrade.reason_name === "none" ? "目标权重调仓（多标的再平衡，按卖出优先、现金约束与最小调仓额执行）" : selectedTrade.reason_name}。引擎 trace={result.reasons ? JSON.stringify(result.reasons) : "off"}。</p>
                </div>
              ) : null}
              <p className="muted small">实验 {experimentId}；点击任一笔交易查看成本与触发解释。结果仅用于研究，不构成投资建议。</p>
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}
