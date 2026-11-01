import { useState } from "react";
import { configure, getApiBase, getToken } from "../api/client";
export default function SettingsPage() {
  const [base, setBase] = useState(getApiBase());
  const [token, setToken] = useState(getToken());
  const [saved, setSaved] = useState(false);
  return (
    <>
      <div className="page-head"><div><h1>设置</h1><p>本地服务地址 · Bearer Token · 主题/密度 · 风格</p></div></div>
      <div className="card" style={{ maxWidth: 620 }}>
        <div className="form-row"><label>API 地址</label><input value={base} onChange={(e) => setBase(e.target.value)} /></div>
        <div className="form-row"><label>Bearer Token</label><input value={token} onChange={(e) => setToken(e.target.value)} type="password" /></div>
        <button className="btn primary" onClick={() => { configure(base, token); setSaved(true); }}>保存</button>
        {saved ? <span style={{ marginLeft: 12, color: "var(--muted)" }}>已保存到本机浏览器</span> : null}
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 16 }}>Token 由 `qc serve` 启动时打印；只保存在本机浏览器 localStorage。</p>
      </div>
    </>
  );
}
