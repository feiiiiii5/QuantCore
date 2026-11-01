import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Loader2, Sparkles } from "lucide-react";
import { useBootstrap, useSubmitBacktest } from "../api/queries";
import { useJobProgress } from "../hooks/useJobProgress";
import { zhCN as t } from "../i18n/zh-CN";

const TEMPLATES = [
  { id: "momentum", label: "动量（20/60 日）" },
  { id: "dual_ma", label: "双均线" },
  { id: "low_vol", label: "低波动" },
  { id: "multi_factor", label: "多因子" },
];

export default function Onboarding({ onDone, onClose }: { onDone: (runId: string) => void; onClose: () => void }) {
  const bootstrap = useBootstrap();
  const submit = useSubmitBacktest();
  const [step, setStep] = useState(0);
  const [snapshot, setSnapshot] = useState("");
  const [template, setTemplate] = useState("momentum");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const finished = useRef(false);
  const progress = useJobProgress(jobId);

  useEffect(() => {
    const job = progress.job;
    if (!job || job.status !== "done" || finished.current) return;
    const runId = typeof job.result?.run_id === "string" ? job.result.run_id : "";
    if (!runId) { setError("回测完成但没有实验 ID；请检查后端。"); return; }
    finished.current = true;
    setMessage(`示例回测完成：${runId}`);
    onDone(runId);
  }, [progress.job, onDone]);

  const generate = async () => {
    setError(""); setMessage("");
    try {
      const result = await bootstrap.mutateAsync({ n_sec: 40, start: "2022-01-04", end: "2024-12-31", seed: 42 });
      const id = typeof result.snapshot === "string" ? result.snapshot : "";
      setSnapshot(id);
      const runId = typeof result.run_id === "string" ? result.run_id : "";
      if (!id) { setError("bootstrap 未返回 snapshot；请检查 /api/onboarding/bootstrap。"); return; }
      setMessage(runId ? `快照 ${id} 已生成（bootstrap 附示例 ${runId}）` : `快照 ${id} 已生成`);
      setStep(1);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "bootstrap 失败"); }
  };
  const run = () => {
    setError("");
    submit.mutate({ template, params: {}, snapshot, config: { start: "2022-01-04", end: "2024-12-31", initial_cash: 1_000_000 } }, {
      onSuccess: (response) => setJobId(response.job_id),
      onError: (reason) => setError(reason.message),
    });
  };
  const busy = bootstrap.isPending || submit.isPending || Boolean(jobId && progress.job?.status === "running");

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <div className="modal card">
        <div className="modal-head"><h2 id="onboarding-title">三步开始 <span className="muted small">第 {Math.min(step + 1, 3)} / 3 步</span></h2><button className="btn ghost" onClick={onClose} disabled={busy}>关闭</button></div>
        <ol className="steps">
          <li className={step >= 0 ? "active" : ""}><strong>生成示例数据</strong><span className="muted">bootstrap：SYNTHETIC 面板 → 不可变快照（+ 示例回测）</span></li>
          <li className={step >= 1 ? "active" : ""}><strong>选择示例策略</strong><span className="muted">模板参数将由后端默认值校验</span></li>
          <li className={step >= 2 ? "active" : ""}><strong>运行并打开实验</strong><span className="muted">真实 POST /api/backtest，实验自动保存</span></li>
        </ol>
        {step === 0 ? <button className="btn primary" onClick={() => void generate()} disabled={busy}><Sparkles size={15} /> {bootstrap.isPending ? "生成中…" : "生成示例数据与快照"}</button> : null}
        {step === 1 ? (
          <>
            <label className="field-label">示例策略</label>
            <select value={template} onChange={(event) => setTemplate(event.target.value)}>{TEMPLATES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
            <p className="muted small">快照：<span className="mono">{snapshot || "—"}</span></p>
            <div className="button-row"><button className="btn" onClick={() => setStep(0)} disabled={busy}>上一步</button><button className="btn primary" onClick={() => setStep(2)}>下一步 <ArrowRight size={15} /></button></div>
          </>
        ) : null}
        {step === 2 ? (
          <>
            <p className="muted small">将用快照 <span className="mono">{snapshot || "—"}</span> 和策略 <strong>{template}</strong> 提交真实回测任务。</p>
            <div className="button-row"><button className="btn" onClick={() => setStep(1)} disabled={busy}>上一步</button><button className="btn primary" onClick={run} disabled={busy || !snapshot}>{jobId && progress.job?.status !== "failed" ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />} {jobId ? `${progress.job?.status ?? "pending"} ${Math.round((progress.job?.progress ?? 0) * 100)}%` : "运行示例回测"}</button></div>
            {progress.job ? <div className="progress"><div className="progress-bar" style={{ width: `${Math.round(progress.job.progress * 100)}%` }} /><span>{progress.job.status}</span></div> : null}
            {progress.job?.status === "done" ? <p className="success-text"><Check size={14} /> 完成，正在打开实验…</p> : null}
          </>
        ) : null}
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error" role="alert">{error}</p> : null}
        <p className="muted small">{t.disclaimer} 合成数据仅用于演示，不构成投资建议。</p>
      </div>
    </div>
  );
}
