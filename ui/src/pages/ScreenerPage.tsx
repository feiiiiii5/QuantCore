import EmptyState from "../components/EmptyState";
export default function ScreenerPage() {
  return (
    <>
      <div className="page-head"><div><h1>选股</h1><p>DSL 条件组合 · 股票池 · 保存方案 · 导出</p></div><button className="btn primary">运行选股</button></div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="form-row"><label>表达式</label><input defaultValue="rank(ts_mean(close,5)/ts_mean(close,20)) > 0.8" /></div>
        <div className="form-row"><label>股票池</label><select defaultValue="main"><option value="main">沪深主板</option><option value="all">全部 A 股</option></select></div>
      </div>
      <EmptyState title="暂无选股结果" hint="运行后显示筛选结果表格；需要本地快照与 qc serve。" />
    </>
  );
}
