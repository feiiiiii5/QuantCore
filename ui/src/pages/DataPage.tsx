import EmptyState from "../components/EmptyState";
export default function DataPage() {
  return (<><div className="page-head"><div><h1>数据</h1><p>数据源 · 下载/增量 · 质量报告 · 导入导出 · 快照</p></div><button className="btn primary">构建快照</button></div><EmptyState title="尚未配置数据源" hint="支持 Synthetic / LocalFile / Tushare（需 Token）/ AKShare / mootdx；见 docs/DEV-SETUP.md。" /></>);
}
