import { useMemo, useState } from "react";
import { Download, ListFilter, Play, Save } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { useRunScreener, useScreenerPresets } from "../api/queries";
import type { ScreenerRow } from "../api/types";
import { Badge, EmptyState, Panel, Skeleton, Tag, VirtualTable } from "../components";
import { compact, downloadText, num, signedPct, toCsv } from "../lib/format";
import { useBeginner } from "../store/ui";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const DEFAULT_EXPRESSION = "rank(ret(close,20)) > 0.8 and ma(close,5) > ma(close,20)";
interface SavedScreener { name: string; expression: string; board: string; excludeSt: boolean; minAmount: string; at: string }

export default function ScreenerPage() {
  const navigate = useNavigate();
  const beginner = useBeginner();
  const presets = useScreenerPresets();
  const runScreener = useRunScreener();
  const [preset, setPreset] = useState(() => useWorkspace.getState().screenerPreset);
  const [expression, setExpression] = useState(() => useWorkspace.getState().screenerExpression || DEFAULT_EXPRESSION);
  const [board, setBoard] = useState("");
  const [excludeSt, setExcludeSt] = useState(true);
  const [minAmount, setMinAmount] = useState("0");
  const [saved, setSaved] = useState<SavedScreener[]>(() => {
    try { return JSON.parse(localStorage.getItem("qc_screener_saved") || "[]") as SavedScreener[]; } catch { return []; }
  });
  const [savedName, setSavedName] = useState("");
  const [notice, setNotice] = useState("");
  const setDraft = useWorkspace((state) => state.setScreenerDraft);
  const result = runScreener.data;

  const applyPreset = (id: string) => {
    setPreset(id);
    const found = presets.data?.find((item) => item.id === id);
    if (found) { setExpression(found.expression); setDraft({ expression: found.expression, preset: id }); }
  };
  const run = () => {
    const universe: Record<string, unknown> = { exclude_st: excludeSt, exclude_suspended: true, min_amount: Number(minAmount) || 0 };
    if (board) universe.boards = [board];
    setDraft({ expression, preset });
    runScreener.mutate({ expression, universe, limit: 500 });
  };
  const save = () => {
    const name = savedName.trim() || expression.slice(0, 28);
    const next = [{ name, expression, board, excludeSt, minAmount, at: new Date().toISOString() }, ...saved].slice(0, 20);
    setSaved(next);
    localStorage.setItem("qc_screener_saved", JSON.stringify(next));
    setNotice(`已保存「${name}」（本机 localStorage）`);
    setSavedName("");
  };
  const exportCsv = () => {
    if (!result) return;
    const rows = result.rows.map((row) => ({ ...row }));
    downloadText("screener.csv", toCsv(rows, ["code", "name", "board", "industry", "close", "change_pct", "turnover", "mktcap", "score"]));
  };
  const backtestWithResult = () => navigate(`/backtest?screener=${encodeURIComponent(expression)}`);
  const columns = useMemo<ColumnDef<ScreenerRow, unknown>[]>(() => [
    { accessorKey: "code", header: "代码", size: 96, cell: ({ row }) => <span className="mono">{row.original.code}</span> },
    { accessorKey: "name", header: "名称", size: 150, cell: ({ row }) => <span className="truncate" title={row.original.name}>{row.original.name}</span> },
    { accessorKey: "board", header: "板块", size: 84 },
    { accessorKey: "industry", header: "行业", size: 100, cell: ({ row }) => <span className="truncate" title={row.original.industry}>{row.original.industry}</span> },
    { accessorKey: "close", header: "收盘", size: 88, cell: ({ row }) => <span className="num">{num(row.original.close)}</span> },
    { accessorKey: "change_pct", header: "涨跌", size: 88, cell: ({ row }) => <span className={`num ${row.original.change_pct >= 0 ? "up" : "down"}`}>{signedPct(row.original.change_pct / 100)}</span> },
    { accessorKey: "turnover", header: "换手", size: 84, cell: ({ row }) => <span className="num">{num(row.original.turnover)}%</span> },
    { accessorKey: "mktcap", header: "市值", size: 100, cell: ({ row }) => <span className="num">{compact(row.original.mktcap)}</span> },
    { accessorKey: "score", header: "分数", size: 84, cell: ({ row }) => <span className="num">{num(row.original.score, 3)}</span> },
  ], []);

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>选股</h1><p className="page-lead">一句话描述条件，选出一篮子股票；可直接用结果发起回测。</p></div>
        <div className="page-head-actions">
          <button className="btn" onClick={save} disabled={!expression.trim()}><Save size={15} /> 保存预设</button>
          <button className="btn" onClick={exportCsv} disabled={!result}><Download size={15} /> 导出 CSV</button>
          <button className="btn primary" onClick={run} disabled={runScreener.isPending}><Play size={15} /> {runScreener.isPending ? "运行中…" : "运行选股"}</button>
        </div>
      </header>

      <Panel title="选股条件" subtitle="模板是常用条件；也可以直接改 DSL 表达式" actions={presets.isError ? <Badge tone="warn">预设加载失败，可自定义</Badge> : <span className="muted small">{presets.data?.length ?? 0} 个模板</span>}>
        {presets.isLoading ? <Skeleton rows={2} /> : (
          <div className="chip-row">
            {(presets.data ?? []).map((item) => <Tag key={item.id} tone={preset === item.id ? "info" : "neutral"} active={preset === item.id} onClick={() => applyPreset(item.id)} title={item.description}>{item.name}</Tag>)}
            <Tag tone="neutral" active={!preset} onClick={() => { setPreset(""); setExpression(DEFAULT_EXPRESSION); }}>自定义</Tag>
          </div>
        )}
        <label className="field-label" htmlFor="screener-expression">选股条件（DSL 一句话）</label>
        <textarea id="screener-expression" className="code-input" value={expression} onChange={(event) => setExpression(event.target.value)} rows={3} spellCheck={false} placeholder={DEFAULT_EXPRESSION} />
        <div className="form-grid" style={{ marginTop: 10 }}>
          <label>板块<select value={board} onChange={(event) => setBoard(event.target.value)}><option value="">全部 A 股</option><option value="MAIN">主板</option><option value="GEM">创业板</option><option value="STAR">科创板</option><option value="BSE">北交所</option></select></label>
          {!beginner ? <label>最小成交额<input value={minAmount} onChange={(event) => setMinAmount(event.target.value)} inputMode="decimal" /></label> : null}
          {!beginner ? <label className="check-line" style={{ alignSelf: "end" }}><input type="checkbox" checked={excludeSt} onChange={(event) => setExcludeSt(event.target.checked)} /> 剔除 ST</label> : null}
          <label>保存名称<input value={savedName} onChange={(event) => setSavedName(event.target.value)} placeholder="方案名称（可选）" /></label>
        </div>
        <p className="muted small">字段 open/high/low/close/volume/amount/turnover/mktcap；函数 ma/std/ret/rank/zscore/ts_mean/ts_std/ts_sum/delay。仅研究，不构成投资建议。{saved.length ? ` 本机已保存 ${saved.length} 个方案。` : ""}</p>
      </Panel>

      <Panel title="选股结果" subtitle={result ? `${result.matched_count} / ${result.universe_count} 只 · 截至 ${result.as_of}` : "运行后显示匹配股票"} actions={result ? <div className="row"><button className="btn primary" onClick={backtestWithResult}><ListFilter size={15} /> 用这个结果回测</button><button className="btn" onClick={exportCsv}><Download size={15} /> 导出</button></div> : null}>
        {runScreener.isPending ? <Skeleton rows={6} /> : runScreener.error ? <EmptyState title="选股运行失败" hint={runScreener.error.message} action={<button className="btn" onClick={run}>重试</button>} /> : !result ? <EmptyState title="还没有选股结果" hint="点右上角「运行选股」；结果会显示匹配数量、排序表格，并可一键带回回测。" action={<button className="btn primary" onClick={run}><Play size={15} /> 运行选股</button>} /> : (
          <VirtualTable data={result.rows} columns={columns} rowKey={(row) => row.sec_id} height={460} ariaLabel="选股结果" empty={<span className="muted">没有股票匹配当前条件。</span>} />
        )}
      </Panel>
      {notice ? <p className="success-text">{notice}</p> : null}
      {beginner ? <p className="muted small">新手提示：先选一个模板再运行；把结果带到回测页只是研究记录，回测仍按策略模板选股。</p> : null}
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
