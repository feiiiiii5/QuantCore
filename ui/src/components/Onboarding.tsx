import { useState } from "react";
import { api } from "../api/client";
import { zhCN as t } from "../i18n/zh-CN";

export default function Onboarding({ onDone, onClose }: { onDone: (runId: string) => void; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState("");
  const boot = async () => {
    setBusy(true); setError("");
    try {
      const result = await api.bootstrap({ n_sec: 40, start: "2022-01-04", end: "2024-12-31", seed: 42 });
      const id = String(result.run_id || "");
      setRunId(id); setStep(2); onDone(id);
    } catch (e) { setError(`${e}`); } finally { setBusy(false); }
  };
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal card">
        <div className="modal-head"><h2>三步开始</h2><button className="btn ghost" onClick={onClose}>关闭</button></div>
        <ol className="steps">
          <li className={step >= 0 ? "active" : ""}>生成 SYNTHETIC 示例数据与不可变快照</li>
          <li className={step >= 1 ? "active" : ""}>跑一次示例策略回测（C++ 引擎）</li>
          <li className={step >= 2 ? "active" : ""}>打开实验，查看净值、交易与报告</li>
        </ol>
        {error ? <p className="error">{error}</p> : null}
        {step === 0 ? <button className="btn primary" disabled={busy} onClick={() => { setStep(1); void boot(); }}>{busy ? "正在生成…" : "生成示例数据并回测"}</button> : null}
        {busy ? <p className="muted">正在构建快照并运行回测，通常需要数秒…</p> : null}
        {step === 2 ? <p className="success-text">完成：{runId}</p> : null}
        <p className="muted small">{t.disclaimer}</p>
      </div>
    </div>
  );
}
