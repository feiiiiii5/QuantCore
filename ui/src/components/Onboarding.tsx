import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles } from "lucide-react";
import { useBootstrap, useSubmitBacktest } from "../api/queries";
import { useJobProgress } from "../hooks/useJobProgress";
import StepList from "./StepList";
import { zhCN as t } from "../i18n/zh-CN";

const TEMPLATES = [
  { id: "momentum", label: "动量（20/60 日）" },
  { id: "dual_ma", label: "双均线" },
  { id: "low_vol", label: "低波动" },
  { id: "multi_factor", label: "多因子" },
];

/** Optional two-step onboarding dialog: bootstrap synthetic data → run a sample backtest. */
export default function Onboarding({ onDone, onClose }: { onDone: (runId: string) => void; onClose: () => void }) {
  const bootstrap = useBootstrap();
  const submit = useSubmitBacktest();
  const [step, setStep] = useState(0);
  const [snapshot, setSnapshot] = useState("");
  const [bootstrapRunId, setBootstrapRunId] = useState("");
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
    setMessage(t.onboarding.done);
    onDone(runId);
  }, [progress.job, onDone]);

  const generate = async () => {
    setError(""); setMessage("");
    try {
      const result = await bootstrap.mutateAsync({ n_sec: 40, start: "2022-01-04", end: "2024-12-31", seed: 42 });
      const id = typeof result.snapshot === "string" ? result.snapshot : "";
      if (!id) { setError("bootstrap 未返回 snapshot；请检查 /api/onboarding/bootstrap。"); return; }
      const runId = typeof result.run_id === "string" ? result.run_id : "";
      setSnapshot(id);
      setBootstrapRunId(runId);
      setMessage(runId ? `快照 ${id} 已生成（附带示例 ${runId}）` : `快照 ${id} 已生成`);
      setStep(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "bootstrap 失败");
    }
  };

  const run = () => {
    setError("");
    submit.mutate(
      { template, params: {}, snapshot, config: { start: "2022-01-04", end: "2024-12-31", initial_cash: 1_000_000 } },
      {
        onSuccess: (response) => setJobId(response.job_id),
        onError: (reason) => setError(reason.message),
      },
    );
  };

  const busy = bootstrap.isPending || submit.isPending || Boolean(jobId && progress.job?.status === "running");
  const steps = [
    { id: "bootstrap", title: t.onboarding.step1, description: t.onboarding.step1Hint, done: Boolean(snapshot), active: step === 0 },
    { id: "run", title: t.onboarding.step2, description: t.onboarding.step2Hint, done: false, active: step === 1 },
  ];

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <div className="modal">
        <div className="modal-head">
          <h2 id="onboarding-title">
            {t.onboarding.title} <span className="muted small">第 {Math.min(step + 1, 2)} / 2 步</span>
          </h2>
          <button className="btn ghost sm" onClick={onClose} disabled={busy}>{t.onboarding.close}</button>
        </div>
        <p className="muted small" style={{ marginBottom: "var(--sp-3)" }}>{t.onboarding.subtitle}</p>
        <StepList steps={steps} compact />
        <div style={{ marginTop: "var(--sp-4)" }}>
          {step === 0 ? (
            <button className="btn primary" onClick={() => void generate()} disabled={busy}>
              <Sparkles size={15} /> {bootstrap.isPending ? t.onboarding.generating : t.onboarding.generate}
            </button>
          ) : null}
          {step === 1 ? (
            <div className="stack tight">
              <label className="field-label">
                {t.onboarding.sample}
                <select value={template} onChange={(event) => setTemplate(event.target.value)} disabled={busy || Boolean(bootstrapRunId)}>
                  {TEMPLATES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <p className="muted small">{t.onboarding.snapshot}：<span className="mono">{snapshot || "—"}</span></p>
              <div className="button-row">
                <button className="btn" onClick={() => setStep(0)} disabled={busy}>{t.onboarding.back}</button>
                {bootstrapRunId ? (
                  <button className="btn primary" onClick={() => onDone(bootstrapRunId)}>
                    <Check size={15} /> {t.onboarding.openExperiment}
                  </button>
                ) : (
                  <button className="btn primary" onClick={run} disabled={busy || !snapshot}>
                    {jobId && progress.job?.status !== "failed" ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}
                    {jobId ? `${progress.job?.status ?? "pending"} ${Math.round((progress.job?.progress ?? 0) * 100)}%` : t.onboarding.run}
                  </button>
                )}
              </div>
              {progress.job ? (
                <div className="progress">
                  <div className="progress-bar" style={{ width: `${Math.round(progress.job.progress * 100)}%` }} />
                  <span>{progress.job.status}</span>
                </div>
              ) : null}
              {progress.job?.status === "done" ? <p className="success-text"><Check size={14} /> {t.onboarding.done}</p> : null}
            </div>
          ) : null}
        </div>
        {message ? <p className="success-text" style={{ marginTop: "var(--sp-2)" }}>{message}</p> : null}
        {error ? <p className="error" role="alert" style={{ marginTop: "var(--sp-2)" }}>{error}</p> : null}
        <p className="muted small" style={{ marginTop: "var(--sp-3)" }}>{t.onboarding.disclaimer} {t.disclaimer}</p>
      </div>
    </div>
  );
}
