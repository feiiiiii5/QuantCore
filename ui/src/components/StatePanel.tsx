import { AlertCircle, Inbox, Loader2 } from "lucide-react";

export default function StatePanel({ loading, error, empty, emptyHint, onRetry }: { loading?: boolean; error?: string; empty?: boolean; emptyHint?: string; onRetry?: () => void }) {
  if (loading) return <div className="state-panel"><Loader2 className="spin" size={20} /><span>加载中…</span></div>;
  if (error) return <div className="state-panel error"><AlertCircle size={20} /><span>{error}</span>{onRetry ? <button className="btn" onClick={onRetry}>重试</button> : null}</div>;
  if (empty) return <div className="state-panel"><Inbox size={20} /><span>{emptyHint || "暂无数据"}</span>{onRetry ? <button className="btn" onClick={onRetry}>刷新</button> : null}</div>;
  return null;
}
