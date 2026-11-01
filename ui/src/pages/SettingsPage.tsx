import { useState } from "react";
import { CheckCircle2, Database, PlugZap, ShieldCheck } from "lucide-react";
import { configure, getApiBase, getToken } from "../api/client";
import { useDataStatus, useHealth, useMeta } from "../api/queries";
import { dateInt } from "../lib/format";
import { ensureNotificationPermission } from "../lib/notify";
import { zhCN as t } from "../i18n/zh-CN";

export default function SettingsPage() {
  const [base, setBase] = useState(getApiBase());
  const [token, setToken] = useState(getToken());
  const [theme, setTheme] = useState(localStorage.getItem("qc_theme") || "light");
  const [density, setDensity] = useState(localStorage.getItem("qc_density") || "comfortable");
  const [colorMode, setColorMode] = useState(localStorage.getItem("qc_color_mode") || "red-up");
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState("");
  const [notifyState, setNotifyState] = useState<string>(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const health = useHealth();
  const meta = useMeta();
  const data = useDataStatus();

  const save = () => {
    configure(base, token);
    localStorage.setItem("qc_theme", theme);
    localStorage.setItem("qc_density", density);
    localStorage.setItem("qc_color_mode", colorMode);
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.colorMode = colorMode;
    setSaved(true);
    setTest("");
    window.dispatchEvent(new Event("qc-settings"));
    void health.refetch(); void meta.refetch(); void data.refetch();
  };
  const check = async () => {
    setTest("测试中…");
    try {
      const result = await health.refetch();
      if (result.error) throw result.error;
      setTest(`已连接：${result.data?.engine_backend ?? "?"} · v${result.data?.version ?? "?"}`);
    } catch (error) { setTest(`连接失败：${error instanceof Error ? error.message : "unknown"}`); }
  };

  return (
    <>
      <div className="page-head"><div><h1>设置</h1><p>本地服务地址 · Bearer Token · 主题/密度/涨跌色 · 数据源状态</p></div></div>
      <div className="grid settings-layout">
        <div className="card settings-card">
          <h3><PlugZap size={14} /> 本地服务</h3>
          <div className="form-grid">
            <label>API 地址<input value={base} onChange={(event) => setBase(event.target.value)} placeholder="留空 = 同源（qc serve 托管 UI）" autoComplete="off" spellCheck={false} /></label>
            <label>Bearer Token<input value={token} onChange={(event) => setToken(event.target.value)} type="password" autoComplete="new-password" spellCheck={false} /></label>
          </div>
          <div className="button-row"><button className="btn" onClick={() => void check()}><PlugZap size={15} /> 测试连接</button><button className="btn primary" onClick={save}>保存</button>{saved ? <span className="success-text"><CheckCircle2 size={14} /> 已保存（仅本机 localStorage）</span> : null}</div>
          {test ? <p className={test.startsWith("已连接") ? "success-text" : "error"}>{test}</p> : null}
          <p className="muted small">`qc serve --open` 的 `?token=` 会自动写入 localStorage 并从 URL 移除；Token 不进入日志、不发送到第三方。留空 API 地址时使用当前同源。</p>
          <h3 style={{ marginTop: 20 }}>外观</h3>
          <div className="form-grid">
            <label>主题<select value={theme} onChange={(event) => setTheme(event.target.value)}><option value="light">浅色</option><option value="dark">深色</option></select></label>
            <label>密度<select value={density} onChange={(event) => setDensity(event.target.value)}><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
            <label>涨跌颜色<select value={colorMode} onChange={(event) => setColorMode(event.target.value)}><option value="red-up">红涨绿跌</option><option value="green-up">绿涨红跌</option><option value="color-blind">色盲友好（蓝/橙）</option></select></label>
          </div>
          <p className="muted small">快捷键：⌘K / Ctrl-K 聚焦搜索；/ 聚焦搜索；Esc 关闭；Alt+1…8 切换页面。设置保存后即时生效。</p>
          <h3 style={{ marginTop: 20 }}>提醒</h3>
          <div className="button-row">
            <button className="btn" onClick={async () => setNotifyState(await ensureNotificationPermission())}>启用桌面提醒</button>
            <span className="muted small">当前：{notifyState === "granted" ? "已允许" : notifyState === "denied" ? "已拒绝/不支持" : notifyState}</span>
          </div>
          <p className="muted small">回测完成、模拟委托成交时显示本地 toast；仅在授予浏览器通知权限后发送系统通知，不联网。</p>
        </div>
        <div className="card">
          <h3><Database size={14} /> 服务与数据源状态</h3>
          <div className="provider-list">
            <div className="provider-row"><span>引擎</span><strong>{health.data?.engine_backend ?? (health.isError ? "未连接" : "…")}</strong></div>
            <div className="provider-row"><span>版本</span><strong>{health.data?.version ?? meta.data?.version ?? "—"}</strong></div>
            <div className="provider-row"><span>数据模式</span><strong>{meta.data?.synthetic_only ? "SYNTHETIC / 本地" : "本地快照"}</strong></div>
            <div className="provider-row"><span>数据根</span><strong className="mono truncate" title={meta.data?.data_root}>{meta.data?.data_root ?? "—"}</strong></div>
            <div className="provider-row"><span>最新快照</span><strong>{data.data?.snapshots[0] ? `${data.data.snapshots[0].id} · ${dateInt(data.data.snapshots[0].end)}` : "无"}</strong></div>
          </div>
          <h3 style={{ marginTop: 16 }}>数据源</h3>
          {(data.data?.providers ?? []).map((provider) => <div className="provider-row" key={provider.id}><div><strong>{provider.name}</strong><small className="muted">{provider.requires_token ? "需 Token" : provider.requires_network ? "需网络" : "本地"}</small></div><span className={provider.available ? "badge success" : "badge"}>{provider.available ? "可用" : "不可用"}</span></div>)}
          <p className="muted small"><ShieldCheck size={13} /> 仅研究与模拟，不包含真实下单；规则/费率 TODO(verify)。{t.disclaimer}</p>
        </div>
      </div>
    </>
  );
}
