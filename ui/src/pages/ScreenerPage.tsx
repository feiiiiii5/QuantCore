import { useMemo, useState } from "react";
import { Download, Play, Save } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { useRunScreener, useScreenerPresets } from "../api/queries";
import type { ScreenerRow } from "../api/types";
import StatePanel from "../components/StatePanel";
import VirtualTable from "../components/VirtualTable";
import { compact, downloadText, num, signedPct, toCsv } from "../lib/format";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";

const DEFAULT_EXPRESSION = "rank(ret(close,20)) > 0.8 and ma(close,5) > ma(close,20)";
interface SavedScreener { name: string; expression: string; board: string; excludeSt: boolean; minAmount: string; at: string }

export default function ScreenerPage() {
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
    setNotice(`已保存“${name}”（localStorage）`);
    setSavedName("");
  };
  const exportCsv = () => {
    if (!result) return;
    const rows = result.rows.map((row) => ({ ...row }));
    downloadText("screener.csv", toCsv(rows, ["code", "name", "board", "industry", "close", "change_pct", "turnover", "mktcap", "score"]));
  };
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
    <>
      <div className="page-head">
        <div><h1>选股</h1><p>DSL 条件组合 · 股票池 · 结果排序 · 保存与 CSV 导出</p></div>
        <div className="button-row">
          <button className="btn" onClick={save} disabled={!expression.trim()}><Save size={15} /> 保存</button>
          <button className="btn" onClick={exportCsv} disabled={!result}><Download size={15} /> 导出</button>
          <button className="btn primary" onClick={run} disabled={runScreener.isPending}><Play size={15} /> {runScreener.isPending ? "运行中…" : "运行选股"}</button>
        </div>
      </div>
      <div className="card">
        {presets.isError ? <StatePanel error={presets.error.message} onRetry={() => void presets.refetch()} /> : (
          <>
            <div className="form-grid">
              <label>预设<select value={preset} onChange={(event) => applyPreset(event.target.value)}><option value="">自定义</option>{(presets.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label>板块<select value={board} onChange={(event) => setBoard(event.target.value)}><option value="">全部 A 股</option><option value="MAIN">主板</option><option value="GEM">创业板</option><option value="STAR">科创板</option><option value="BSE">北交所</option></select></label>
              <label>最小成交额<input value={minAmount} onChange={(event) => setMinAmount(event.target.value)} inputMode="decimal" /></label>
            </div>
            <label className="check-line"><input type="checkbox" checked={excludeSt} onChange={(event) => setExcludeSt(event.target.checked)} /> 剔除 ST</label>
          </>
        )}
        <label className="field-label" htmlFor="screener-expression">表达式（DSL）</label>
        <textarea id="screener-expression" className="code-input" value={expression} onChange={(event) => setExpression(event.target.value)} rows={3} spellCheck={false} />
        <div className="inline-actions">
          <input className="input compact" placeholder="方案名称（可选）" value={savedName} onChange={(event) => setSavedName(event.target.value)} />
          {saved.length ? <span className="muted small">已保存 {saved.length} 个方案</span> : null}
        </div>
        <p className="muted small">字段 open/high/low/close/volume/amount/turnover/mktcap；函数 ma/std/ret/rank/zscore/ts_mean/ts_std/ts_sum/delay。仅研究，不构成投资建议。</p>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        {runScreener.isPending ? <StatePanel loading /> : runScreener.error ? <StatePanel error={runScreener.error.message} onRetry={run} /> : !result ? <StatePanel empty emptyHint="运行一个选股表达式，结果会显示在这里。" /> : (
          <>
            <div className="card-head"><h3>结果 <span className="muted small">{result.matched_count} / {result.universe_count} 只 · 截至 {result.as_of}</span></h3><span className="muted small">点击表头排序</span></div>
            <VirtualTable data={result.rows} columns={columns} rowKey={(row) => row.sec_id} height={460} ariaLabel="选股结果" empty={<span className="muted">没有股票匹配当前条件。</span>} />
          </>
        )}
      </div>
      {notice ? <p className="success-text">{notice}</p> : null}
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
