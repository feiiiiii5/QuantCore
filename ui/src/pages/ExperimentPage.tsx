import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, GitCompare, RefreshCw, RotateCcw } from "lucide-react";
import { api, getApiBase, getToken } from "../api/client";
import type { BacktestResultPayload, Experiment } from "../api/types";
import Chart from "../components/Chart";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

export default function ExperimentPage() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [result, setResult] = useState<BacktestResultPayload | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<Array<{ run_id: string; dates: number[]; equity: number[] }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [replayMessage, setReplayMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const list = await api.experiments();
      setItems(list);
      if (list[0] && !selected) { setSelected(list[0].run_id); }
    } catch (e) { setError(`${e}`); } finally { setLoading(false); }
  }, [selected]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!selected) { setResult(null); return; }
    api.experimentResult(selected).then(setResult).catch((e) => setError(`${e}`));
  }, [selected]);

  const current = items.find((item) => item.run_id === selected) || null;
  const toggleCompare = (id: string) => setCompareIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id].slice(0, 5));
  const compare = async () => {
    setError(""); setCompareData([]);
    if (compareIds.length < 2) { setError("至少选择两个实验进行对比"); return; }
    try {
      const base = getApiBase();
      const response = await fetch(`${base}/api/experiments/compare?ids=${compareIds.join(",")}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      setCompareData(payload.equity || []);
    } catch (e) { setError(`${e}`); }
  };
  const replay = async () => {
    setReplayMessage("");
    try {
      const outcome = await api.replayExperiment(selected);
      setReplayMessage(outcome.matched ? "复现一致：净值、交易、指标全部匹配" : `发现差异：${JSON.stringify(outcome.differences)}`);
    } catch (e) { setReplayMessage(`${e}`); }
  };
  const download = async (path: string, filename: string) => {
    const response = await fetch(`${getApiBase()}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  };

  const option = useMemo(() => {
    if (result) {
      return {
        animation: false, tooltip: { trigger: "axis" as const }, grid: { left: 68, right: 20, top: 24, bottom: 40 },
        xAxis: { type: "category" as const, data: result.dates.map(String), axisLabel: { fontSize: 10 } },
        yAxis: { type: "value" as const, scale: true, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
        dataZoom: [{ type: "inside" as const, start: 0, end: 100 }],
        series: [{ type: "line" as const, name: "净值", data: result.equity, showSymbol: false, lineStyle: { width: 1.6, color: "#2563eb" } }],
      };
    }
    if (compareData.length) {
      return {
        animation: false, tooltip: { trigger: "axis" as const }, legend: { top: 0, textStyle: { fontSize: 10 } },
        xAxis: { type: "category" as const, data: compareData[0].dates.map(String), axisLabel: { fontSize: 10 } },
        yAxis: { type: "value" as const, scale: true },
        series: compareData.map((item, index) => ({ type: "line" as const, name: item.run_id.slice(0, 18), data: item.equity, showSymbol: false, lineStyle: { width: index === 0 ? 1.6 : 1, } })),
      };
    }
    return null;
  }, [result, compareData]);

  return (
    <>
      <div className="page-head"><div><h1>实验</h1><p>版本 · 参数 · 快照 · 复现 · 对比 · 导出</p></div><button className="btn" onClick={() => void load()}><RefreshCw size={15} /> 刷新</button></div>
      {loading ? <StatePanel loading /> : error && !items.length ? <StatePanel error={error} onRetry={() => void load()} /> : null}
      {!loading && !items.length ? <StatePanel empty emptyHint="运行一次回测后，实验会出现在这里。" /> : null}
      {items.length ? (
        <div className="grid experiments-layout">
          <div className="card experiment-list">
            <h3>运行记录</h3>
            {items.map((item) => (
              <div key={item.run_id} className={`experiment-item ${selected === item.run_id ? "active" : ""}`} onClick={() => setSelected(item.run_id)}>
                <div><strong>{item.strategy_name || item.template || item.run_id}</strong><small>{item.run_id}</small></div>
                <div className="experiment-meta"><span className={(item.metrics?.total_return || 0) >= 0 ? "up" : "down"}>{item.metrics ? `${(item.metrics.total_return * 100).toFixed(2)}%` : "—"}</span><input type="checkbox" aria-label="compare" checked={compareIds.includes(item.run_id)} onChange={() => toggleCompare(item.run_id)} onClick={(e) => e.stopPropagation()} /></div>
              </div>
            ))}
            <button className="btn" style={{ marginTop: 8 }} onClick={() => void compare()}><GitCompare size={15} /> 对比所选</button>
          </div>
          <div className="card result-card">
            {!selected ? <StatePanel empty emptyHint="选择一个实验" /> : (
              <>
                <div className="card-head"><h3>{current?.strategy_name || selected}</h3><div className="button-row"><button className="btn" onClick={() => void replay()}><RotateCcw size={15} /> 复现</button><button className="btn" onClick={() => void download(`/api/experiments/${selected}/report`, `${selected}.html`)}><Download size={15} /> 报告</button><button className="btn" onClick={() => void download(`/api/experiments/${selected}/export`, `${selected}.zip`)}><Download size={15} /> 导出</button></div></div>
                {replayMessage ? <p className={replayMessage.startsWith("复现一致") ? "success-text" : "error"}>{replayMessage}</p> : null}
                {option ? <Chart option={option} height={340} /> : <StatePanel loading />}
                {result ? <div className="metric-inline"><span>总收益 <strong>{(result.metrics.total_return * 100).toFixed(2)}%</strong></span><span>Sharpe <strong>{result.metrics.sharpe.toFixed(2)}</strong></span><span>最大回撤 <strong>{(result.metrics.max_drawdown * 100).toFixed(2)}%</strong></span><span>交易 <strong>{result.trades.length}</strong></span><span>引擎 <strong>{result.engine_backend}</strong></span></div> : null}
                <p className="muted small">{t.disclaimer}</p>
              </>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
