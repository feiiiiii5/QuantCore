import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { Gauge, Play, ShieldCheck } from "lucide-react";
import type { Experiment } from "../api/types";
import {
  useCapacity,
  useCostSensitivity,
  useMonteCarlo,
  useOverfitting,
  usePBO,
} from "../api/queries";
import Chart from "./Chart";
import { chartToken } from "../lib/tokens";

const pct = (value: number | undefined) => `${((value ?? 0) * 100).toFixed(2)}%`;
const money = (value: number | undefined) => `¥${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function RobustnessPanel({ experiments }: { experiments: Experiment[] }) {
  const [runId, setRunId] = useState("");
  const [nTrials, setNTrials] = useState("10");
  const [pboIds, setPboIds] = useState<string[]>([]);
  const [nSplits, setNSplits] = useState("8");
  const [multipliers, setMultipliers] = useState("0, 0.5, 1, 2, 3");
  const [nPaths, setNPaths] = useState("500");
  const [horizon, setHorizon] = useState("250");
  const [participation, setParticipation] = useState("0.1");
  const [formError, setFormError] = useState("");

  const overfitting = useOverfitting();
  const pbo = usePBO();
  const cost = useCostSensitivity();
  const monteCarlo = useMonteCarlo();
  const capacity = useCapacity();
  const busy = overfitting.isPending || pbo.isPending || cost.isPending || monteCarlo.isPending || capacity.isPending;
  const error = formError || [overfitting.error, pbo.error, cost.error, monteCarlo.error, capacity.error].find(Boolean)?.message || "";

  useEffect(() => {
    if (!runId && experiments.length) setRunId(experiments[0].run_id);
  }, [runId, experiments]);

  const togglePbo = (id: string) => {
    setPboIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };

  const runOverfitting = () => {
    if (!runId) { setFormError("请先选择实验"); return; }
    setFormError("");
    overfitting.mutate({ run_id: runId, n_trials: Number(nTrials) || 1 });
  };
  const runPbo = () => {
    if (pboIds.length < 2) { setFormError("PBO 至少选择 2 个实验"); return; }
    setFormError("");
    pbo.mutate({ run_ids: pboIds, n_splits: Number(nSplits) || 8 });
  };
  const runCost = () => {
    if (!runId) { setFormError("请先选择实验"); return; }
    setFormError("");
    try {
      const values = multipliers.split(",").map((part) => Number(part.trim())).filter((value) => Number.isFinite(value));
      cost.mutate({ run_id: runId, multipliers: values });
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : "成本倍数无效"); }
  };
  const runMonteCarlo = () => {
    if (!runId) { setFormError("请先选择实验"); return; }
    setFormError("");
    monteCarlo.mutate({ run_id: runId, n_paths: Number(nPaths) || 500, horizon: Number(horizon) || 250 });
  };
  const runCapacity = () => {
    if (!runId) { setFormError("请先选择实验"); return; }
    setFormError("");
    capacity.mutate({ run_id: runId, adv_participation: Number(participation) || 0.1 });
  };

  const overResult = overfitting.data;
  const costOption = useMemo<EChartsOption | null>(() => {
    if (!cost.data?.points.length) return null;
    return {
      animation: false, tooltip: { trigger: "axis" }, legend: { top: 0, data: ["总收益", "Sharpe"] },
      grid: { left: 50, right: 50, top: 30, bottom: 34 },
      xAxis: { type: "category", data: cost.data.points.map((point) => `${point.multiplier}×`) },
      yAxis: [
        { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
        { type: "value", splitLine: { show: false } },
      ],
      series: [
        { name: "总收益", type: "bar", data: cost.data.points.map((point) => point.total_return * 100), itemStyle: { color: chartToken("--primary", "#2563eb") } },
        { name: "Sharpe", type: "line", yAxisIndex: 1, data: cost.data.points.map((point) => point.sharpe), lineStyle: { color: chartToken("--warn", "#eab308") }, symbolSize: 5 },
      ],
    };
  }, [cost.data]);
  const mcOption = useMemo<EChartsOption | null>(() => {
    if (!monteCarlo.data?.paths.length) return null;
    const paths = monteCarlo.data.paths.slice(0, 12);
    return {
      animation: false, tooltip: { trigger: "axis" }, legend: { top: 0, data: ["路径", "中位路径"] },
      grid: { left: 50, right: 20, top: 30, bottom: 30 },
      xAxis: { type: "category", data: Array.from({ length: monteCarlo.data.horizon + 1 }, (_, index) => String(index)) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
      series: [
        ...paths.map((path, index) => ({ name: `路径${index + 1}`, type: "line" as const, data: path.map((value) => value * 100), showSymbol: false, lineStyle: { width: 1, opacity: 0.35 }, silent: true })),
        { name: "中位路径", type: "line" as const, data: (() => {
          const rows = monteCarlo.data?.paths ?? [];
          if (!rows.length) return [];
          const length = Math.min(...rows.map((row) => row.length));
          return Array.from({ length }, (_, index) => {
            const values = rows.map((row) => row[index]).sort((a, b) => a - b);
            return values[Math.floor(values.length / 2)] * 100;
          });
        })(), showSymbol: false, lineStyle: { width: 2, color: chartToken("--primary", "#2563eb") } },
      ],
    };
  }, [monteCarlo.data]);

  return (
    <div className="grid two-col">
      {error ? <p className="error" role="alert" style={{ gridColumn: "1 / -1" }}>{error}</p> : null}
      <div className="card">
        <div className="card-head"><h3><ShieldCheck size={16} /> 实验与过拟合</h3></div>
        <label className="field-label">实验</label>
        <select value={runId} onChange={(event) => setRunId(event.target.value)}>
          {experiments.map((item) => <option key={item.run_id} value={item.run_id}>{item.strategy_name || item.template} · {item.run_id.slice(-8)}</option>)}
        </select>
        <div className="form-grid two" style={{ marginTop: 10 }}>
          <label>试验次数<input value={nTrials} onChange={(event) => setNTrials(event.target.value)} inputMode="numeric" /></label>
          <label>成本倍数<input value={multipliers} onChange={(event) => setMultipliers(event.target.value)} /></label>
          <label>MC 路径数<input value={nPaths} onChange={(event) => setNPaths(event.target.value)} inputMode="numeric" /></label>
          <label>MC 期限<input value={horizon} onChange={(event) => setHorizon(event.target.value)} inputMode="numeric" /></label>
        </div>
        <div className="button-row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={busy || !runId} onClick={runOverfitting}><Play size={14} /> Deflated Sharpe</button>
          <button className="btn" disabled={busy || !runId} onClick={runCost}>成本敏感性</button>
          <button className="btn" disabled={busy || !runId} onClick={runMonteCarlo}>Monte Carlo</button>
          <button className="btn" disabled={busy || !runId} onClick={runCapacity}>容量</button>
        </div>
        <label className="field-label" style={{ marginTop: 10 }}>容量参与率<input value={participation} onChange={(event) => setParticipation(event.target.value)} inputMode="decimal" /></label>
        {overResult ? (
          <div className="grid kpis" style={{ marginTop: 12 }}>
            <div><h3>Sharpe</h3><div className="kpi">{overResult.sharpe.toFixed(2)}</div></div>
            <div><h3>Deflated Sharpe</h3><div className={`kpi ${overResult.deflated_sharpe >= 0.95 ? "up" : "down"}`}>{overResult.deflated_sharpe.toFixed(3)}</div></div>
            <div><h3>判定</h3><div className="kpi">{overResult.verdict}</div></div>
            <div><h3>期望最大 Sharpe</h3><div className="kpi">{overResult.expected_max_sharpe.toFixed(2)}</div></div>
          </div>
        ) : null}
        {overResult ? <p className="muted small">观测 {overResult.observations} 日 · 偏度 {overResult.skew.toFixed(2)} · 峰度 {overResult.kurtosis.toFixed(2)} · DSR≥0.95 视为稳健。</p> : null}
        {monteCarlo.data ? (
          <div className="grid kpis" style={{ marginTop: 12 }}>
            <div><h3>终值 P05</h3><div className="kpi down">{pct(monteCarlo.data.terminal_return.p05)}</div></div>
            <div><h3>终值 P50</h3><div className="kpi">{pct(monteCarlo.data.terminal_return.p50)}</div></div>
            <div><h3>终值 P95</h3><div className="kpi up">{pct(monteCarlo.data.terminal_return.p95)}</div></div>
            <div><h3>最大回撤 P50</h3><div className="kpi down">{pct(monteCarlo.data.max_drawdown.p50)}</div></div>
          </div>
        ) : null}
        {capacity.data ? (
          <div className="card" style={{ marginTop: 12 }}>
            <h3><Gauge size={15} /> 容量估计</h3>
            <p>约 <strong>{money(capacity.data.capacity_cny)}</strong>（参与率 {pct(capacity.data.participation)}，日均换手 {pct(capacity.data.avg_turnover)}）</p>
            <p className="muted small">限制证券：{capacity.data.limiting_sec}；{capacity.data.notes}</p>
          </div>
        ) : null}
      </div>
      <div className="card">
        <div className="card-head"><h3>PBO（CSCV）</h3><span className="muted small">至少选择 2 个实验</span></div>
        <div className="pbo-list">
          {experiments.slice(0, 20).map((item) => (
            <label key={item.run_id} className="check-row">
              <input type="checkbox" checked={pboIds.includes(item.run_id)} onChange={() => togglePbo(item.run_id)} />
              <span>{item.strategy_name || item.template} · {item.run_id.slice(-8)}</span>
            </label>
          ))}
        </div>
        <div className="form-grid two">
          <label>切分数<input value={nSplits} onChange={(event) => setNSplits(event.target.value)} inputMode="numeric" /></label>
          <label>&nbsp;<button className="btn primary" disabled={busy || pboIds.length < 2} onClick={runPbo}><Play size={14} /> 运行 PBO</button></label>
        </div>
        {pbo.data ? (
          <>
            <div className="grid kpis" style={{ marginTop: 10 }}>
              <div><h3>PBO</h3><div className={`kpi ${pbo.data.pbo <= 0.5 ? "up" : "down"}`}>{pct(pbo.data.pbo)}</div></div>
              <div><h3>组合数</h3><div className="kpi">{pbo.data.combinations}</div></div>
              <div><h3>OOS 中位排名</h3><div className="kpi">{pbo.data.median_oos_rank.toFixed(1)}</div></div>
            </div>
            <p className="muted small">PBO 越低越好；这是 CSCV 的近似，样本区间重叠时会高估稳定性。</p>
          </>
        ) : <p className="muted small">选择多个实验（最好来自参数扫描）估计回测过拟合概率。</p>}
        {costOption ? <><div className="card-head" style={{ marginTop: 14 }}><h3>成本敏感性</h3>{cost.data?.breakeven_multiplier != null ? <span className="badge">盈亏平衡 {cost.data.breakeven_multiplier.toFixed(2)}×</span> : null}</div><Chart option={costOption} height={250} /></> : null}
        {mcOption ? <><div className="card-head" style={{ marginTop: 14 }}><h3>Monte Carlo 路径</h3><span className="muted small">{monteCarlo.data?.n_paths} 条 · {monteCarlo.data?.horizon} 日</span></div><Chart option={mcOption} height={250} /></> : null}
      </div>
    </div>
  );
}
