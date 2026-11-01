import { useState } from "react";
import { api } from "../api/client";
import type { BacktestResult } from "../api/types";
import { zhCN as t } from "../i18n/zh-CN";

export default function BacktestPage() {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");
  const run = async () => {
    setError("");
    try {
      setResult(await api.runBacktest({ snapshot: "synthetic", strategy: "ma_cross" }));
    } catch (e) {
      setError(`${e}`);
    }
  };
  return (
    <>
      <div className="page-head"><div><h1>回测</h1><p>净值/回撤 · 指标 · 交易解释 · 参数稳定性</p></div><button className="btn primary" onClick={run}>{t.common.run}</button></div>
      <div className="grid" style={{ gridTemplateColumns: "320px 1fr" }}>
        <div className="card">
          <div className="form-row"><label>日期</label><input defaultValue="2021-01-01 ~ 2025-12-31" /></div>
          <div className="form-row"><label>初始资金</label><input defaultValue="1000000" /></div>
          <div className="form-row"><label>调仓</label><select defaultValue="monthly"><option value="monthly">月度</option><option value="weekly">周度</option></select></div>
          <div className="form-row"><label>成交</label><select defaultValue="next_open"><option value="next_open">次日开盘</option><option value="next_close">次日收盘</option></select></div>
          <p style={{ color: "var(--muted)", fontSize: 11 }}>{t.disclaimer}</p>
        </div>
        <div className="card">
          {error ? <p className="error">{error}</p> : null}
          {!result ? <div className="empty"><strong>尚无可展示的回测</strong><span>运行后显示指标、净值、回撤与逐笔交易。</span></div> : (
            <>
              <div className="grid kpis">
                <div><h3>总收益</h3><div className="kpi">{(result.metrics.total_return * 100).toFixed(2)}%</div></div>
                <div><h3>年化</h3><div className="kpi">{(result.metrics.annualized_return * 100).toFixed(2)}%</div></div>
                <div><h3>Sharpe</h3><div className="kpi">{result.metrics.sharpe.toFixed(2)}</div></div>
                <div><h3>最大回撤</h3><div className="kpi down">{(result.metrics.max_drawdown * 100).toFixed(2)}%</div></div>
              </div>
              <p style={{ color: "var(--muted)", fontSize: 12 }}>engine {result.engine_version}；交易 {result.metrics.trade_count} 笔</p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
