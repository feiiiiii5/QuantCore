import { useEffect, useState } from "react";
import { Gauge, Play, ShieldCheck } from "lucide-react";
import type { Experiment } from "../api/types";
import {
  useCapacity,
  useCostSensitivity,
  useMonteCarlo,
  useOverfitting,
  usePBO,
} from "../api/queries";
import Chart, { type ChartSeries } from "./Chart";
import Button from "./Button";
import Callout from "./Callout";
import Field from "./Field";
import Input from "./Input";
import Panel from "./Panel";
import Select from "./Select";
import StatTile from "./StatTile";

const pct = (value: number | undefined) => `${((value ?? 0) * 100).toFixed(2)}%`;
const money = (value: number | undefined) => `¥${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

/** English verdict → short Chinese label (raw value kept as hint). */
function verdictLabel(verdict: string): string {
  if (verdict === "robust") return "稳健";
  if (verdict === "likely_overfit") return "可能过拟合";
  if (verdict === "inconclusive") return "不确定";
  return verdict;
}

export default function RobustnessPanel({ experiments, initialRunId = "" }: { experiments: Experiment[]; initialRunId?: string }) {
  const [runId, setRunId] = useState(initialRunId);
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
    if (initialRunId) setRunId(initialRunId);
  }, [initialRunId]);
  const resetOverfitting = overfitting.reset, resetCost = cost.reset, resetMonteCarlo = monteCarlo.reset, resetCapacity = capacity.reset;
  useEffect(() => {
    resetOverfitting(); resetCost(); resetMonteCarlo(); resetCapacity(); setFormError("");
  }, [runId, resetOverfitting, resetCost, resetMonteCarlo, resetCapacity]);
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
    const values = multipliers.split(",").map((part) => Number(part.trim())).filter((value) => Number.isFinite(value));
    cost.mutate({ run_id: runId, multipliers: values });
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
  const experimentOptions = [...(runId && !experiments.some((item) => item.run_id === runId) ? [{ value: runId, label: `历史实验 · ${runId}` }] : []), ...experiments.map((item) => ({
    value: item.run_id,
    label: `${item.strategy_name || item.template} · ${item.run_id.slice(-8)}`,
  }))];

  const costSeries: ChartSeries[] = cost.data?.points.length
    ? [
        {
          kind: "histogram",
          title: "总收益 %",
          data: cost.data.points.map((point) => ({ time: point.multiplier, value: point.total_return * 100 })),
        },
        {
          kind: "line",
          title: "Sharpe",
          data: cost.data.points.map((point) => ({ time: point.multiplier, value: point.sharpe })),
          pane: 1,
        },
      ]
    : [];
  const mcSeries: ChartSeries[] = monteCarlo.data?.paths.length
    ? [
        ...monteCarlo.data.paths.slice(0, 12).map((path, index): ChartSeries => ({
          kind: "line",
          title: index === 0 ? "路径" : undefined,
          data: path.map((value, step) => ({ time: step, value: value * 100 })),
          lineWidth: 1,
        })),
        {
          kind: "line",
          title: "中位路径",
          data: (() => {
            const rows = monteCarlo.data?.paths ?? [];
            if (!rows.length) return [];
            const length = Math.min(...rows.map((row) => row.length));
            return Array.from({ length }, (_, index) => {
              const values = rows.map((row) => row[index]).sort((a, b) => a - b);
              return { time: index, value: values[Math.floor(values.length / 2)] * 100 };
            });
          })(),
          lineWidth: 2,
        },
      ]
    : [];

  return (
    <div className="grid grid-2">
      <Panel
        title={<><ShieldCheck size={16} aria-hidden="true" /> 实验与过拟合</>}
        subtitle="选择实验，运行 Deflated Sharpe、成本敏感性、Monte Carlo 与容量估算"
        actions={<span className="caption2 text-3">{busy ? "计算中…" : "仅研究口径 · 不构成投资建议"}</span>}
      >
        {error ? <Callout tone="danger" title="无法运行">{error}</Callout> : null}
        <div className="stack stack-tight">
          <Field label="实验" htmlFor="robust-run">
            <Select
              id="robust-run"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
              options={experimentOptions}
              placeholder={experiments.length ? undefined : "还没有实验"}
            />
          </Field>
          <div className="form-grid">
            <Field label="试验次数" hint="Deflated Sharpe 的试验数">
              <Input value={nTrials} onChange={(event) => setNTrials(event.target.value)} inputMode="numeric" />
            </Field>
            <Field label="成本倍数" hint="逗号分隔，如 0, 0.5, 1, 2, 3">
              <Input value={multipliers} onChange={(event) => setMultipliers(event.target.value)} />
            </Field>
            <Field label="MC 路径数">
              <Input value={nPaths} onChange={(event) => setNPaths(event.target.value)} inputMode="numeric" />
            </Field>
            <Field label="MC 期限（交易日）">
              <Input value={horizon} onChange={(event) => setHorizon(event.target.value)} inputMode="numeric" />
            </Field>
          </div>
          <Field label="容量参与率" hint="占日均成交额比例（0–1），用于容量估算" className="field-inline">
            <Input value={participation} onChange={(event) => setParticipation(event.target.value)} inputMode="decimal" style={{ width: 120 }} />
          </Field>
          <div className="row">
            <Button variant="primary" icon={Play} disabled={busy || !runId} loading={overfitting.isPending} onClick={runOverfitting}>Deflated Sharpe</Button>
            <Button variant="secondary" disabled={busy || !runId} loading={cost.isPending} onClick={runCost}>成本敏感性</Button>
            <Button variant="secondary" disabled={busy || !runId} loading={monteCarlo.isPending} onClick={runMonteCarlo}>Monte Carlo</Button>
            <Button variant="secondary" icon={Gauge} disabled={busy || !runId} loading={capacity.isPending} onClick={runCapacity}>容量</Button>
          </div>

          {overResult ? (
            <div className="stack stack-tight">
              <div className="grid grid-4">
                <StatTile label="Sharpe" value={overResult.sharpe.toFixed(2)} />
                <StatTile
                  label="Deflated Sharpe"
                  value={overResult.deflated_sharpe.toFixed(3)}
                  tone={overResult.deflated_sharpe >= 0.95 ? "ok" : "danger"}
                  hint="DSR ≥ 0.95 视为稳健"
                />
                <StatTile
                  size="sm"
                  label="判定"
                  value={verdictLabel(overResult.verdict)}
                  tone={overResult.verdict === "robust" ? "ok" : overResult.verdict === "likely_overfit" ? "danger" : "warn"}
                  hint={overResult.verdict}
                />
                <StatTile label="期望最大 Sharpe" value={overResult.expected_max_sharpe.toFixed(2)} />
              </div>
              <p className="caption text-3">观测 {overResult.observations} 日 · 偏度 {overResult.skew.toFixed(2)} · 峰度 {overResult.kurtosis.toFixed(2)}；Deflated Sharpe 对多试验做了惩罚，越高越可信。</p>
            </div>
          ) : null}

          {monteCarlo.data ? (
            <div className="grid grid-4">
              <StatTile label="终值 P05" value={pct(monteCarlo.data.terminal_return.p05)} tone="down" />
              <StatTile label="终值 P50" value={pct(monteCarlo.data.terminal_return.p50)} />
              <StatTile label="终值 P95" value={pct(monteCarlo.data.terminal_return.p95)} tone="up" />
              <StatTile label="最大回撤 P50" value={pct(monteCarlo.data.max_drawdown.p50)} tone="down" />
            </div>
          ) : null}

          {capacity.data ? (
            <Callout tone="info" icon={Gauge} title={`容量估计：约 ${money(capacity.data.capacity_cny)}`}>
              参与率 {pct(capacity.data.participation)} · 日均换手 {pct(capacity.data.avg_turnover)} · 限制证券 {capacity.data.limiting_sec}。{capacity.data.notes}
            </Callout>
          ) : null}
        </div>
      </Panel>

      <Panel
        title="PBO（CSCV）"
        subtitle="至少选择 2 个实验（最好来自参数扫描），估计回测过拟合概率"
        actions={<span className="caption2 text-3">已选 {pboIds.length}</span>}
      >
        <div className="stack stack-tight">
          <div className="pbo-list" role="group" aria-label="选择实验">
            {experiments.slice(0, 20).map((item) => (
              <label key={item.run_id} className="check-row">
                <input type="checkbox" checked={pboIds.includes(item.run_id)} onChange={() => togglePbo(item.run_id)} />
                <span className="truncate">{item.strategy_name || item.template} · {item.run_id.slice(-8)}</span>
              </label>
            ))}
            {experiments.length === 0 ? <span className="caption text-3">还没有实验，先跑一次回测。</span> : null}
          </div>
          <div className="row">
            <Field label="切分数" className="field-inline">
              <Input value={nSplits} onChange={(event) => setNSplits(event.target.value)} inputMode="numeric" style={{ width: 110 }} />
            </Field>
            <Button variant="primary" icon={Play} disabled={busy || pboIds.length < 2} loading={pbo.isPending} onClick={runPbo}>运行 PBO</Button>
          </div>
          {pbo.data ? (
            <>
              <div className="grid grid-3">
                <StatTile label="PBO" value={pct(pbo.data.pbo)} tone={pbo.data.pbo <= 0.5 ? "ok" : "danger"} hint="越低越好" />
                <StatTile label="组合数" value={String(pbo.data.combinations)} />
                <StatTile label="OOS 中位排名" value={pbo.data.median_oos_rank.toFixed(1)} />
              </div>
              <p className="caption text-3">PBO 越低越好；CSCV 为近似，样本区间重叠时会高估稳定性。</p>
            </>
          ) : null}
          {costSeries.length ? (
            <div className="stack stack-tight">
              <div className="split">
                <strong className="headline">成本敏感性</strong>
                {cost.data?.breakeven_multiplier != null ? <span className="badge badge-info">盈亏平衡 {cost.data.breakeven_multiplier.toFixed(2)}×</span> : null}
              </div>
              <Chart series={costSeries} height={240} />
            </div>
          ) : null}
          {mcSeries.length ? (
            <div className="stack stack-tight">
              <div className="split">
                <strong className="headline">Monte Carlo 路径</strong>
                <span className="caption2 text-3">{monteCarlo.data?.n_paths} 条 · {monteCarlo.data?.horizon} 日</span>
              </div>
              <Chart series={mcSeries} height={240} />
            </div>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}
