import { zhCN as t } from "../i18n/zh-CN";

export default function EmptyState({ title, hint }: { title?: string; hint?: string }) {
  return (
    <div className="empty card">
      <strong>{title || t.common.empty}</strong>
      <span>{hint || t.common.connectHint}</span>
    </div>
  );
}
