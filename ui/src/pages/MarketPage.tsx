import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, SlidersHorizontal } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { useBars, useFinancials, useOverview, useSecurities, useSecurityProfile } from "../api/queries";
import type { SecurityRow } from "../api/types";
import KLineChart from "../components/KLineChart";
import Sparkline from "../components/Sparkline";
import StatePanel from "../components/StatePanel";
import VirtualTable from "../components/VirtualTable";
import { compact, num, signedPct } from "../lib/format";
import { useChartPalette } from "../theme";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";

export default function MarketPage() {
  const palette = useChartPalette();
  const [searchParams, setSearchParams] = useSearchParams();
  const overview = useOverview();
  const securitiesQuery = useSecurities("", 1000);
  const rows = securitiesQuery.data ?? [];
  const [picked, setPicked] = useState(() => useWorkspace.getState().marketCode);
  const [query, setQuery] = useState(() => useWorkspace.getState().marketQuery);
  const [showMA5, setShowMA5] = useState(true);
  const [showMA20, setShowMA20] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const setMarketCode = useWorkspace((state) => state.setMarketCode);
  const setMarketQuery = useWorkspace((state) => state.setMarketQuery);
  const code = searchParams.get("code") || picked || rows[0]?.code || "";
  const bars = useBars(code || null);
  const profile = useSecurityProfile(code || null);
  const financials = useFinancials(code || null);

  useEffect(() => {
    if (!code && rows[0]) { setPicked(rows[0].code); setMarketCode(rows[0].code); }
  }, [code, rows, setMarketCode]);
  useEffect(() => { setMarketQuery(query); }, [query, setMarketQuery]);

  const select = useCallback((row: SecurityRow) => {
    setPicked(row.code);
    setMarketCode(row.code);
    setSearchParams({ code: row.code }, { replace: true });
  }, [setMarketCode, setSearchParams]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => `${row.code}${row.name}${row.industry}${row.board}`.toLowerCase().includes(needle));
  }, [query, rows]);
  const selected = rows.find((row) => row.code === code) ?? null;
  const refresh = () => { void overview.refetch(); void securitiesQuery.refetch(); void bars.refetch(); };

  const columns = useMemo<ColumnDef<SecurityRow, unknown>[]>(() => [
    { accessorKey: "code", header: "代码", size: 96, cell: ({ row }) => <span className="mono">{row.original.code}</span> },
    { accessorKey: "name", header: "名称", size: 150, cell: ({ row }) => <span className="truncate" title={row.original.name}>{row.original.name}</span> },
    { accessorKey: "industry", header: "行业", size: 100, cell: ({ row }) => <span className="truncate" title={row.original.industry}>{row.original.industry}</span> },
    { accessorKey: "last", header: "最新", size: 92, cell: ({ row }) => <span className="num">{num(row.original.last)}</span> },
    { accessorKey: "change_pct", header: "涨跌", size: 88, cell: ({ row }) => <span className={`num ${row.original.change_pct >= 0 ? "up" : "down"}`}>{signedPct(row.original.change_pct / 100)}</span> },
    { accessorKey: "turnover", header: "换手", size: 84, cell: ({ row }) => <span className="num">{num(row.original.turnover)}%</span> },
    { accessorKey: "mktcap", header: "市值", size: 100, cell: ({ row }) => <span className="num" title={`${row.original.mktcap}`}>{compact(row.original.mktcap)}</span> },
  ], []);

  const loading = overview.isLoading || securitiesQuery.isLoading;
  const fatalError = overview.error || securitiesQuery.error;
  return (
    <>
      <div className="page-head">
        <div><h1>行情</h1><p>指数、涨跌分布、行业板块、证券搜索与 K 线（本地快照，SYNTHETIC 标注）</p></div>
        <button className="btn" onClick={refresh} disabled={loading}><RefreshCw size={15} /> 刷新</button>
      </div>
      {fatalError && !overview.data && !rows.length ? <StatePanel error={`本地服务未连接或尚无快照：${fatalError.message}`} onRetry={refresh} /> : null}
      {loading && !fatalError ? <StatePanel loading /> : null}
      {overview.data ? (
        <>
          <div className="grid kpis">
            {overview.data.indices.map((index) => (
              <div className="card index-card" key={index.name}>
                <div className="index-top"><h3>{index.name}</h3><span className={index.change_pct >= 0 ? "up" : "down"}>{signedPct(index.change_pct / 100)}</span></div>
                <div className="kpi">{num(index.close)}</div>
                <Sparkline values={index.spark} positive={index.change_pct >= 0} />
              </div>
            ))}
          </div>
          <div className="grid two-col" style={{ marginTop: 14 }}>
            <div className="card">
              <h3>涨跌分布 <span className="muted small">截至 {overview.data.as_of || "—"}</span></h3>
              <div className="breadth">
                <span className="up">上涨 {overview.data.breadth.up}</span>
                <span className="down">下跌 {overview.data.breadth.down}</span>
                <span>平盘 {overview.data.breadth.flat}</span>
                <span>涨停 {overview.data.breadth.limit_up}</span>
                <span>跌停 {overview.data.breadth.limit_down}</span>
                <span>停牌 {overview.data.breadth.suspended}</span>
              </div>
              <div className="breadth-bar" aria-hidden="true">
                <i className="up-bg" style={{ flex: Math.max(overview.data.breadth.up, 0.01) }} />
                <i className="flat-bg" style={{ flex: Math.max(overview.data.breadth.flat, 0.01) }} />
                <i className="down-bg" style={{ flex: Math.max(overview.data.breadth.down, 0.01) }} />
              </div>
            </div>
            <div className="card">
              <h3>行业板块</h3>
              {overview.data.sectors.length ? <div className="sector-list">{overview.data.sectors.slice(0, 10).map((sector) => (
                <div className="sector-row" key={sector.name}>
                  <span className="truncate" title={sector.name}>{sector.name}</span>
                  <span className={sector.avg_change >= 0 ? "up" : "down"}>{signedPct(sector.avg_change / 100)}</span>
                  <small>{sector.up}↑ / {sector.down}↓</small>
                </div>
              ))}</div> : <StatePanel empty emptyHint="当前快照没有行业数据。" />}
            </div>
          </div>
          <div className="grid market-layout" style={{ marginTop: 14 }}>
            <div className="card market-table-card">
              <div className="card-head"><h3>证券列表 <span className="muted small">{filtered.length} / {rows.length}</span></h3><input className="input compact" placeholder="代码/名称/行业" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="筛选证券" /></div>
              {securitiesQuery.isError ? <StatePanel error={securitiesQuery.error.message} onRetry={() => void securitiesQuery.refetch()} /> : (
                <VirtualTable data={filtered} columns={columns} rowKey={(row) => row.sec_id} height={450} onRowClick={select} ariaLabel="证券列表" empty={<span className="muted">没有匹配证券</span>} />
              )}
            </div>
            <div className="card chart-card">
              <div className="card-head">
                <h3>{selected ? `${selected.code} ${selected.name}` : "K 线"}</h3>
                <div className="chart-tools" aria-label="K线指标">
                  <span className="muted small">{selected ? `${selected.board} · ${selected.industry}` : ""}</span>
                  <button className={`chip ${showMA5 ? "active" : ""}`} onClick={() => setShowMA5((value) => !value)} aria-pressed={showMA5}>MA5</button>
                  <button className={`chip ${showMA20 ? "active" : ""}`} onClick={() => setShowMA20((value) => !value)} aria-pressed={showMA20}>MA20</button>
                  <button className={`chip ${showVolume ? "active" : ""}`} onClick={() => setShowVolume((value) => !value)} aria-pressed={showVolume}>量</button>
                  <SlidersHorizontal size={14} className="muted" aria-hidden="true" />
                </div>
              </div>
              {bars.isLoading ? <StatePanel loading /> : bars.error ? <StatePanel error={bars.error.message} onRetry={() => void bars.refetch()} /> : bars.data ? (
                <KLineChart bars={bars.data} palette={palette} height={430} showMA5={showMA5} showMA20={showMA20} showVolume={showVolume} />
              ) : <StatePanel empty emptyHint="选择左侧证券查看 K 线、成交量与均线" />}
              {profile.data ? (
                <div className="profile-strip">
                  <div><span>交易所</span><strong>{profile.data.exchange || "—"}</strong></div>
                  <div><span>板块 / 类型</span><strong>{profile.data.board} · {profile.data.sec_type}</strong></div>
                  <div><span>行业</span><strong>{profile.data.industry || "—"}</strong></div>
                  <div><span>上市日</span><strong>{profile.data.list_date ? String(profile.data.list_date).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3") : "—"}</strong></div>
                  <div><span>数据源</span><strong>{profile.data.source || "—"}</strong></div>
                  <div><span>最近成交额</span><strong>{compact(profile.data.quote.amount)}</strong></div>
                </div>
              ) : null}
              {financials.data?.latest ? (
                <div className="financial-panel">
                  <div className="card-head"><h3>PIT 财务 <span className="muted small">最近公告 {String(financials.data.latest.ann_date)}</span></h3><span className="muted small">{financials.data.note}</span></div>
                  <div className="table-wrap" style={{ maxHeight: 150 }}>
                    <table><thead><tr><th>报告期</th><th>公告日</th><th className="num">ROE</th><th className="num">EPS</th><th className="num">营收</th><th className="num">净利润</th></tr></thead>
                      <tbody>{financials.data.rows.slice(0, 6).map((row) => <tr key={`${row.end_date}-${row.ann_date}`}><td className="mono">{String(row.end_date)}</td><td className="mono">{String(row.ann_date)}</td><td className="num">{row.roe == null ? "—" : `${(row.roe * 100).toFixed(2)}%`}</td><td className="num">{row.eps?.toFixed(2) ?? "—"}</td><td className="num">{row.revenue == null ? "—" : compact(row.revenue)}</td><td className="num">{row.net_profit == null ? "—" : compact(row.net_profit)}</td></tr>)}</tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          {overview.data.snapshot.synthetic ? <p className="notice">当前为 SYNTHETIC 合成行情，仅用于功能演示，不代表真实市场。</p> : null}
        </>
      ) : null}
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
