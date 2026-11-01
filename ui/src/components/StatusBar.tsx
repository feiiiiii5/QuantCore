import { useEffect, useState } from "react";
import { api, getApiBase } from "../api/client";
import { zhCN as t } from "../i18n/zh-CN";

export default function StatusBar() {
  const [state, setState] = useState("—");
  useEffect(() => {
    api.health().then((h) => setState(`${h.engine_backend} · ${h.version}`)).catch(() => setState(t.status.disconnected));
  }, []);
  return (
    <footer className="statusbar">
      <span>{t.status.dataDate}: —</span>
      <span>{t.status.source}: local</span>
      <span>{t.status.task}: idle</span>
      <span>{t.status.network}: {state}</span>
      <span style={{ marginLeft: "auto" }}>{getApiBase()}</span>
    </footer>
  );
}
