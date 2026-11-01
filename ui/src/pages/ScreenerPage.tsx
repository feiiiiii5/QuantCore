import { useCallback, useEffect, useState } from "react";
import { Download, Play, Save } from "lucide-react";
import { api } from "../api/client";
import type { ScreenerPreset, ScreenerResult } from "../api/types";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

const DEFAULT_EXPRESSION = "rank(ret(close,20)) > 0.8 and ma(close,5) > ma(close,20)";

export default function ScreenerPage() {
  const [presets, setPresets] = useState<ScreenerPreset[]>([]);
  const [preset, setPreset] = useState("");
  const [expression, setExpression] = useState(DEFAULT_EXPRESSION);
  const [board, setBoard] = useState("");
  const [excludeSt, setExcludeSt] = useState(true);
  const [minAmount, setMinAmount] = useState("0");
  const [result, setResult] = useState<ScreenerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { api.screenerPresets().then(setPresets).catch(() => undefined); }, []);
  const applyPreset = (id: string) => {
    setPreset(id);
    const found = presets.find((item) => item.id === id);
    if (found) setExpression(found.expression);
  };
  const run = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const universe: Record<string, unknown> = { exclude_st: excludeSt, exclude_suspended: true, min_amount: Number(minAmount) || 0 };
      if (board) universe.boards = [board];
      setResult(await api.runScreener({ expression, universe, limit: 300 }));
    } catch (e) { setError(`${e}`); } finally { setLoading(false); }
  }, [expression, board, excludeSt, minAmount]);
  const save = () => {
    const saved = JSON.parse(localStorage.getItem("qc_screener_saved") || "[]");
    saved.unshift({ expression, board, excludeSt, minAmount, at: new Date().toISOString() });
    localStorage.setItem("qc_screener_saved", JSON.stringify(saved.slice(0, 20)));
  };
  const exportCsv = () => {
    if (!result) return;
    const header = "code,name,board,industry,close,change_pct,turnover,mktcap,score\n";
    const body = result.rows.map((row) => [row.code, row.name, row.board, row.industry, row.close, row.change_pct, row.turnover, row.mktcap, row.score].join(",")).join("\n");
    const blob = new Blob([header + body], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "screener.csv"; link.click();
  };

  return (
    <>
      <div className="page-head"><div><h1>选股</h1><p>DSL 条件组合 · 股票池 · 保存方案 · 导出</p></div>
        <div className="button-row"><button className="btn" onClick={save}><Save size={15} /> 保存</button><button className="btn" onClick={exportCsv} disabled={!result}><Download size={15} /> 导出</button><button className="btn primary" onClick={() => void run()} disabled={loading}><Play size={15} /> {loading ? "运行中…" : "运行选股"}</button></div>
      </div>
      <div className="card">
        <div className="form-grid">
          <label>预设<select value={preset} onChange={(e) => applyPreset(e.target.value)}><option value="">自定义</option>{presets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>板块<select value={board} onChange={(e) => setBoard(e.target.value)}><option value="">全部 A 股</option><option value="MAIN">主板</option><option value="GEM">创业板</option><option value="STAR">科创板</option><option value="BSE">北交所</option></select></label>
          <label>最小成交额<input value={minAmount} onChange={(e) => setMinAmount(e.target.value)} inputMode="decimal" /></label>
          <label className="check"><input type="checkbox" checked={excludeSt} onChange={(e) => setExcludeSt(e.target.checked)} /> 剔除 ST</label>
        </div>
        <label className="field-label">表达式（DSL）</label>
        <textarea className="code-input" value={expression} onChange={(e) => setExpression(e.target.value)} rows={3} spellCheck={false} />
        <p className="muted small">支持字段 open/high/low/close/volume/amount/turnover/mktcap/... 与函数 ma/std/ret/rank/zscore/ts_mean/ts_std/ts_sum/delay。</p>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        {loading ? <StatePanel loading /> : error ? <StatePanel error={error} onRetry={() => void run()} /> : !result ? <StatePanel empty emptyHint="运行一个选股表达式，结果会显示在这里。" /> : (
          <>
            <div className="card-head"><h3>结果 <span className="muted small">{result.matched_count} / {result.universe_count} 只 · 截至 {result.as_of}</span></h3></div>
            <div className="table-wrap tall">
              <table>
                <thead><tr><th>代码</th><th>名称</th><th>板块</th><th>行业</th><th className="num">收盘</th><th className="num">涨跌</th><th className="num">换手</th><th className="num">市值</th><th className="num">分数</th></tr></thead>
                <tbody>{result.rows.map((row) => <tr key={row.sec_id}><td>{row.code}</td><td>{row.name}</td><td>{row.board}</td><td>{row.industry}</td><td className="num">{row.close.toFixed(2)}</td><td className={`num ${row.change_pct >= 0 ? "up" : "down"}`}>{row.change_pct.toFixed(2)}%</td><td className="num">{row.turnover.toFixed(2)}%</td><td className="num">{(row.mktcap / 1e8).toFixed(1)} 亿</td><td className="num">{row.score.toFixed(3)}</td></tr>)}</tbody>
              </table>
            </div>
          </>
        )}
      </div>
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
