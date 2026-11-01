import { useState } from "react";
import { CheckCircle2, PlugZap } from "lucide-react";
import { api, configure, getApiBase, getToken } from "../api/client";
import { zhCN as t } from "../i18n/zh-CN";

export default function SettingsPage() {
  const [base, setBase] = useState(getApiBase());
  const [token, setToken] = useState(getToken());
  const [theme, setTheme] = useState(localStorage.getItem("qc_theme") || "light");
  const [density, setDensity] = useState(localStorage.getItem("qc_density") || "comfortable");
  const [colorMode, setColorMode] = useState(localStorage.getItem("qc_color_mode") || "red-up");
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState("");
  const save = () => {
    configure(base, token);
    localStorage.setItem("qc_theme", theme); localStorage.setItem("qc_density", density); localStorage.setItem("qc_color_mode", colorMode);
    setSaved(true); window.dispatchEvent(new Event("qc-settings"));
  };
  const check = async () => {
    setTest("测试中…");
    try { const health = await api.health(); setTest(`已连接：${health.engine_backend} · v${health.version}`); } catch (e) { setTest(`连接失败：${e}`); }
  };
  return (
    <>
      <div className="page-head"><div><h1>设置</h1><p>本地服务地址 · Bearer Token · 主题/密度 · 风格</p></div></div>
      <div className="card settings-card">
        <h3>本地服务</h3>
        <div className="form-grid">
          <label>API 地址<input value={base} onChange={(e) => setBase(e.target.value)} placeholder="留空表示同源（qc serve 托管 UI）" /></label>
          <label>Bearer Token<input value={token} onChange={(e) => setToken(e.target.value)} type="password" autoComplete="off" /></label>
        </div>
        <div className="button-row"><button className="btn" onClick={() => void check()}><PlugZap size={15} /> 测试连接</button>{test ? <span className={test.startsWith("已连接") ? "success-text" : "error"}>{test}</span> : null}</div>
        <p className="muted small">Token 由 `qc serve` 启动时打印；只保存在本机浏览器 localStorage。</p>
        <h3 style={{ marginTop: 20 }}>外观</h3>
        <div className="form-grid">
          <label>主题<select value={theme} onChange={(e) => setTheme(e.target.value)}><option value="light">浅色</option><option value="dark">深色</option></select></label>
          <label>密度<select value={density} onChange={(e) => setDensity(e.target.value)}><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
          <label>涨跌颜色<select value={colorMode} onChange={(e) => setColorMode(e.target.value)}><option value="red-up">红涨绿跌</option><option value="green-up">绿涨红跌</option><option value="color-blind">色盲友好</option></select></label>
        </div>
        <button className="btn primary" onClick={save}>保存</button>{saved ? <span className="success-text" style={{ marginLeft: 12 }}><CheckCircle2 size={14} /> 已保存</span> : null}
        <p className="muted small" style={{ marginTop: 18 }}>{t.disclaimer}</p>
      </div>
    </>
  );
}
