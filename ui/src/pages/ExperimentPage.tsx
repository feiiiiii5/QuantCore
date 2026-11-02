import { useEffect, useMemo, useState } from "react";
import { Download, FlaskConical, GitCompare, LayoutGrid, List, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { downloadWithAuth } from "../api/client";
import { useCompareExperiments, useDeleteExperiment, useExperimentResult, useExperiments, useReplayExperiment } from "../api/queries";
import type { Experiment } from "../api/types";
import {
  Badge, Button, Chart, ChartCard, DataTable, EmptyState, Field, Input, PageHeader, Panel, Segmented, Sheet,
  Skeleton, StatTile, Textarea, Toolbar, type ChartSeries,
} from "../components";
import { num, pct } from "../lib/format";
import { chartToken } from "../lib/tokens";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const COMPARE_COLORS = ["--accent", "--warn", "--ok", "--up"];

export default function ExperimentPage() {
  const [searchParams] = useSearchParams();
  const experiments = useExperiments();
  const compare = useCompareExperiments();
  const replay = useReplayExperiment();
  const remove = useDeleteExperiment();
  const [view, setView] = useState("cards");
  const [selected, setSelected] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
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
  const equitySeries = useMemo<ChartSeries[]>(() => {
    if (compare.data?.equity.length) {
      return compare.data.equity.map((item, index) => ({
        kind: "line" as const,
        title: item.run_id.slice(-10),
        color: chartToken(COMPARE_COLORS[index % COMPARE_COLORS.length], "#0071e3"),
        data: item.dates.map((date, point) => ({ time: date, value: item.equity[point] })),
      }));
    }
    if (resultQuery.data) {
      return [{ kind: "area" as const, title: "净值", data: resultQuery.data.dates.map((date, index) => ({ time: date, value: resultQuery.data!.equity[index] })) }];
    }
    return [];
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
    try { await compare.mutateAsync(compareIds); setCompareOpen(true); } catch (reason) { setError(reason instanceof Error ? reason.message : "对比失败"); }
  };
  const updateTags = (value: string) => setTags(selected, value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean).slice(0, 8));

  const cardMetrics = (item: Experiment) => (
    <div className="exp-metrics">
      <div className="exp-metric"><span>总收益</span><strong className={(item.metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(item.metrics?.total_return)}</strong></div>
      <div className="exp-metric"><span>Sharpe</span><strong>{num(item.metrics?.sharpe)}</strong></div>
      <div className="exp-metric"><span>最大回撤</span><strong className="down">{pct(item.metrics?.max_drawdown)}</strong></div>
      <div className="exp-metric"><span>交易</span><strong>{num(item.metrics?.trade_count, 0)}</strong></div>
    </div>
  );

  const columns = [
    { key: "run", header: "实验", width: "30%", render: (item: Experiment) => <div style={{ minWidth: 0 }}><div className="truncate">{item.strategy_name || item.template || item.run_id}</div><span className="mono page-note-sm">{item.run_id}</span></div> },
    { key: "date", header: "创建", width: 110, render: (item: Experiment) => item.created_at.slice(0, 10) },
    { key: "ret", header: "总收益", align: "right" as const, render: (item: Experiment) => <span className={(item.metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(item.metrics?.total_return)}</span> },
    { key: "sharpe", header: "Sharpe", align: "right" as const, render: (item: Experiment) => num(item.metrics?.sharpe) },
    { key: "dd", header: "最大回撤", align: "right" as const, render: (item: Experiment) => pct(item.metrics?.max_drawdown) },
    { key: "trades", header: "交易", align: "right" as const, render: (item: Experiment) => num(item.metrics?.trade_count, 0) },
    { key: "type", header: "类型", width: 100, render: (item: Experiment) => <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge> },
    { key: "compare", header: "对比", width: 80, render: (item: Experiment) => <input className="checkbox" type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} onClick={(event) => event.stopPropagation()} onChange={() => toggleCompare(item.run_id)} /> },
  ];

  return (
    <div className="page">
      <PageHeader
        title="实验"
        subtitle="每次回测自动存为实验；在本机比较、复现、导出与删除。"
        actions={(
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={() => void experiments.refetch()} disabled={experiments.isFetching}>刷新</Button>
            <Button variant="primary" icon={FlaskConical} href="/backtest">去跑回测</Button>
          </>
        )}
      />

      {experiments.isLoading ? <Skeleton rows={5} /> : experiments.error ? (
        <EmptyState title="实验列表加载失败" hint={experiments.error.message} action={<Button variant="secondary" onClick={() => void experiments.refetch()}>重试</Button>} />
      ) : !items.length ? (
        <Panel><EmptyState title="还没有实验" hint="先跑第一个回测，或使用一键示例生成 SYNTHETIC 示例；每次回测都会自动保存为可复现实验。" action={<Button variant="primary" icon={FlaskConical} href="/backtest">去跑第一个回测</Button>} /></Panel>
      ) : (
        <>
          <Toolbar actions={(
            <>
              <Button variant="secondary" icon={GitCompare} loading={compare.isPending} disabled={compareIds.length < 2} onClick={() => void onCompare()}>{compare.isPending ? "对比中…" : `对比所选 (${compareIds.length}/4)`}</Button>
              <Button variant="ghost" onClick={() => setCompareIds([])} disabled={!compareIds.length}>清空选择</Button>
            </>
          )}>
            <Segmented ariaLabel="实验视图" value={view} onChange={setView} items={[{ value: "cards", label: "卡片", icon: LayoutGrid }, { value: "table", label: "表格", icon: List }]} />
            <span className="page-note-sm">运行记录 {items.length}</span>
          </Toolbar>
          {error ? <p className="error-text" role="alert">{error}</p> : null}
          {view === "cards" ? (
            <div className="exp-grid">
              {items.map((item) => (
                <div
                  key={item.run_id}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selected === item.run_id}
                  className={`exp-card ${selected === item.run_id ? "selected" : ""}`}
                  onClick={() => setSelected(item.run_id)}
                  onKeyDown={(event) => { if (event.key === "Enter") setSelected(item.run_id); }}
                >
                  <div className="exp-card-head">
                    <div style={{ minWidth: 0 }}>
                      <div className="exp-card-name" title={item.strategy_name || item.run_id}>{item.strategy_name || item.template || item.run_id}</div>
                      <div className="exp-card-sub">{item.created_at.slice(0, 10)} · {item.synthetic ? "SYNTHETIC" : "本地数据"} · {item.run_id.slice(-10)}</div>
                    </div>
                    <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge>
                  </div>
                  {cardMetrics(item)}
                  <div className="exp-card-foot">
                    <Badge tone="neutral">{item.template || "—"}</Badge>
                    <label className="check-row" onClick={(event) => event.stopPropagation()}>
                      <input className="checkbox" type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} onChange={() => toggleCompare(item.run_id)} />
                      加入对比
                    </label>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Panel flush><DataTable columns={columns} rows={items} rowKey={(item) => item.run_id} onRowClick={(item) => setSelected(item.run_id)} selectedKey={selected} ariaLabel="实验表格" maxHeight={520} /></Panel>
          )}

          {selected ? (
            <Panel
              title={<span className="truncate" title={current?.strategy_name || selected}>{current?.strategy_name || selected}</span>}
              subtitle={<span className="mono">{selected}</span>}
              actions={(
                <>
                  <Button variant="secondary" icon={RotateCcw} loading={replay.isPending} onClick={() => void onReplay()}>复现</Button>
                  <Button variant="secondary" icon={Download} onClick={() => void downloadWithAuth(`/api/experiments/${selected}/report`, `${selected}.html`)}>报告</Button>
                  <Button variant="secondary" icon={Download} onClick={() => void downloadWithAuth(`/api/experiments/${selected}/export`, `${selected}.zip`)}>导出</Button>
                  <Button variant="danger" icon={Trash2} loading={remove.isPending} onClick={() => void onDelete()}>删除</Button>
                </>
              )}
            >
              <div className="stack">
                {current ? (
                  <div className="row">
                    <Badge tone="neutral">模板 {current.template || "—"}</Badge>
                    <Badge tone="neutral">快照 {current.snapshot_id?.slice(0, 16) || "—"}</Badge>
                    <Badge tone={current.synthetic ? "info" : "neutral"}>{current.synthetic ? "SYNTHETIC" : "本地数据"}</Badge>
                    <Badge tone="neutral">状态 {current.status}</Badge>
                    <span className="page-note-sm">创建 {current.created_at}</span>
                  </div>
                ) : null}
                <div className="grid grid-2">
                  <Field label="标签（逗号分隔，本地）" hint="例如：动量, 低波动；只存本机 localStorage" htmlFor="exp-tags">
                    <Input id="exp-tags" value={selectedTags.join(", ")} onChange={(event) => updateTags(event.target.value)} placeholder="例如：动量, 低波动" aria-label="标签（逗号分隔，本地）" />
                  </Field>
                  <Field label="笔记（本地）" hint="记录假设/风险/下一步；只存本机 localStorage" htmlFor="exp-notes">
                    <Textarea id="exp-notes" rows={2} value={note} onChange={(event) => setNote(selected, event.target.value)} placeholder="记录假设/风险/下一步" aria-label="笔记（本地）" />
                  </Field>
                </div>
                {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error-text"}>{replayMessage}</p> : null}
                {resultQuery.isLoading ? <Skeleton rows={4} /> : resultQuery.error ? (
                  <EmptyState title="结果加载失败" hint={resultQuery.error.message} action={<Button variant="secondary" onClick={() => void resultQuery.refetch()}>重试</Button>} />
                ) : equitySeries.length ? (
                  <ChartCard title={compare.data ? "对比净值" : "净值曲线"} subtitle={compare.data ? `${compare.data.ids.length} 个实验` : "实验保存的权益序列"} height={340}>
                    <Chart series={equitySeries} height={340} ariaLabel="实验净值曲线" valueFormatter={(value) => value.toFixed(0)} />
                  </ChartCard>
                ) : <EmptyState title="该实验没有可绘制的净值" hint="检查实验目录是否完整。" />}
                {resultQuery.data ? (
                  <div className="metric-grid">
                    <StatTile label="总收益" value={pct(resultQuery.data.metrics.total_return)} tone={resultQuery.data.metrics.total_return >= 0 ? "up" : "down"} hint={`年化 ${pct(resultQuery.data.metrics.annualized_return)}`} />
                    <StatTile label="Sharpe" value={num(resultQuery.data.metrics.sharpe)} hint={`胜率 ${pct(resultQuery.data.metrics.win_rate)}`} />
                    <StatTile label="最大回撤" value={pct(resultQuery.data.metrics.max_drawdown)} tone="down" hint={`换手 ${pct(resultQuery.data.metrics.turnover)}`} />
                    <StatTile label="交易" value={num(resultQuery.data.metrics.trade_count, 0)} hint={`引擎 ${resultQuery.data.engine_backend}`} />
                  </div>
                ) : null}
              </div>
            </Panel>
          ) : null}
        </>
      )}

      <Sheet open={compareOpen} onOpenChange={setCompareOpen} side="right" title="实验对比" description={compare.data ? `${compare.data.ids.length} 个实验 · 同一指标口径` : "选择 2–4 个实验进行对比"}>
        {compare.data ? (
          <div className="stack">
            <div className="table-wrap">
              <table>
                <thead><tr><th>实验</th><th className="num">总收益</th><th className="num">Sharpe</th><th className="num">最大回撤</th></tr></thead>
                <tbody>
                  {compare.data.ids.map((id) => {
                    const metrics = compare.data?.metrics[id];
                    return <tr key={id}><td className="mono truncate" title={id}>{id}</td><td className="num">{pct(metrics?.total_return)}</td><td className="num">{num(metrics?.sharpe)}</td><td className="num">{pct(metrics?.max_drawdown)}</td></tr>;
                  })}
                </tbody>
              </table>
            </div>
            {equitySeries.length ? <Chart series={equitySeries} height={280} ariaLabel="对比净值曲线" /> : null}
          </div>
        ) : <p className="page-note-sm">勾选实验卡片上的「加入对比」，再点「对比所选」。</p>}
      </Sheet>

      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
