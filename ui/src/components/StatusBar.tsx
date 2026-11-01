import { useEffect, useState } from "react";
import { api, getApiBase } from "../api/client";
import type { Meta } from "../api/types";
import { zhCN as t } from "../i18n/zh-CN";

export default function StatusBar() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api.meta().then(setMeta).catch(() => setFailed(true));
  }, []);
  return (
    <footer className="statusbar">
      <span>{t.status.dataDate}: {meta?.synthetic_only ? "SYNTHETIC" : "—"}</span>
      <span>{t.status.source}: {meta?.synthetic_only ? "合成/本地" : "本地快照"}</span>
      <span>{t.status.task}: idle</span>
      <span className={failed ? "error" : ""}>{t.status.network}: {meta ? `${meta.engine_backend} · v${meta.version}` : failed ? t.status.disconnected : "…"}</span>
      <span className="statusbar-spacer">{getApiBase() || "same-origin"}</span>
    </footer>
  );
}
