import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Download, FlaskConical, GitCompare, LayoutGrid, List, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { downloadWithAuth } from "../api/client";
import { useCompareExperiments, useDeleteExperiment, useExperimentDetail, useExperiments, useReplayExperiment } from "../api/queries";
import type { Experiment } from "../api/types";
import {
  Badge, Button, Callout, Chart, ChartCard, DataTable, EmptyState, Field, Input, PageHeader, Panel, Segmented, Sheet,
  Skeleton, StatTile, Textarea, Toolbar, type ChartSeries,
} from "../components";
import ExperimentComparison from "../components/ExperimentComparison";
import ExperimentProvenance from "../components/ExperimentProvenance";
import { num, pct } from "../lib/format";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";
import "../styles/experiments.css";

export default function ExperimentPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const experiments = useExperiments();
  const compare = useCompareExperiments();
  const replay = useReplayExperiment();
  const remove = useDeleteExperiment();
  const [view, setView] = useState("cards");
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [replayStatus, setReplayStatus] = useState<{ runId: string; message: string; matched: boolean | null } | null>(null);
  const [error, setError] = useState("");
  const notes = useWorkspace((state) => state.notes);
  const tags = useWorkspace((state) => state.tags);
  const setNote = useWorkspace((state) => state.setNote);
  const setTags = useWorkspace((state) => state.setTags);
  const items = experiments.data ?? [];
  const requested = searchParams.get("run");
  const selected = requested || items[0]?.run_id || "";
  const detailQuery = useExperimentDetail(selected || null);
  const result = detailQuery.data?.result;
  const current = items.find((item) => item.run_id === selected) ?? null;
  const selectedName = current?.strategy_name || detailQuery.data?.metadata.strategy_name || selected;
  const selectedTags = tags[selected] ?? [];
  const note = notes[selected] ?? "";

  useEffect(() => {
    if (experiments.data) setCompareIds((ids) => ids.filter((id) => experiments.data!.some((item) => item.run_id === id)));
  }, [experiments.data]);

  const selectRun = (runId: string) => {
    setSearchParams((params) => { params.set("run", runId); return params; }, { replace: true });
  };
  const toggleCompare = (id: string) => setCompareIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : ids.length >= 4 ? ids : [...ids, id]);
  const equitySeries = useMemo<ChartSeries[]>(() => result ? [{
    kind: "area", title: "账户权益（元）",
    data: result.dates.map((date, index) => ({ time: date, value: result.equity[index] })),
  }] : [], [result]);

  const onReplay = async () => {
    const runId = selected;
    setReplayStatus({ runId, message: "复现中…", matched: null }); setError("");
    try {
      const outcome = await replay.mutateAsync(runId);
      setReplayStatus({ runId, matched: Boolean(outcome.matched), message: outcome.matched ? "复现一致：净值、交易与指标全部匹配。" : `发现差异：${JSON.stringify(outcome.differences ?? outcome.diffs ?? outcome)}` });
    } catch (reason) {
      setReplayStatus({ runId, matched: false, message: reason instanceof Error ? reason.message : "复现失败" });
    }
  };
  const onDelete = async () => {
    const runId = selected;
    if (!runId || !window.confirm(`删除实验 ${runId}？该操作只删除本地实验目录。`)) return;
    setError("");
    try {
      await remove.mutateAsync(runId);
      setCompareIds((ids) => ids.filter((id) => id !== runId));
      setSearchParams((params) => { if (params.get("run") === runId) params.delete("run"); return params; }, { replace: true });
      if (compare.data?.ids.includes(runId)) { compare.reset(); setCompareOpen(false); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败"); }
  };
  const onCompare = async () => {
    if (compareIds.length < 2) return;
    setError(""); compare.reset(); setCompareOpen(true);
    try { await compare.mutateAsync([...compareIds]); } catch (reason) { setError(reason instanceof Error ? reason.message : "对比失败"); }
  };
  const onDownload = async (kind: "report" | "export") => {
    setError("");
    try { await downloadWithAuth(`/api/experiments/${encodeURIComponent(selected)}/${kind}`, `${selected}.${kind === "report" ? "html" : "zip"}`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "下载失败"); }
  };
  const updateTags = (value: string) => setTags(selected, value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean).slice(0, 8));
  const compareInput = (item: Experiment) => <input className="checkbox" type="checkbox" aria-label={`对比 ${item.run_id}`} checked={compareIds.includes(item.run_id)} disabled={!compareIds.includes(item.run_id) && compareIds.length >= 4} onClick={(event) => event.stopPropagation()} onChange={() => toggleCompare(item.run_id)} />;
  const cardMetrics = (item: Experiment) => (
    <div className="exp-metrics">
      <div className="exp-metric"><span>总收益</span><strong className={item.metrics?.total_return == null ? "" : item.metrics.total_return >= 0 ? "up" : "down"}>{pct(item.metrics?.total_return)}</strong></div>
      <div className="exp-metric"><span>Sharpe</span><strong>{num(item.metrics?.sharpe)}</strong></div>
      <div className="exp-metric"><span>最大回撤</span><strong className="down">{pct(item.metrics?.max_drawdown)}</strong></div>
      <div className="exp-metric"><span>交易</span><strong>{num(item.metrics?.trade_count, 0)}</strong></div>
    </div>
  );
  const columns = [
    { key: "run", header: "实验", width: "30%", render: (item: Experiment) => <div style={{ minWidth: 0 }}><div className="truncate">{item.strategy_name || item.template || item.run_id}</div><span className="mono page-note-sm">{item.run_id}</span></div> },
    { key: "date", header: "创建", width: 110, render: (item: Experiment) => item.created_at.slice(0, 10) },
    { key: "ret", header: "总收益", align: "right" as const, render: (item: Experiment) => pct(item.metrics?.total_return) },
    { key: "sharpe", header: "Sharpe", align: "right" as const, render: (item: Experiment) => num(item.metrics?.sharpe) },
    { key: "dd", header: "最大回撤", align: "right" as const, render: (item: Experiment) => pct(item.metrics?.max_drawdown) },
    { key: "type", header: "数据", width: 100, render: (item: Experiment) => <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge> },
    { key: "compare", header: "对比", width: 80, render: compareInput },
  ];

  return (
    <div className="page">
      <PageHeader
        title="实验"
        subtitle="把每次研究留下来。先核对数据与条件，再比较收益、回撤和参数。"
        actions={<><Button variant="secondary" icon={RefreshCw} onClick={() => void experiments.refetch()} disabled={experiments.isFetching}>刷新</Button><Button variant="primary" icon={FlaskConical} href="/backtest">去跑回测</Button></>}
      />
      {error ? <Callout tone="danger" title={error} /> : null}
      {experiments.isLoading ? <Skeleton rows={5} /> : experiments.error ? (
        <EmptyState title="实验列表加载失败" hint={experiments.error.message} action={<Button variant="secondary" onClick={() => void experiments.refetch()}>重试</Button>} />
      ) : !items.length && !requested ? (
        <Panel><EmptyState title="还没有实验" hint="先跑第一个回测，或使用一键示例生成 SYNTHETIC 示例；每次回测都会自动保存为可复现实验。" action={<Button variant="primary" icon={FlaskConical} href="/backtest">去跑第一个回测</Button>} /></Panel>
      ) : (
        <>
          {requested && !items.some((item) => item.run_id === requested) ? <Callout tone="info" title="按链接载入历史实验">列表展示最近 100 条记录；下方详情按指定实验载入。</Callout> : null}
          <Toolbar actions={<><Button variant="secondary" icon={GitCompare} loading={compare.isPending} disabled={compareIds.length < 2} onClick={() => void onCompare()}>{compare.isPending ? "对比中…" : `对比所选 (${compareIds.length}/4)`}</Button><Button variant="ghost" onClick={() => setCompareIds([])} disabled={!compareIds.length}>清空选择</Button></>}>
            <Segmented ariaLabel="实验视图" value={view} onChange={setView} items={[{ value: "cards", label: "卡片", icon: LayoutGrid }, { value: "table", label: "表格", icon: List }]} />
            <span className="page-note-sm">运行记录 {items.length} · 选择 2–4 个实验比较</span>
          </Toolbar>
          {view === "cards" ? (
            <div className="exp-grid">
              {items.map((item) => (
                <article key={item.run_id} className={`exp-card ${selected === item.run_id ? "selected" : ""}`}>
                  <button className="exp-card-select" type="button" aria-pressed={selected === item.run_id} onClick={() => selectRun(item.run_id)}>
                    <span className="exp-card-head">
                      <span className="exp-card-heading"><span className="exp-card-name" title={item.strategy_name || item.run_id}>{item.strategy_name || item.template || item.run_id}</span><span className="exp-card-sub">{item.created_at.slice(0, 10)} · {item.run_id.slice(-10)}</span></span>
                      <Badge tone={item.synthetic ? "info" : "neutral"}>{item.synthetic ? "SYNTHETIC" : "本地"}</Badge>
                    </span>
                    {cardMetrics(item)}
                  </button>
                  <div className="exp-card-foot"><Badge tone="neutral">{item.template || item.kind}</Badge><label className="check-row">{compareInput(item)}加入对比</label></div>
                </article>
              ))}
            </div>
          ) : <Panel flush><DataTable columns={columns} rows={items} rowKey={(item) => item.run_id} onRowClick={(item) => selectRun(item.run_id)} selectedKey={selected} ariaLabel="实验表格" maxHeight={520} /></Panel>}

          {selected ? (
            <Panel
              title={<span className="truncate" title={selectedName}>{selectedName}</span>}
              subtitle={<span className="mono">{selected}</span>}
              actions={<><Button variant="secondary" icon={RotateCcw} loading={replay.isPending} onClick={() => void onReplay()}>复现</Button><Button variant="secondary" icon={Download} onClick={() => void onDownload("report")}>报告</Button><Button variant="secondary" icon={Download} onClick={() => void onDownload("export")}>导出</Button><Button variant="danger" icon={Trash2} loading={remove.isPending} onClick={() => void onDelete()}>删除</Button></>}
            >
              <div className="stack">
                {current ? <div className="row"><Badge tone="neutral">模板 {current.template || "—"}</Badge><Badge tone={current.synthetic ? "info" : "neutral"}>{current.synthetic ? "SYNTHETIC" : "本地数据"}</Badge><Badge tone="neutral">状态 {current.status}</Badge><span className="page-note-sm">创建 {current.created_at}</span></div> : null}
                {detailQuery.isLoading ? <Skeleton rows={5} /> : detailQuery.error ? (
                  <EmptyState title="实验加载失败" hint={detailQuery.error.message} action={<Button variant="secondary" onClick={() => void detailQuery.refetch()}>重试</Button>} />
                ) : (
                  <>
                    {result ? <div className="metric-grid"><StatTile label="总收益" value={pct(result.metrics.total_return)} tone={result.metrics.total_return >= 0 ? "up" : "down"} hint={`年化 ${pct(result.metrics.annualized_return)}`} /><StatTile label="Sharpe" value={num(result.metrics.sharpe)} hint={`胜率 ${pct(result.metrics.win_rate)}`} /><StatTile label="最大回撤" value={pct(result.metrics.max_drawdown)} tone="down" hint={`换手 ${pct(result.metrics.turnover)}`} /><StatTile label="交易" value={num(result.metrics.trade_count, 0)} hint={`引擎 ${result.engine_backend}`} /></div> : null}
                    {equitySeries.length ? <ChartCard title="账户权益" subtitle="当前选中实验保存的权益，单位为元；对比实验时使用归一化净值。" height={320}><Chart series={equitySeries} height={320} ariaLabel="实验净值曲线" valueFormatter={(value) => num(value, 0)} /></ChartCard> : <EmptyState title="该实验没有可绘制的权益" hint="检查实验结果是否保存完整。" />}
                    {detailQuery.data ? <ExperimentProvenance metadata={detailQuery.data.metadata} result={result} /> : null}
                    <div className="row">
                      {detailQuery.data?.metadata.strategy?.template ? <Button variant="secondary" icon={FlaskConical} href={`/backtest?source=${encodeURIComponent(selected)}`}>沿用数据与参数</Button> : null}
                      <Button variant="ghost" iconRight={ArrowRight} href={`/research?run=${encodeURIComponent(selected)}`}>继续研究</Button>
                    </div>
                  </>
                )}
                {replayStatus?.runId === selected ? <p role="status" className={replayStatus.matched === true ? "success-text" : replayStatus.matched === false ? "error-text" : "page-note"}>{replayStatus.message}</p> : null}
                <div className="grid grid-2">
                  <Field label="标签（逗号分隔，本地）" hint="例如：动量, 低波动；只存本机 localStorage" htmlFor="exp-tags"><Input id="exp-tags" value={selectedTags.join(", ")} onChange={(event) => updateTags(event.target.value)} placeholder="例如：动量, 低波动" aria-label="标签（逗号分隔，本地）" /></Field>
                  <Field label="笔记（本地）" hint="记录假设、风险与下一步；只存本机 localStorage" htmlFor="exp-notes"><Textarea id="exp-notes" rows={2} value={note} onChange={(event) => setNote(selected, event.target.value)} placeholder="记录假设、风险与下一步" aria-label="笔记（本地）" /></Field>
                </div>
              </div>
            </Panel>
          ) : null}
        </>
      )}
      <Sheet open={compareOpen} onOpenChange={setCompareOpen} side="right" size="lg" className="exp-comparison-sheet" title="实验对比" description="核对研究条件，再比较净值、回撤与指标差值。">
        {compare.isPending ? <Skeleton rows={8} /> : compare.error ? <EmptyState title="对比加载失败" hint={compare.error.message} action={<Button variant="secondary" onClick={() => void onCompare()}>重试</Button>} /> : compare.data ? <ExperimentComparison result={compare.data} onOpenRun={(runId) => { selectRun(runId); setCompareOpen(false); }} /> : <EmptyState title="选择实验开始对比" hint="勾选 2–4 个实验，再点「对比所选」。" />}
      </Sheet>
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
