import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles } from "lucide-react";
import { useBootstrap, useSubmitBacktest } from "../api/queries";
import { useJobProgress } from "../hooks/useJobProgress";
import Dialog from "./Dialog";
import Button from "./Button";
import Select from "./Select";
import ProgressBar from "./ProgressBar";
import StepList from "./StepList";
import { zhCN as t } from "../i18n/zh-CN";

const TEMPLATES = [
  { id: "momentum", label: "动量（20/60 日）" },
  { id: "dual_ma", label: "双均线" },
  { id: "low_vol", label: "低波动" },
  { id: "multi_factor", label: "多因子" },
];

/** Two-step onboarding dialog: bootstrap synthetic data then run a sample backtest. */
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
      { onSuccess: (response) => setJobId(response.job_id), onError: (reason) => setError(reason.message) },
    );
  };

  const busy = bootstrap.isPending || submit.isPending || Boolean(jobId && progress.job?.status === "running");
  const steps = [
    { id: "bootstrap", title: t.onboarding.step1, description: t.onboarding.step1Hint, done: Boolean(snapshot), active: step === 0 },
    { id: "run", title: t.onboarding.step2, description: t.onboarding.step2Hint, done: false, active: step === 1 },
  ];

  return (
    <Dialog
      open
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={<>{t.onboarding.title} <span className="caption text-3">第 {Math.min(step + 1, 2)} / 2 步</span></>}
      description={t.onboarding.subtitle}
      footer={<span className="caption2 text-3">{t.onboarding.disclaimer} {t.disclaimer}</span>}
    >
      <StepList steps={steps} compact />
      <div style={{ marginTop: "var(--sp-6)" }}>
        {step === 0 ? (
          <Button variant="primary" icon={Sparkles} loading={bootstrap.isPending} onClick={() => void generate()}>
            {bootstrap.isPending ? t.onboarding.generating : t.onboarding.generate}
          </Button>
        ) : null}
        {step === 1 ? (
          <div className="stack stack-tight">
            <Select
              aria-label={t.onboarding.sample}
              value={template}
              onChange={(event) => setTemplate(event.target.value)}
              disabled={busy || Boolean(bootstrapRunId)}
              options={TEMPLATES.map((item) => ({ value: item.id, label: item.label }))}
            />
            <p className="caption text-3">{t.onboarding.snapshot}：<span className="mono">{snapshot || "—"}</span></p>
            <div className="row">
              <Button variant="secondary" size="sm" onClick={() => setStep(0)} disabled={busy}>{t.onboarding.back}</Button>
              {bootstrapRunId ? (
                <Button variant="primary" icon={Check} onClick={() => onDone(bootstrapRunId)}>{t.onboarding.openExperiment}</Button>
              ) : (
                <Button variant="primary" loading={Boolean(jobId && progress.job?.status !== "failed")} onClick={run} disabled={busy || !snapshot} icon={Sparkles}>
                  {jobId ? `${progress.job?.status ?? "pending"} ${Math.round((progress.job?.progress ?? 0) * 100)}%` : t.onboarding.run}
                </Button>
              )}
            </div>
            {jobId ? <ProgressBar value={Math.round((progress.job?.progress ?? 0) * 100)} label={progress.job?.status ?? "pending"} /> : null}
            {progress.job?.status === "done" ? <p className="success-text"><Check size={14} /> {t.onboarding.done}</p> : null}
            {jobId && progress.job?.status !== "done" ? <Loader2 className="spin" size={14} aria-hidden="true" /> : null}
          </div>
        ) : null}
      </div>
      {message ? <p className="success-text" style={{ marginTop: "var(--sp-4)" }}>{message}</p> : null}
      {error ? <p className="error-text" role="alert" style={{ marginTop: "var(--sp-4)" }}>{error}</p> : null}
    </Dialog>
  );
}
