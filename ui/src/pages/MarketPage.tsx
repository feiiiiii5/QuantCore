import EmptyState from "../components/EmptyState";
export default function MarketPage() {
  return (
    <>
      <div className="page-head"><div><h1>行情</h1><p>指数、涨跌分布、行业板块、自选与 K 线（数据来自本地快照）</p></div></div>
      <div className="grid kpis">
        {["上证指数", "深证成指", "创业板指", "北证50"].map((n) => (
          <div className="card" key={n}><h3>{n}</h3><div className="kpi">—</div></div>
        ))}
      </div>
      <div style={{ height: 14 }} />
      <EmptyState title="尚未加载行情" hint="配置数据源并构建快照后，这里会显示 K 线与板块数据。" />
    </>
  );
}
