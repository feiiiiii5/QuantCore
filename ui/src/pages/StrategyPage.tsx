import Editor from "@monaco-editor/react";
import EmptyState from "../components/EmptyState";
export default function StrategyPage() {
  return (
    <>
      <div className="page-head"><div><h1>策略</h1><p>模板 · 参数 JSON Schema · Monaco 编辑 · 版本与 diff</p></div></div>
      <div className="grid" style={{ gridTemplateColumns: "280px 1fr" }}>
        <div className="card"><h3>模板</h3><ul style={{ margin: 0, paddingLeft: 18, lineHeight: 2 }}><li>双均线</li><li>动量 / 反转</li><li>低波动</li><li>红利质量</li><li>小市值 + 流动性</li><li>多因子打分</li><li>买入持有</li></ul></div>
        <div className="card" style={{ minHeight: 360 }}>
          <Editor height="340px" defaultLanguage="python" defaultValue={"def on_rebalance(ctx):\n    return {}\n"} options={{ minimap: { enabled: false }, fontSize: 13 }} />
        </div>
      </div>
      <div style={{ height: 14 }} />
      <EmptyState title="策略服务未连接" hint="启动 qc serve 后，这里会加载策略列表、参数表单和运行日志。" />
    </>
  );
}
