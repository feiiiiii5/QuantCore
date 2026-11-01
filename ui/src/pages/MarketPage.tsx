import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { Bars, MarketOverview, SecurityRow } from "../api/types";
import Chart from "../components/Chart";
import Sparkline from "../components/Sparkline";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";
import { useChartPalette } from "../theme";

const percent = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;

export default function MarketPage() {
  const palette = useChartPalette();
  const [searchParams] = useSearchParams();
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [securities, setSecurities] = useState<SecurityRow[]>([]);
  const [selected, setSelected] = useState<SecurityRow | null>(null);
  const [bars, setBars] = useState<Bars | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [barLoading, setBarLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [ov, rows] = await Promise.all([api.overview(), api.securities("", 300)]);
      setOverview(ov); setSecurities(rows);
      const code = searchParams.get("code");
      const hit = code ? rows.find((row) => row.code === code || row.sec_id === code) : undefined;
      const first = hit || rows.find((row) => !row.suspended) || rows[0] || null;
      setSelected(first);
      if (first) setBars(await api.bars(first.code));
    } catch (e) { setError(`${e}`); } finally { setLoading(false); }
  }, [searchParams]);
  useEffect(() => { void load(); }, [load]);

  const pick = async (row: SecurityRow) => {
    setSelected(row); setBarLoading(true); setError("");
    try { setBars(await api.bars(row.code)); } catch (e) { setError(`${e}`); } finally { setBarLoading(false); }
  };
  const filtered = securities.filter((row) => !query || `${row.code}${row.name}${row.industry}`.toLowerCase().includes(query.toLowerCase()));

  const candleOption = bars && {
    animation: false,
    tooltip: { trigger: "axis" as const, axisPointer: { type: "cross" as const } },
    legend: { data: ["K线", "MA5", "MA20"], top: 0, textStyle: { fontSize: 11 } },
    grid: [{ left: 50, right: 16, top: 32, height: "58%" }, { left: 50, right: 16, top: "76%", height: "16%" }],
    xAxis: [
      { type: "category" as const, data: bars.dates, axisLine: { lineStyle: { color: "#9aa3af" } }, axisLabel: { fontSize: 10 } },
      { type: "category" as const, data: bars.dates, gridIndex: 1, axisLabel: { show: false }, axisTick: { show: false } },
    ],
    yAxis: [
      { type: "value" as const, scale: true, splitLine: { lineStyle: { color: "rgba(148,163,184,.18)" } } },
      { type: "value" as const, gridIndex: 1, splitNumber: 2, axisLabel: { fontSize: 10 } },
    ],
    dataZoom: [{ type: "inside" as const, xAxisIndex: [0, 1], start: 55, end: 100 }],
    series: [
      {
        name: "K线", type: "candlestick" as const,
        data: bars.dates.map((_, i) => [bars.open[i], bars.close[i], bars.low[i], bars.high[i]]),
        itemStyle: { color: palette.up, color0: palette.down, borderColor: palette.up, borderColor0: palette.down },
      },
      { name: "MA5", type: "line" as const, data: bars.ma5, showSymbol: false, lineStyle: { width: 1, color: "#eab308" } },
      { name: "MA20", type: "line" as const, data: bars.ma20, showSymbol: false, lineStyle: { width: 1, color: "#3b82f6" } },
      { name: "成交量", type: "bar" as const, xAxisIndex: 1, yAxisIndex: 1, data: bars.volume, itemStyle: { color: "rgba(99,102,241,.45)" } },
    ],
  };

  return (
    <>
      <div className="page-head">
        <div><h1>行情</h1><p>指数、涨跌分布、行业板块、自选与 K 线（本地快照，SYNTHETIC 标注）</p></div>
        <button className="btn" onClick={() => void load()}><RefreshCw size={15} /> 刷新</button>
      </div>
      {loading ? <StatePanel loading /> : error && !overview ? <StatePanel error={error} onRetry={() => void load()} /> : null}
      {overview ? (
        <>
          <div className="grid kpis">
            {overview.indices.map((index) => (
              <div className="card index-card" key={index.name}>
                <div className="index-top"><h3>{index.name}</h3><span className={index.change_pct >= 0 ? "up" : "down"}>{percent(index.change_pct)}</span></div>
                <div className="kpi">{index.close.toFixed(2)}</div>
                <Sparkline values={index.spark} positive={index.change_pct >= 0} />
              </div>
            ))}
          </div>
          <div className="grid two-col" style={{ marginTop: 14 }}>
            <div className="card">
              <h3>涨跌分布 <span className="muted small">截至 {overview.as_of || "—"}</span></h3>
              <div className="breadth">
                <span className="up">上涨 {overview.breadth.up}</span>
                <span className="down">下跌 {overview.breadth.down}</span>
                <span>平盘 {overview.breadth.flat}</span>
                <span>涨停 {overview.breadth.limit_up}</span>
                <span>跌停 {overview.breadth.limit_down}</span>
                <span>停牌 {overview.breadth.suspended}</span>
              </div>
            </div>
            <div className="card">
              <h3>行业板块</h3>
              <div className="sector-list">
                {overview.sectors.slice(0, 8).map((sector) => (
                  <div className="sector-row" key={sector.name}>
                    <span>{sector.name}</span>
                    <span className={sector.avg_change >= 0 ? "up" : "down"}>{percent(sector.avg_change)}</span>
                    <small>{sector.up}↑ / {sector.down}↓</small>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="grid market-layout" style={{ marginTop: 14 }}>
            <div className="card market-table-card">
              <div className="card-head"><h3>证券列表</h3><input className="input compact" placeholder="代码/名称/行业" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
              <div className="table-wrap tall">
                <table>
                  <thead><tr><th>代码</th><th>名称</th><th>行业</th><th className="num">最新</th><th className="num">涨跌</th><th className="num">换手</th></tr></thead>
                  <tbody>
                    {filtered.slice(0, 120).map((row) => (
                      <tr key={row.sec_id} className={selected?.sec_id === row.sec_id ? "selected" : ""} onClick={() => void pick(row)}>
                        <td>{row.code}</td><td>{row.name}</td><td>{row.industry}</td>
                        <td className="num">{row.last.toFixed(2)}</td>
                        <td className={`num ${row.change_pct >= 0 ? "up" : "down"}`}>{percent(row.change_pct)}</td>
                        <td className="num">{row.turnover.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card chart-card">
              <div className="card-head"><h3>{selected ? `${selected.code} ${selected.name}` : "K 线"}</h3><span className="muted small">{selected ? `${selected.board} · ${selected.industry}` : ""}</span></div>
              {barLoading ? <StatePanel loading /> : candleOption ? <Chart option={candleOption} height={430} /> : <StatePanel empty emptyHint="选择证券查看 K 线" />}
            </div>
          </div>
          {overview.snapshot.synthetic ? <p className="notice">当前为 SYNTHETIC 合成行情，仅用于功能演示，不代表真实市场。</p> : null}
          <p className="muted small">{t.disclaimer}</p>
        </>
      ) : null}
    </>
  );
}
