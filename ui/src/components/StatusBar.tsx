import { useEffect, useState } from "react";
import { useDataStatus, useHealth, useJobs, useMeta } from "../api/queries";
import { getApiBase } from "../api/client";
import { dateInt } from "../lib/format";
import { zhCN as t } from "../i18n/zh-CN";

export default function StatusBar() {
  const health = useHealth();
  const meta = useMeta();
  const data = useDataStatus();
  const running = useJobs("running");
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  const snapshot = data.data?.snapshots[0];
  const source = snapshot ? (snapshot.synthetic ? "SYNTHETIC" : snapshot.source && snapshot.source !== "unknown" ? snapshot.source : "本地快照") : meta.data?.synthetic_only ? "SYNTHETIC" : "—";
  const job = running.data?.[0];
  const connected = !health.isError && !meta.isError && online;
  return (
    <footer className={`statusbar ${connected ? "" : "offline"}`} aria-label="工作区状态">
      <span>{t.status.dataDate}: {snapshot ? dateInt(snapshot.end) : "—"}</span>
      <span>{t.status.source}: {source}</span>
      <span>{t.status.task}: {job ? `${job.kind} ${Math.round(job.progress * 100)}%` : "idle"}</span>
      <span>{t.status.network}: {connected ? (health.data?.engine_backend ?? meta.data?.engine_backend ?? "…") : t.status.disconnected}</span>
      <span>版本: {health.data?.version ?? meta.data?.version ?? "—"}</span>
      <span className="statusbar-spacer">{getApiBase() || "same-origin"}</span>
    </footer>
  );
}
