import { useEffect, useMemo, useState } from "react";
import { Download, FlaskConical, GitCompare, LayoutGrid, List, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { downloadWithAuth } from "../api/client";
import { useCompareExperiments, useDeleteExperiment, useExperimentResult, useExperiments, useReplayExperiment } from "../api/queries";
import type { Experiment } from "../api/types";
import { Badge, Chart, ChartCard, DataTable, EmptyState, Panel, Segmented, Skeleton, StatTile, Toolbar } from "../components";
import { dateInt, num, pct } from "../lib/format";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

export default function ExperimentPage() {
  const [searchParams] = useSearchParams();
  const experiments = useExperiments();
  const compare = useCompareExperiments();
  const replay = useReplayExperiment();
  const remove = useDeleteExperiment();
  const [view, setView] = useState("cards");
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
  const toggleCompare = (id: string) => setCompareIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : ids.length >= 4 ? ids : [...ids, id]);
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
        series: [{ type: "line", name: "净值", data: resultQuery.data.equity, showSymbol: false, lineStyle: { width: 1.6, color: "var(--primary)" } }],
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

  const renderExperiment = (item: Experiment, compact = false) => {
    const metrics = item.metrics;
    return (
      <>
        <div className="exp-card-top">
          <div style={{ minWidth: 0 }}><strong title={item.strategy_name || item.run_id}>{item.strategy_name || item.template || item.run_id}</strong><small>{item.created_at.slice(0, 10)} · {item.synthetic ? "SYNTHETIC" : "本地数据"} · {item.run_id.slice(-10)}</small></div>
          <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge>
        </div>
        {compact ? <span className="mono small truncate">{item.run_id}</span> : (
          <div className="exp-metrics">
            <div><span>总收益</span><strong className={(metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(metrics?.total_return)}</strong></div>
            <div><span>Sharpe</span><strong>{num(metrics?.sharpe)}</strong></div>
            <div><span>最大回撤</span><strong className="down">{pct(metrics?.max_drawdown)}</strong></div>
            <div><span>交易</span><strong>{num(metrics?.trade_count, 0)}</strong></div>
          </div>
        )}
        <div className="exp-card-foot">
          <Badge tone="neutral">{item.template || "—"}</Badge>
          <label className="check-row" onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} onChange={() => toggleCompare(item.run_id)} /> 加入对比</label>
        </div>
      </>
    );
  };

  const columns = [
    { key: "run", header: "实验", width: "30%", render: (item: Experiment) => <div style={{ minWidth: 0 }}><div className="truncate">{item.strategy_name || item.template || item.run_id}</div><span className="mono small muted">{item.run_id}</span></div> },
    { key: "date", header: "创建", width: 110, render: (item: Experiment) => item.created_at.slice(0, 10) },
    { key: "ret", header: "总收益", align: "right" as const, render: (item: Experiment) => <span className={(item.metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(item.metrics?.total_return)}</span> },
    { key: "sharpe", header: "Sharpe", align: "right" as const, render: (item: Experiment) => num(item.metrics?.sharpe) },
    { key: "dd", header: "最大回撤", align: "right" as const, render: (item: Experiment) => pct(item.metrics?.max_drawdown) },
    { key: "trades", header: "交易", align: "right" as const, render: (item: Experiment) => num(item.metrics?.trade_count, 0) },
    { key: "type", header: "类型", width: 100, render: (item: Experiment) => <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge> },
    { key: "compare", header: "对比", width: 80, render: (item: Experiment) => <input type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} onClick={(event) => event.stopPropagation()} onChange={() => toggleCompare(item.run_id)} /> },
  ];

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>实验</h1><p className="page-lead">每次回测自动存为实验；在本机比较、复现、导出与删除。</p></div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => void experiments.refetch()} disabled={experiments.isFetching}><RefreshCw size={15} /> 刷新</button>
          <Link className="btn primary" to="/backtest"><FlaskConical size={15} /> 去跑回测</Link>
        </div>
      </header>

      {experiments.isLoading ? <Skeleton rows={5} /> : experiments.error ? <EmptyState title="实验列表加载失败" hint={experiments.error.message} action={<button className="btn" onClick={() => void experiments.refetch()}>重试</button>} /> : !items.length ? (
        <Panel><EmptyState title="还没有实验" hint="先跑第一个回测，或使用一键示例生成 SYNTHETIC 示例；每次回测都会自动保存为可复现实验。" action={<Link className="btn primary" to="/backtest"><FlaskConical size={15} /> 去跑第一个回测</Link>} /></Panel>
      ) : (
        <>
          <Toolbar actions={<><button className="btn" onClick={() => void onCompare()} disabled={compare.isPending || compareIds.length < 2}><GitCompare size={15} /> {compare.isPending ? "对比中…" : `对比所选 (${compareIds.length}/4)`}</button><button className="btn ghost" onClick={() => setCompareIds([])} disabled={!compareIds.length}>清空选择</button></>}>
            <Segmented ariaLabel="实验视图" value={view} onChange={setView} options={[{ value: "cards", label: "卡片", icon: LayoutGrid }, { value: "table", label: "表格", icon: List }]} />
            <span className="muted small">运行记录 {items.length}</span>
          </Toolbar>
          {error ? <p className="error" role="alert">{error}</p> : null}
          {view === "cards" ? (
            <div className="exp-grid">
              {items.map((item) => (
                <div key={item.run_id} role="button" tabIndex={0} className={`exp-card ${selected === item.run_id ? "active" : ""}`} onClick={() => setSelected(item.run_id)} onKeyDown={(event) => { if (event.key === "Enter") setSelected(item.run_id); }}>
                  {renderExperiment(item)}
                </div>
              ))}
            </div>
          ) : (
            <Panel dense><DataTable columns={columns} rows={items} rowKey={(item) => item.run_id} onRowClick={(item) => setSelected(item.run_id)} selectedKey={selected} ariaLabel="实验表格" maxHeight={520} /></Panel>
          )}

          {selected ? (
            <Panel
              title={<span className="truncate" title={current?.strategy_name || selected}>{current?.strategy_name || selected}</span>}
              subtitle={<span className="mono small">{selected}</span>}
              actions={<div className="row">
                <button className="btn" onClick={() => void onReplay()} disabled={replay.isPending}><RotateCcw size={15} /> 复现</button>
                <button className="btn" onClick={() => void downloadWithAuth(`/api/experiments/${selected}/report`, `${selected}.html`)}><Download size={15} /> 报告</button>
                <button className="btn" onClick={() => void downloadWithAuth(`/api/experiments/${selected}/export`, `${selected}.zip`)}><Download size={15} /> 导出</button>
                <button className="btn danger" onClick={() => void onDelete()} disabled={remove.isPending}><Trash2 size={15} /> 删除</button>
              </div>}
            >
              {current ? <div className="experiment-facts"><span>模板 <strong>{current.template || "—"}</strong></span><span>快照 <strong className="truncate">{current.snapshot_id || "—"}</strong></span><span>创建 <strong>{current.created_at}</strong></span><span>状态 <strong>{current.status}</strong></span></div> : null}
              <div className="form-grid two">
                <label>标签（逗号分隔，本地）<input value={selectedTags.join(", ")} onChange={(event) => updateTags(event.target.value)} placeholder="例如：动量, 低波动" /></label>
                <label>笔记（本地）<textarea rows={2} value={note} onChange={(event) => setNote(selected, event.target.value)} placeholder="记录假设/风险/下一步；只存本机 localStorage" /></label>
              </div>
              {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error"}>{replayMessage}</p> : null}
              {resultQuery.isLoading ? <Skeleton rows={4} /> : resultQuery.error ? <EmptyState title="结果加载失败" hint={resultQuery.error.message} action={<button className="btn" onClick={() => void resultQuery.refetch()}>重试</button>} /> : equityOption ? <ChartCard title={compare.data ? "对比净值" : "净值曲线"} subtitle={compare.data ? `${compare.data.ids.length} 个实验` : "实验保存的权益序列"} height={330}><Chart option={equityOption} height={330} /></ChartCard> : <EmptyState title="该实验没有可绘制的净值" hint="检查实验目录是否完整。" />}
              {resultQuery.data ? (
                <div className="stat-grid">
                  <StatTile label="总收益" value={pct(resultQuery.data.metrics.total_return)} tone={resultQuery.data.metrics.total_return >= 0 ? "up" : "down"} hint={`年化 ${pct(resultQuery.data.metrics.annualized_return)}`} />
                  <StatTile label="Sharpe" value={num(resultQuery.data.metrics.sharpe)} hint={`胜率 ${pct(resultQuery.data.metrics.win_rate)}`} />
                  <StatTile label="最大回撤" value={pct(resultQuery.data.metrics.max_drawdown)} tone="down" hint={`换手 ${pct(resultQuery.data.metrics.turnover)}`} />
                  <StatTile label="交易" value={num(resultQuery.data.metrics.trade_count, 0)} hint={`引擎 ${resultQuery.data.engine_backend}`} />
                </div>
              ) : null}
              {compare.data ? (
                <Panel title="对比指标" subtitle={`${compare.data.ids.length} 个实验 · 同一指标口径`}>
                  <div className="table-wrap"><table><thead><tr><th>实验</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th></tr></thead><tbody>{compare.data.ids.map((id) => { const metrics = compare.data?.metrics[id]; return <tr key={id}><td className="mono truncate" title={id}>{id}</td><td className="num">{pct(metrics?.total_return)}</td><td className="num">{num(metrics?.sharpe)}</td><td className="num">{pct(metrics?.max_drawdown)}</td></tr>; })}</tbody></table></div>
                </Panel>
              ) : null}
            </Panel>
          ) : null}
        </>
      )}
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
