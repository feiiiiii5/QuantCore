import { useMemo, useState } from "react";
import { Download, ListFilter, Play, Save } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { useRunScreener, useScreenerPresets } from "../api/queries";
import type { ScreenerRow } from "../api/types";
import {
  Button, EmptyState, Field, Input, PageHeader, Panel, Select, Skeleton, Tag, VirtualTable,
} from "../components";
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
    downloadText("screener.csv", toCsv(result.rows.map((row) => ({ ...row })), ["code", "name", "board", "industry", "close", "change_pct", "turnover", "mktcap", "score"]));
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
      <PageHeader
        title="选股"
        subtitle="一句话描述条件，选出一篮子股票；可直接用结果发起回测。"
        actions={(
          <>
            <Button variant="secondary" icon={Save} onClick={save} disabled={!expression.trim()}>保存预设</Button>
            <Button variant="secondary" icon={Download} onClick={exportCsv} disabled={!result}>导出 CSV</Button>
            <Button variant="primary" icon={Play} loading={runScreener.isPending} onClick={run}>{runScreener.isPending ? "运行中…" : "运行选股"}</Button>
          </>
        )}
      />

      <Panel title="选股条件" subtitle="模板是常用条件；也可以直接改 DSL 表达式" actions={presets.isError ? <span className="page-note-sm">预设加载失败，可自定义</span> : <span className="page-note-sm">{presets.data?.length ?? 0} 个模板</span>}>
        <div className="stack">
          {presets.isLoading ? <Skeleton rows={2} /> : (
            <div className="condition-chips">
              {(presets.data ?? []).map((item) => (
                <Tag key={item.id} active={preset === item.id} onClick={() => applyPreset(item.id)} title={item.description}>{item.name}</Tag>
              ))}
              <Tag active={!preset} onClick={() => { setPreset(""); setExpression(DEFAULT_EXPRESSION); }}>自定义</Tag>
            </div>
          )}
          <Field label="选股条件（DSL 一句话）" hint="字段 open/high/low/close/volume/amount/turnover/mktcap；函数 ma/std/ret/rank/zscore/ts_mean/ts_std/ts_sum/delay。">
            <textarea
              className="textarea"
              value={expression}
              onChange={(event) => setExpression(event.target.value)}
              rows={3}
              spellCheck={false}
              placeholder={DEFAULT_EXPRESSION}
              aria-label="选股条件（DSL 一句话）"
              style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-footnote)" }}
            />
          </Field>
          <div className="grid grid-3">
            <Field label="板块">
              <Select value={board} onChange={(event) => setBoard(event.target.value)} aria-label="板块" options={[
                { value: "", label: "全部 A 股" },
                { value: "MAIN", label: "主板" },
                { value: "GEM", label: "创业板" },
                { value: "STAR", label: "科创板" },
                { value: "BSE", label: "北交所" },
              ]} />
            </Field>
            {!beginner ? (
              <>
                <Field label="最小成交额">
                  <Input value={minAmount} onChange={(event) => setMinAmount(event.target.value)} inputMode="decimal" aria-label="最小成交额" />
                </Field>
                <Field label="股票池">
                  <label className="check-row" style={{ height: "var(--control-h)" }}>
                    <input className="checkbox" type="checkbox" checked={excludeSt} onChange={(event) => setExcludeSt(event.target.checked)} />
                    剔除 ST
                  </label>
                </Field>
              </>
            ) : null}
            <Field label="保存名称" hint={saved.length ? `本机已保存 ${saved.length} 个方案` : "可选；保存到本机 localStorage"}>
              <Input value={savedName} onChange={(event) => setSavedName(event.target.value)} placeholder="方案名称（可选）" aria-label="保存名称" />
            </Field>
          </div>
          {notice ? <p className="success-text">{notice}</p> : null}
        </div>
      </Panel>

      <Panel
        title="选股结果"
        subtitle={result ? `${result.matched_count} / ${result.universe_count} 只 · 截至 ${result.as_of}` : "运行后显示匹配股票"}
        actions={result ? (
          <>
            <Button variant="secondary" icon={Download} onClick={exportCsv}>导出</Button>
            <Button variant="primary" icon={ListFilter} onClick={backtestWithResult}>用这个结果回测</Button>
          </>
        ) : null}
      >
        {runScreener.isPending ? <Skeleton rows={6} /> : runScreener.error ? (
          <EmptyState title="选股运行失败" hint={runScreener.error.message} action={<Button variant="secondary" onClick={run}>重试</Button>} />
        ) : !result ? (
          <EmptyState title="还没有选股结果" hint="点右上角「运行选股」；结果会显示匹配数量、排序表格，并可一键带回回测。" action={<Button variant="primary" icon={Play} onClick={run}>运行选股</Button>} />
        ) : (
          <VirtualTable data={result.rows} columns={columns} rowKey={(row) => row.sec_id} height={460} ariaLabel="选股结果" empty={<span className="text-3">没有股票匹配当前条件。</span>} />
        )}
      </Panel>
      {beginner ? <p className="page-note-sm">新手提示：先选一个模板再运行；把结果带到回测页只是研究记录，回测仍按策略模板选股。</p> : null}
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
