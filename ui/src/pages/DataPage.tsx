import { useEffect, useRef, useState } from "react";
import { Copy, Database, HardDrive, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useBuildSnapshot, useDataStatus, useQuality, useUpdateData } from "../api/queries";
import type { SnapshotStatus } from "../api/types";
import StatePanel from "../components/StatePanel";
import Onboarding from "../components/Onboarding";
import { useJobProgress } from "../hooks/useJobProgress";
import { bytes, dateInt, num } from "../lib/format";
import { zhCN as t } from "../i18n/zh-CN";

interface DataJob { id: string; kind: "data_update" | "snapshot_build" }

export default function DataPage() {
  const status = useDataStatus();
  const update = useUpdateData();
  const snapshot = useBuildSnapshot();
  const navigate = useNavigate();
  const [job, setJob] = useState<DataJob | null>(null);
  const [qualitySnapshot, setQualitySnapshot] = useState<string | null>(null);
  const [quality, setQuality] = useState<import("../api/types").QualityReport | null>(null);
  const qualityQuery = useQuality(qualitySnapshot);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [wizard, setWizard] = useState(false);
  const [provider, setProvider] = useState("synthetic");
  const [start, setStart] = useState("2022-01-04");
  const [end, setEnd] = useState("2024-12-31");
  const [nSec, setNSec] = useState("40");
  const [localDir, setLocalDir] = useState("");
  const chainSnapshot = useRef(false);
  const handled = useRef<string>("");
  const progress = useJobProgress(job?.id ?? null);

  useEffect(() => {
    if (!progress.job || !job || handled.current === `${job.id}:${progress.job.status}`) return;
    handled.current = `${job.id}:${progress.job.status}`;
    if (progress.job.status === "done") {
      if (job.kind === "data_update" && chainSnapshot.current) {
        chainSnapshot.current = false;
        snapshot.mutate(undefined, {
          onSuccess: (response) => setJob({ id: response.job_id, kind: "snapshot_build" }),
          onError: (reason) => { setError(reason.message); setJob(null); },
        });
      } else {
        setNotice(job.kind === "snapshot_build" ? "快照构建完成" : "数据更新完成");
        void status.refetch();
        setJob(null);
      }
    } else if (progress.job.status === "failed" || progress.job.status === "cancelled") {
      setError(progress.job.error || (progress.job.status === "cancelled" ? "任务已取消" : "任务失败"));
      setJob(null);
    }
  }, [progress.job, job, snapshot, status]);
  useEffect(() => { if (qualityQuery.data) setQuality(qualityQuery.data); }, [qualityQuery.data]);

  const copy = async (text: string, label: string) => {
    try { await navigator.clipboard.writeText(text); setNotice(`已复制${label}：${text}`); }
    catch { setNotice(`${label}：${text}（浏览器拒绝剪贴板，可手动复制）`); }
  };
  const startUpdate = () => {
    setError(""); setNotice(""); chainSnapshot.current = true;
    const payload: Record<string, unknown> = { provider, start, end, n_sec: Number(nSec) || 40, seed: 42 };
    if (provider === "local" && localDir.trim()) payload.local_dir = localDir.trim();
    update.mutate(payload, {
      onSuccess: (response) => setJob({ id: response.job_id, kind: "data_update" }),
      onError: (reason) => { chainSnapshot.current = false; setError(reason.message); },
    });
  };
  const startSnapshot = () => {
    setError(""); setNotice("");
    snapshot.mutate(undefined, {
      onSuccess: (response) => setJob({ id: response.job_id, kind: "snapshot_build" }),
      onError: (reason) => { setError(reason.message); setJob(null); },
    });
  };
  const data = status.data;
  const busy = Boolean(job) || update.isPending || snapshot.isPending;

  return (
    <>
      <div className="page-head"><div><h1>数据</h1><p>数据源 · 快照 · 质量 · 存储 · 导入导出路径 · 首次向导</p></div><div className="button-row">
        <button className="btn" onClick={() => void status.refetch()} disabled={status.isFetching}><RefreshCw size={15} /> 刷新</button>
        <button className="btn" onClick={() => setWizard(true)}><Sparkles size={15} /> 首次向导</button>
        <button className="btn" onClick={startUpdate} disabled={busy}>更新 + 构建快照</button>
        <button className="btn primary" onClick={startSnapshot} disabled={busy}>构建快照</button>
      </div></div>
      {status.isLoading ? <StatePanel loading /> : status.error ? <StatePanel error={status.error.message} onRetry={() => void status.refetch()} /> : data ? (
        <>
          <div className="grid kpis">
            <div className="card"><h3><Database size={14} /> 数据仓库</h3><div className="kpi">{data.warehouse.rows.toLocaleString("zh-CN")}</div><small>行 · {bytes(data.warehouse.bytes)}</small></div>
            <div className="card"><h3>快照</h3><div className="kpi">{data.snapshots.length}</div><small>{bytes(data.storage.snapshot_bytes)}</small></div>
            <div className="card"><h3>实验产物</h3><div className="kpi">{bytes(data.storage.experiments_bytes)}</div><small>experiments/</small></div>
            <div className="card"><h3><HardDrive size={14} /> 可用空间</h3><div className="kpi">{bytes(data.storage.free_bytes)}</div><small className="truncate" title={data.data_root}>{data.data_root}</small></div>
          </div>
          {job ? <div className="card progress-card"><span>{job.kind === "data_update" ? "数据更新" : "快照构建"} · {progress.job?.status ?? "排队"} · {progress.transport ?? "等待"}</span><div className="progress"><div className="progress-bar" style={{ width: `${Math.round((progress.job?.progress ?? 0) * 100)}%` }} /><span>{Math.round((progress.job?.progress ?? 0) * 100)}%</span></div><button className="btn ghost" onClick={() => { setJob(null); setNotice("已隐藏任务进度，后台任务仍可继续。"); }}>隐藏</button></div> : null}
          {error ? <p className="error">{error}</p> : null}
          {notice ? <p className="success-text">{notice}</p> : null}
          <div className="card" style={{ marginTop: 14 }}>
            <h3>更新数据</h3>
            <div className="form-grid">
              <label>数据源<select value={provider} onChange={(event) => setProvider(event.target.value)}>{(data.providers.length ? data.providers : [{ id: "synthetic", name: "Synthetic", available: true, requires_network: false, requires_token: false, capabilities: {} }]).map((item) => <option key={item.id} value={item.id} disabled={!item.available}>{item.name}{item.available ? "" : "（不可用）"}</option>)}</select></label>
              <label>开始<input value={start} onChange={(event) => setStart(event.target.value)} placeholder="YYYY-MM-DD" /></label>
              <label>结束<input value={end} onChange={(event) => setEnd(event.target.value)} placeholder="YYYY-MM-DD" /></label>
              <label>证券数（synthetic）<input value={nSec} onChange={(event) => setNSec(event.target.value)} inputMode="numeric" /></label>
              {provider === "local" ? <label>本地目录<input value={localDir} onChange={(event) => setLocalDir(event.target.value)} placeholder="/path/to/data" /></label> : null}
            </div>
            <div className="button-row"><button className="btn primary" onClick={startUpdate} disabled={busy}>更新并构建快照</button><button className="btn" onClick={startSnapshot} disabled={busy}>仅构建快照</button><span className="muted small">provider 需已配置 Token/本地目录；失败会显示 job 错误，不阻塞其他页面。</span></div>
          </div>
          <div className="grid two-col" style={{ marginTop: 14 }}>
            <div className="card">
              <div className="card-head"><h3>快照</h3><span className="muted small">点击行查看质量</span></div>
              {data.snapshots.length ? <div className="table-wrap"><table><thead><tr><th>ID</th><th>证券</th><th>交易日</th><th>区间</th><th>质量</th><th>类型</th></tr></thead><tbody>{data.snapshots.map((snap: SnapshotStatus) => <tr key={snap.id} className={qualitySnapshot === snap.id ? "selected" : ""} onClick={() => setQualitySnapshot(snap.id)}><td className="mono truncate" title={snap.id}>{snap.id}</td><td>{snap.n_sec}</td><td>{snap.n_time}</td><td>{dateInt(snap.start)} – {dateInt(snap.end)}</td><td>{String((snap.quality as { passed?: boolean }).passed ?? "—")}</td><td>{snap.synthetic ? "SYNTHETIC" : snap.source}</td></tr>)}</tbody></table></div> : <StatePanel empty emptyHint="还没有快照。使用“首次向导”或“更新 + 构建快照”。" />}
              <div className="inline-actions"><button className="btn" onClick={() => void copy(data.data_root, "数据目录")}><Copy size={14} /> 复制数据路径</button><button className="btn" onClick={() => void copy(`${data.data_root}/snapshots`, "快照目录")}><Copy size={14} /> 复制快照路径</button><button className="btn" onClick={() => setNotice("导入：将 Parquet/LocalFile 放入数据目录后运行数据更新；导出：快照目录可直接复制备份。")}>导入/导出提示</button></div>
              {qualitySnapshot ? <div className="quality-panel"><div className="card-head"><h3>质量报告 <span className="mono small">{qualitySnapshot}</span></h3><button className="btn ghost" onClick={() => setQualitySnapshot(null)}>关闭</button></div>{qualityQuery.isLoading ? <StatePanel loading /> : qualityQuery.error ? <p className="error">{qualityQuery.error.message}</p> : <pre className="validation">{JSON.stringify(quality?.report ?? quality?.quality ?? {}, null, 2)}</pre>}</div> : null}
            </div>
            <div className="card"><h3>数据源</h3><div className="provider-list">{data.providers.map((provider) => <div key={provider.id} className="provider-row"><div><strong>{provider.name}</strong><small className="muted">{provider.requires_token ? "需要 Token" : provider.requires_network ? "需要网络" : "本地/公开"}</small></div><span className={provider.available ? "badge success" : "badge"}>{provider.available ? "可用" : "不可用"}</span></div>)}</div><p className="muted small">凭据只从本地环境/系统钥匙串读取；UI 不发起真实网络请求，也不记录 Token。</p></div>
          </div>
          <div className="card" style={{ marginTop: 14 }}><h3><ShieldCheck size={14} /> 质量与存储</h3><div className="metric-inline"><span>行数 <strong>{num(data.warehouse.rows, 0)}</strong></span><span>数据集 <strong>{Object.keys(data.warehouse.datasets).length}</strong></span><span>manifest <strong className="mono">{data.warehouse.manifest_hash.slice(0, 16)}…</strong></span><span>快照字节 <strong>{bytes(data.storage.snapshot_bytes)}</strong></span></div><p className="muted small">合成数据标 SYNTHETIC；规则/费率 TODO(verify)。质量报告按快照选择查看。</p></div>
        </>
      ) : <StatePanel empty emptyHint="本地服务已连接，但还没有数据状态。先运行首次向导。" />}
      {wizard ? <Onboarding onDone={(runId) => { setWizard(false); navigate(`/experiments?run=${encodeURIComponent(runId)}`); }} onClose={() => setWizard(false)} /> : null}
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
