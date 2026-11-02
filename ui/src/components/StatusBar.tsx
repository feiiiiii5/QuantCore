import { useEffect, useState } from "react";
import { useDataStatus, useHealth, useJobs, useLiveStatus, useMeta } from "../api/queries";
import { getApiBase } from "../api/client";
import { dateInt } from "../lib/format";
import { liveSummary, liveTone } from "../lib/live";
import { zhCN as t } from "../i18n/zh-CN";

const DOT_CLASS: Record<string, string> = { live: "dot live", closed: "dot closed", offline: "dot offline", error: "dot error" };

/** 28px glass status bar: live source · snapshot · engine · jobs · disclaimer. */
export default function StatusBar() {
  const health = useHealth();
  const meta = useMeta();
  const data = useDataStatus();
  const live = useLiveStatus();
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
  const source = snapshot
    ? (snapshot.synthetic ? "SYNTHETIC" : snapshot.source && snapshot.source !== "unknown" ? snapshot.source : "本地快照")
    : meta.data?.synthetic_only ? "SYNTHETIC" : "—";
  const job = running.data?.[0];
  const connected = !health.isError && !meta.isError && online;
  const tone = liveTone(live.data);
  const liveText = live.data?.enabled
    ? liveSummary(live.data, snapshot ? dateInt(snapshot.end) : null)
    : t.status.offline;

  return (
    <footer className={connected ? "statusbar" : "statusbar offline"} aria-label="工作区状态">
      <span className="statusbar-item">
        <span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />
        {liveText}
      </span>
      <span className="statusbar-item">{t.status.source}: <strong>{source}</strong></span>
      <span className="statusbar-item optional">{t.status.dataDate}: <strong>{snapshot ? dateInt(snapshot.end) : "—"}</strong></span>
      <span className="statusbar-item optional">{t.status.engine}: <strong>{connected ? (health.data?.engine_backend ?? meta.data?.engine_backend ?? "…") : t.status.disconnected}</strong></span>
      <span className="statusbar-item optional">{t.status.task}: <strong>{job ? `${job.kind} ${Math.round(job.progress * 100)}%` : t.status.idle}</strong></span>
      <span className="statusbar-spacer" />
      <span className="statusbar-item optional mono">{getApiBase() || t.status.sameOrigin}</span>
      <span className="statusbar-item disclaimer" title={t.disclaimer}>{t.status.disclaimer}</span>
    </footer>
  );
}
