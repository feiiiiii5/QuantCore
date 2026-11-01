import EmptyState from "../components/EmptyState";
export default function ExperimentPage() {
  return (<><div className="page-head"><div><h1>实验</h1><p>版本 · 参数 · 快照哈希 · 对比 · 导出/replay</p></div></div><EmptyState title="暂无实验" hint="运行一次回测后，实验会保存策略版本、参数、快照与引擎元数据。" /></>);
}
