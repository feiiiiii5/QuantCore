import { useCallback, useEffect, useRef, useState } from "react";
import { Database, HardDrive, RefreshCw, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { DataStatus, Job } from "../api/types";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

function humanBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(1)} KB`;
  return `${bytes} B`;
}

export default function DataPage() {
  const [data, setData] = useState<DataStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);
  const navigate = useNavigate();

  const stop = () => { if (timer.current !== null) { window.clearInterval(timer.current); timer.current = null; } };
  useEffect(() => stop, []);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await api.dataStatus()); } catch (e) { setError(`${e}`); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const poll = (jobId: string, next?: () => void) => {
    stop(); setBusy(true);
    timer.current = window.setInterval(async () => {
      try {
        const current = await api.job(jobId); setJob(current);
        if (current.status === "done") { stop(); setBusy(false); await load(); next?.(); }
        else if (current.status === "failed" || current.status === "cancelled") { stop(); setBusy(false); setError(current.error || current.status); }
      } catch (e) { stop(); setBusy(false); setError(`${e}`); }
    }, 500);
  };
  const bootstrap = async () => {
    setBusy(true); setError("");
    try {
      const result = await api.bootstrap({ n_sec: 40, start: "2022-01-04", end: "2024-12-31", seed: 42 });
      await load();
      const runId = String(result.run_id || "");
      if (runId) navigate(`/experiments?run=${encodeURIComponent(runId)}`);
    } catch (e) { setError(`${e}`); } finally { setBusy(false); }
  };
  const update = async () => {
    setBusy(true); setError("");
    try {
      stop();
      const payload = { provider: "synthetic", start: "2022-01-04", end: "2024-12-31", n_sec: 40, seed: 42 };
      const first = await api.updateData(payload);
      setJob({ id: first.job_id, kind: "data_update", status: "pending", progress: 0, created_at: "", started_at: null, finished_at: null, error: null, result: null });
      timer.current = window.setInterval(async () => {
        const current = await api.job(first.job_id); setJob(current);
        if (current.status === "done") {
          stop();
          const snapJob = await api.buildSnapshot();
          setJob({ id: snapJob.job_id, kind: "snapshot_build", status: "pending", progress: 0, created_at: "", started_at: null, finished_at: null, error: null, result: null });
          poll(snapJob.job_id);
        } else if (current.status === "failed" || current.status === "cancelled") { stop(); setBusy(false); setError(current.error || current.status); }
      }, 500);
    } catch (e) { setBusy(false); setError(`${e}`); }
  };

  return (
    <>
      <div className="page-head"><div><h1>数据</h1><p>数据源 · 快照 · 质量 · 存储 · 备份</p></div><div className="button-row"><button className="btn" onClick={() => void load()}><RefreshCw size={15} /> 刷新</button><button className="btn" disabled={busy} onClick={() => void update()}>增量更新 + 构建快照</button><button className="btn primary" disabled={busy} onClick={() => void bootstrap()}><Sparkles size={15} /> 一键示例</button></div></div>
      {loading ? <StatePanel loading /> : error && !data ? <StatePanel error={error} onRetry={() => void load()} /> : null}
      {data ? (
        <>
          <div className="grid kpis">
            <div className="card"><h3><Database size={14} /> 数据仓库</h3><div className="kpi">{Object.values(data.warehouse.datasets).reduce((a, b) => a + b, 0).toLocaleString()}</div><small>行 · {humanBytes(data.warehouse.bytes)}</small></div>
            <div className="card"><h3>快照</h3><div className="kpi">{data.snapshots.length}</div><small>{humanBytes(data.storage.snapshot_bytes)}</small></div>
            <div className="card"><h3>实验</h3><div className="kpi">{humanBytes(data.storage.experiments_bytes)}</div><small>本地实验产物</small></div>
            <div className="card"><h3><HardDrive size={14} /> 可用空间</h3><div className="kpi">{humanBytes(data.storage.free_bytes)}</div><small>{data.data_root}</small></div>
          </div>
          {job ? <div className="card progress-card"><span>{job.kind} · {job.status}</span><div className="progress"><div className="progress-bar" style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /><span>{Math.round((job.progress || 0) * 100)}%</span></div></div> : null}
          {error ? <p className="error">{error}</p> : null}
          <div className="grid two-col" style={{ marginTop: 14 }}>
            <div className="card"><h3>快照</h3>{data.snapshots.length ? <div className="table-wrap"><table><thead><tr><th>ID</th><th>证券</th><th>交易日</th><th>质量</th><th>类型</th></tr></thead><tbody>{data.snapshots.map((snap) => <tr key={snap.id}><td className="mono">{snap.id.slice(0, 18)}…</td><td>{snap.n_sec}</td><td>{snap.n_time}</td><td>{String((snap.quality as { passed?: boolean }).passed ?? "—")}</td><td>{snap.synthetic ? "SYNTHETIC" : snap.source}</td></tr>)}</tbody></table></div> : <StatePanel empty emptyHint="还没有快照。点击“一键示例”或“增量更新”。" />}</div>
            <div className="card"><h3>数据源</h3><div className="provider-list">{data.providers.map((provider) => <div key={String(provider.name)} className="provider-row"><strong>{String(provider.name)}</strong><span className="muted small">{provider.requires_token ? "需要 Token" : provider.requires_network ? "需要网络" : "本地/公开"}{provider.available === false ? " · 不可用" : ""}</span></div>)}</div></div>
          </div>
          <p className="muted small">{t.disclaimer}</p>
        </>
      ) : null}
    </>
  );
}
