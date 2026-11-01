import { useEffect, useMemo, useState } from "react";
import { Download, GitCompare, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { downloadWithAuth } from "../api/client";
import { useCompareExperiments, useDeleteExperiment, useExperimentResult, useExperiments, useReplayExperiment } from "../api/queries";
import type { Experiment } from "../api/types";
import Chart from "../components/Chart";
import StatePanel from "../components/StatePanel";
import { dateInt, num, pct } from "../lib/format";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";

export default function ExperimentPage() {
  const [searchParams] = useSearchParams();
  const experiments = useExperiments();
  const compare = useCompareExperiments();
  const replay = useReplayExperiment();
  const remove = useDeleteExperiment();
  const [selected, setSelected] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [replayMessage, setReplayMessage] = useState("");
  const [error, setError] = useState("");
  const notes = useWorkspace((state) => state.notes);
  const tags = useWorkspace((state) => state.tags);
  const setNote = useWorkspace((state) => state.setNote);
  const setTags = useWorkspace((state) => state.setTags);
  const resultQuery = useExperimentResult(selected || null);
  const items = experiments.data ?? [];

  useEffect(() => {
    if (!items.length) return;
    const requested = searchParams.get("run");
    const valid = requested && items.some((item) => item.run_id === requested);
    if (valid) setSelected(requested);
    else if (!selected || !items.some((item) => item.run_id === selected)) setSelected(items[0].run_id);
  }, [items, searchParams, selected]);

  const current = items.find((item) => item.run_id === selected) ?? null;
  const selectedTags = tags[selected] ?? [];
  const note = notes[selected] ?? "";
  const toggleCompare = (id: string) => setCompareIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : ids.length >= 6 ? ids : [...ids, id]);
  const equityOption = useMemo<EChartsOption | null>(() => {
    if (compare.data?.equity.length) {
      return {
        animation: false, tooltip: { trigger: "axis" }, legend: { top: 0, textStyle: { fontSize: 10 } },
        xAxis: { type: "category", data: compare.data.equity[0].dates.map(dateInt), axisLabel: { fontSize: 10 } }, yAxis: { type: "value", scale: true },
        series: compare.data.equity.map((item) => ({ type: "line", name: item.run_id.slice(-12), data: item.equity, showSymbol: false, lineStyle: { width: 1.2 } })),
      };
    }
    if (resultQuery.data) {
      return {
        animation: false, tooltip: { trigger: "axis" }, grid: { left: 68, right: 20, top: 24, bottom: 40 },
        xAxis: { type: "category", data: resultQuery.data.dates.map(dateInt), axisLabel: { fontSize: 10 } }, yAxis: { type: "value", scale: true },
        series: [{ type: "line", name: "净值", data: resultQuery.data.equity, showSymbol: false, lineStyle: { width: 1.6, color: "#2563eb" } }],
      };
    }
    return null;
  }, [compare.data, resultQuery.data]);

  const onReplay = async () => {
    setReplayMessage("复现中…"); setError("");
    try {
      const outcome = await replay.mutateAsync(selected);
      setReplayMessage(outcome.matched ? "复现一致：净值/交易/指标全部匹配" : `发现差异：${JSON.stringify(outcome.differences ?? outcome.diffs ?? outcome)}`);
    } catch (reason) { setReplayMessage(reason instanceof Error ? reason.message : "复现失败"); }
  };
  const onDelete = async () => {
    if (!selected || !window.confirm(`删除实验 ${selected}？该操作只删除本地实验目录。`)) return;
    setError("");
    try {
      await remove.mutateAsync(selected);
      setSelected(""); setCompareIds((ids) => ids.filter((id) => id !== selected));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败"); }
  };
  const onCompare = async () => {
    setError("");
    if (compareIds.length < 2) { setError("至少选择两个实验进行对比"); return; }
    try { await compare.mutateAsync(compareIds); } catch (reason) { setError(reason instanceof Error ? reason.message : "对比失败"); }
  };
  const updateTags = (value: string) => setTags(selected, value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean).slice(0, 8));

  return (
    <>
      <div className="page-head"><div><h1>实验</h1><p>版本 · 参数 · 快照 · 本地标签/笔记 · 复现 · 对比 · 导出</p></div><button className="btn" onClick={() => void experiments.refetch()} disabled={experiments.isFetching}><RefreshCw size={15} /> 刷新</button></div>
      {experiments.isLoading ? <StatePanel loading /> : experiments.error ? <StatePanel error={experiments.error.message} onRetry={() => void experiments.refetch()} /> : !items.length ? (
        <div className="empty card"><strong>还没有实验</strong><span>先运行一次回测，或使用一键示例生成 SYNTHETIC 示例。</span><Link className="btn primary" to="/backtest">去回测</Link></div>
      ) : (
        <div className="grid experiments-layout">
          <div className="card experiment-list">
            <h3>运行记录 <span className="muted small">{items.length}</span></h3>
            {items.map((item: Experiment) => (
              <div key={item.run_id} className={`experiment-item ${selected === item.run_id ? "active" : ""}`} onClick={() => setSelected(item.run_id)} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setSelected(item.run_id); }}>
                <div><strong className="truncate" title={item.strategy_name || item.run_id}>{item.strategy_name || item.template || item.run_id}</strong><small>{item.run_id}</small><small>{item.created_at.slice(0, 10)} · {item.synthetic ? "SYNTHETIC" : "本地"}</small></div>
                <div className="experiment-meta"><span className={(item.metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(item.metrics?.total_return)}</span><input type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} onChange={() => toggleCompare(item.run_id)} onClick={(event) => event.stopPropagation()} /></div>
              </div>
            ))}
            <button className="btn" style={{ marginTop: 8 }} onClick={() => void onCompare()} disabled={compare.isPending}><GitCompare size={15} /> {compare.isPending ? "对比中…" : `对比所选 (${compareIds.length})`}</button>
          </div>
          <div className="card result-card">
            {!selected ? <StatePanel empty emptyHint="选择一个实验" /> : (
              <>
                <div className="card-head"><h3 className="truncate" title={current?.strategy_name || selected}>{current?.strategy_name || selected}</h3><div className="button-row">
                  <button className="btn" onClick={() => void onReplay()} disabled={replay.isPending}><RotateCcw size={15} /> 复现</button>
                  <button className="btn" onClick={() => void downloadWithAuth(`/api/experiments/${selected}/report`, `${selected}.html`)}><Download size={15} /> 报告</button>
                  <button className="btn" onClick={() => void downloadWithAuth(`/api/experiments/${selected}/export`, `${selected}.zip`)}><Download size={15} /> 导出</button>
                  <button className="btn danger" onClick={() => void onDelete()} disabled={remove.isPending}><Trash2 size={15} /> 删除</button>
                </div></div>
                {current ? <div className="experiment-facts"><span>模板 <strong>{current.template || "—"}</strong></span><span>快照 <strong className="truncate">{current.snapshot_id || "—"}</strong></span><span>创建 <strong>{current.created_at}</strong></span><span>状态 <strong>{current.status}</strong></span></div> : null}
                <div className="form-grid two">
                  <label>标签（逗号分隔，本地）<input value={selectedTags.join(", ")} onChange={(event) => updateTags(event.target.value)} placeholder="例如：动量, 低波动" /></label>
                  <label>笔记（本地）<textarea rows={2} value={note} onChange={(event) => setNote(selected, event.target.value)} placeholder="记录假设/风险/下一步；只存本机 localStorage" /></label>
                </div>
                {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error"}>{replayMessage}</p> : null}
                {error ? <p className="error">{error}</p> : null}
                {resultQuery.isLoading ? <StatePanel loading /> : resultQuery.error ? <StatePanel error={resultQuery.error.message} onRetry={() => void resultQuery.refetch()} /> : equityOption ? <Chart option={equityOption} height={330} /> : <StatePanel empty emptyHint="该实验没有可绘制的净值。" />}
                {resultQuery.data ? <div className="metric-inline"><span>总收益 <strong>{pct(resultQuery.data.metrics.total_return)}</strong></span><span>Sharpe <strong>{num(resultQuery.data.metrics.sharpe)}</strong></span><span>最大回撤 <strong>{pct(resultQuery.data.metrics.max_drawdown)}</strong></span><span>交易 <strong>{resultQuery.data.trades.length}</strong></span><span>引擎 <strong>{resultQuery.data.engine_backend}</strong></span></div> : null}
                {compare.data ? <div className="card" style={{ marginTop: 12 }}><h3>对比指标</h3><div className="table-wrap"><table><thead><tr><th>实验</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th></tr></thead><tbody>{compare.data.ids.map((id) => { const metrics = compare.data?.metrics[id]; return <tr key={id}><td className="mono truncate" title={id}>{id}</td><td className="num">{pct(metrics?.total_return)}</td><td className="num">{num(metrics?.sharpe)}</td><td className="num">{pct(metrics?.max_drawdown)}</td></tr>; })}</tbody></table></div></div> : null}
              </>
            )}
          </div>
        </div>
      )}
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
