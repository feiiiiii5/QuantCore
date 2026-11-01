import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";

export default function StatePanel({ loading, error, empty, emptyHint, onRetry }: { loading?: boolean; error?: string; empty?: boolean; emptyHint?: string; onRetry?: () => void }) {
  if (loading) return <div className="state-panel" role="status"><Loader2 className="spin" size={20} /><span>加载中…</span></div>;
  if (error) return (
    <div className="state-panel error" role="alert">
      <AlertCircle size={20} />
      <span>{error}</span>
      <div className="button-row">
        {onRetry ? <button className="btn" onClick={onRetry}>重试</button> : null}
        <Link className="btn" to="/settings">连接设置</Link>
      </div>
    </div>
  );
  if (empty) return (
    <div className="state-panel">
      <Inbox size={20} />
      <span>{emptyHint || "暂无数据"}</span>
      <div className="button-row">
        {onRetry ? <button className="btn" onClick={onRetry}>刷新</button> : null}
        <Link className="btn" to="/settings">连接设置</Link>
      </div>
    </div>
  );
  return null;
}
