import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Database, HardDrive, Network, RefreshCw, ShieldCheck, Sparkles, Upload, XCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  useBuildSnapshot, useCompleteOnboardingStep, useDataCatalog, useDataIntegrity, useDataStatus,
  useLiveStatus, useQuality, useUpdateData,
} from "../api/queries";
import { isApiError } from "../api/client";
import type { DataIntegrity, ProviderInfo, SnapshotStatus } from "../api/types";
import { Badge, EmptyState, Panel, Skeleton, StatTile } from "../components";
import Onboarding from "../components/Onboarding";
import { useJobProgress } from "../hooks/useJobProgress";
import { bytes, dateInt } from "../lib/format";
import { useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

interface DataJob { id: string; kind: "data_update" | "snapshot_build" }

function CheckIcon({ status }: { status: string }) {
  if (status === "pass") return <CheckCircle2 size={14} className="success-text" style={{ flex: "0 0 auto" }} />;
  if (status === "warn") return <AlertTriangle size={14} style={{ flex: "0 0 auto", color: "var(--warn, #d97706)" }} />;
  return <XCircle size={14} style={{ flex: "0 0 auto", color: "var(--danger, var(--up, #e5484d))" }} />;
}

function IntegrityPanel({ integrity, onRetry }: { integrity: ReturnType<typeof useDataIntegrity>; onRetry: () => void }) {
  if (integrity.isLoading) return <Panel title="数据体检" subtitle="覆盖率 / 缺口 / 准确性 / 跨源抽样"><Skeleton rows={4} /></Panel>;
  if (integrity.isError) {
    const notReady = isApiError(integrity.error) && integrity.error.status === 404;
    return (
      <Panel title="数据体检" subtitle="数据可信是回测可信的前提">
        <EmptyState title={notReady ? "数据体检后端未就绪" : "数据体检加载失败"} hint={notReady ? "GET /api/data/integrity 尚未上线；页面已降级显示，不影响导入与快照。升级后端后刷新即可。" : integrity.error.message} action={<button className="btn" onClick={onRetry}><RefreshCw size={15} /> 重试</button>} />
      </Panel>
    );
  }
  const data = integrity.data as DataIntegrity;
  const tone = data.status === "ok" ? "ok" as const : data.status === "warn" ? "warn" as const : "danger" as const;
  const accuracyRows = [
    { label: "OHLC 自洽", value: data.accuracy.ohlc_violations },
    { label: "量额一致", value: data.accuracy.volume_amount_mismatch },
    { label: "涨跌停校验", value: data.accuracy.limit_violations },
    { label: "复权连续性", value: data.accuracy.adjustment_breaks },
  ];
  return (
    <Panel title="数据体检" subtitle="覆盖率 / 缺口 / 准确性 / 跨源抽样；不通过时结果页会降级提示" actions={<button className="btn ghost" onClick={onRetry} disabled={integrity.isFetching}><RefreshCw size={14} /> 刷新</button>}>
      <div className="health-hero">
        <div className="health-hero-main">
          <Badge tone={tone} dot>{data.status === "ok" ? "体检通过" : data.status === "warn" ? "有警告" : "未通过"}</Badge>
          {data.snapshot ? <Badge tone="neutral">{data.snapshot.id.slice(0, 20)}{data.snapshot.synthetic ? " · SYNTHETIC" : ` · ${data.snapshot.source}`}</Badge> : <Badge tone="neutral">无快照</Badge>}
          <span className="muted small">生成于 {data.generated_at}</span>
        </div>
        <span className="muted small">只读检查，不联网、不修改数据。</span>
      </div>
      <div className="health-metrics">
        <div className="health-metric"><span>覆盖率</span><strong>{data.coverage.coverage_pct.toFixed(2)}%</strong><small>{data.coverage.present_cells.toLocaleString("zh-CN")} / {data.coverage.expected_cells.toLocaleString("zh-CN")} 个数据格</small></div>
        <div className="health-metric"><span>证券数</span><strong>{data.coverage.symbols}</strong><small>交易日 {data.coverage.trading_days}</small></div>
        <div className="health-metric"><span>缺口交易日</span><strong>{data.gaps.missing_days}</strong><small>{data.gaps.symbols_with_gaps} 只证券存在缺口</small></div>
        <div className="health-metric"><span>准确性异常</span><strong>{accuracyRows.reduce((sum, row) => sum + row.value, 0)}</strong><small>{accuracyRows.map((row) => `${row.label} ${row.value}`).join(" · ")}</small></div>
      </div>
      {data.checks.length ? (
        <div style={{ marginTop: 12 }}>
          <h3>体检项</h3>
          {data.checks.map((check) => (
            <div className="health-check" key={check.id}>
              <CheckIcon status={check.status} />
              <div className="health-check-body"><strong>{check.title}</strong><small>{check.detail}</small></div>
              <Badge tone={check.status === "pass" ? "ok" : check.status === "warn" ? "warn" : "danger"}>{check.status === "pass" ? "通过" : check.status === "warn" ? "警告" : "失败"}</Badge>
            </div>
          ))}
        </div>
      ) : null}
      {data.gaps.examples.length ? (
        <div style={{ marginTop: 10 }}>
          <h3>缺口 Top</h3>
          <div className="gap-chips">{data.gaps.examples.slice(0, 12).map((gap, index) => <span className="gap-chip" key={`${gap.code}-${gap.date}-${index}`}>{gap.code} {dateInt(gap.date)}</span>)}</div>
          <p className="muted small">修复建议：重新导入缺失区间或检查停牌/退市；缺口较多时不要直接相信回测结论。</p>
        </div>
      ) : null}
      <p className="muted small">跨源抽样：检查 {data.cross_source.checked} · 匹配 {data.cross_source.matched}{data.cross_source.max_rel_diff != null ? ` · 最大相对差 ${data.cross_source.max_rel_diff.toFixed(4)}` : ""}{data.cross_source.source ? ` · 对照源 ${data.cross_source.source}` : ""}。{data.cross_source.note}</p>
      <p className="muted small">{data.note}</p>
    </Panel>
  );
}

export default function DataPage() {
  const status = useDataStatus();
  const catalog = useDataCatalog();
  const integrity = useDataIntegrity();
  const live = useLiveStatus();
  const update = useUpdateData();
  const snapshot = useBuildSnapshot();
  const navigate = useNavigate();
  const beginner = useBeginner();
  const [job, setJob] = useState<DataJob | null>(null);
  const [qualitySnapshot, setQualitySnapshot] = useState<string | null>(null);
  const qualityQuery = useQuality(qualitySnapshot);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [wizard, setWizard] = useState(false);
  const [provider, setProvider] = useState("synthetic");
  const [start, setStart] = useState("2022-01-04");
  const [end, setEnd] = useState("2024-12-31");
  const [nSec, setNSec] = useState("40");
  const [localDir, setLocalDir] = useState("");
  const [codes, setCodes] = useState("");
  const [limit, setLimit] = useState("20");
  const chainSnapshot = useRef(false);
  const handled = useRef<string>("");
  const healthMarked = useRef(false);
  const progress = useJobProgress(job?.id ?? null);
  const completeStep = useCompleteOnboardingStep();

  // Onboarding step "data_health" is not auto-detected by the backend; mark it once
  // the integrity report loads (idempotent, failures are ignored).
  useEffect(() => {
    if (healthMarked.current || !integrity.data) return;
    healthMarked.current = true;
    completeStep.mutate("data_health", { onError: () => undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [integrity.data]);

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
        void integrity.refetch();
        setJob(null);
      }
    } else if (progress.job.status === "failed" || progress.job.status === "cancelled") {
      setError(progress.job.error || (progress.job.status === "cancelled" ? "任务已取消" : "任务失败"));
      setJob(null);
    }
  }, [progress.job, job, snapshot, status, integrity]);

  const copy = async (text: string, label: string) => {
    try { await navigator.clipboard.writeText(text); setNotice(`已复制${label}：${text}`); }
    catch { setNotice(`${label}：${text}（浏览器拒绝剪贴板，可手动复制）`); }
  };
  const startUpdate = (providerId = provider) => {
    setError(""); setNotice(""); chainSnapshot.current = true;
    const payload: Record<string, unknown> = { provider: providerId, start, end, incremental: true };
    if (providerId === "synthetic") {
      payload.n_sec = Number(nSec) || 40;
      payload.seed = 42;
    } else if (["sina", "eastmoney", "tushare"].includes(providerId)) {
      const list = codes.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean);
      if (list.length) payload.codes = list;
      else payload.limit = Number(limit) || 20;
    }
    if (providerId === "local" && localDir.trim()) payload.local_dir = localDir.trim();
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
  const providers: ProviderInfo[] = data?.providers ?? [];
  const findProvider = (ids: string[], names: string[]) => providers.find((item) => ids.includes(item.id) || names.some((name) => item.name.includes(name))) ?? null;
  const sina = findProvider(["sina"], ["新浪"]);
  const eastmoney = findProvider(["eastmoney", "east_money"], ["东方财富"]);
  const tushare = findProvider(["tushare"], ["Tushare", "tushare"]);
  const local = findProvider(["local"], ["本地"]);
  const networkOn = live.data?.enabled === true;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>数据</h1><p className="page-lead">先看数据体检，再导入真实数据；数据可信是回测可信的前提。</p></div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => void status.refetch()} disabled={status.isFetching}><RefreshCw size={15} /> 刷新</button>
          <button className="btn" onClick={() => setWizard(true)}><Sparkles size={15} /> 首次向导</button>
          <button className="btn primary" onClick={startSnapshot} disabled={busy}>构建快照</button>
        </div>
      </header>
      {status.isLoading ? <Skeleton rows={5} /> : status.error ? <EmptyState title="无法连接本地服务" hint={status.error.message} action={<button className="btn" onClick={() => void status.refetch()}>重试</button>} /> : data ? (
        <>
          <IntegrityPanel integrity={integrity} onRetry={() => void integrity.refetch()} />

          <Panel title="导入真实数据" subtitle="网络默认关闭；真实数据导入需在服务端显式开启（QC_ALLOW_NETWORK=1）" actions={<Badge tone={networkOn ? "ok" : "warn"} dot>{networkOn ? "网络已开启" : "网络默认关闭"}</Badge>}>
            <p className="muted small">开启方式：启动 <span className="mono">qc serve</span> 前设置环境变量 <span className="mono">QC_ALLOW_NETWORK=1</span> 并重启；测试永远用录制 fixture，不联网。未开启时页面不会发起任何外部请求。全市场导入约 30–45 分钟，建议先导几只试试；公开数据不得再分发，导入后先看「数据体检」通过再回测。<button className="link-btn" onClick={() => navigate("/settings")}>去设置查看 →</button></p>
            <div className="import-grid" style={{ marginTop: 10 }}>
              <div className="import-card">
                <h3><Sparkles size={15} /> 一键示例 <Badge tone="info">SYNTHETIC</Badge></h3>
                <p>生成合成面板 → 不可变快照 → 示例回测，零网络，最快看到完整链路。合成数据只用于演示，不代表真实市场。</p>
                <div className="import-foot"><button className="btn primary" onClick={() => setWizard(true)} disabled={busy}>生成示例数据</button><button className="btn" onClick={startSnapshot} disabled={busy}>仅构建快照</button></div>
              </div>
              <div className="import-card">
                <h3><Network size={15} /> 新浪财经（免 Token）</h3>
                <p>公开行情日线，免 Token；需开启网络。全市场较慢（约 30–45 分钟），建议先用下面的「先试几只」导入 5 只验证链路。</p>
                <div className="import-foot">
                  <button className="btn primary" disabled={busy || !sina?.available} onClick={() => startUpdate("sina")}><Upload size={15} /> 导入新浪日线</button>
                  <Badge tone={sina?.available ? "ok" : "neutral"}>{sina ? (sina.available ? "可用" : "需开启网络") : "后端未就绪"}</Badge>
                </div>
              </div>
              <div className="import-card">
                <h3><Network size={15} /> 东方财富（备用）</h3>
                <p>备用公开日线源，免 Token；需要开启网络。新浪不可用时可切换。</p>
                <div className="import-foot">
                  <button className="btn" disabled={busy || !eastmoney?.available} onClick={() => startUpdate("eastmoney")}><Upload size={15} /> 导入东财日线</button>
                  <Badge tone={eastmoney?.available ? "ok" : "neutral"}>{eastmoney ? (eastmoney.available ? "可用" : "需开启网络") : "后端未就绪"}</Badge>
                </div>
              </div>
              <div className="import-card">
                <h3><Database size={15} /> Tushare（需 Token）</h3>
                <p>需在服务端设置 <span className="mono">TUSHARE_TOKEN</span>；免费额度有限，适合补充历史数据。</p>
                <div className="import-foot">
                  <button className="btn" disabled={busy || !tushare?.available} onClick={() => startUpdate("tushare")}><Upload size={15} /> 导入 Tushare</button>
                  <Badge tone={tushare?.available ? "ok" : "neutral"}>{tushare ? (tushare.available ? "已配置 Token" : "未配置 Token") : "后端未就绪"}</Badge>
                </div>
              </div>
              <div className="import-card">
                <h3><HardDrive size={15} /> 本地文件</h3>
                <p>把 Parquet/CSV 放到本机目录后导入；不联网，适合自有数据。</p>
                <input className="input" value={localDir} onChange={(event) => setLocalDir(event.target.value)} placeholder="/path/to/data" aria-label="本地数据目录" />
                <div className="import-foot"><button className="btn" disabled={busy || !local?.available || !localDir.trim()} onClick={() => startUpdate("local")}><Upload size={15} /> 导入本地目录</button></div>
              </div>
            </div>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <label>开始<input value={start} onChange={(event) => setStart(event.target.value)} placeholder="YYYY-MM-DD" /></label>
              <label>结束<input value={end} onChange={(event) => setEnd(event.target.value)} placeholder="YYYY-MM-DD" /></label>
              <label>先试几只（代码，逗号分隔）<input value={codes} onChange={(event) => setCodes(event.target.value)} placeholder="600000,000001；留空按数量上限" /></label>
              <label>数量上限（留空默认 20）<input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" /></label>
              <label>证券数（synthetic）<input value={nSec} onChange={(event) => setNSec(event.target.value)} inputMode="numeric" /></label>
              <label>数据源<select value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.length ? providers.map((item) => <option key={item.id} value={item.id} disabled={!item.available}>{item.name}{item.available ? "" : "（不可用）"}</option>) : <option value="synthetic">Synthetic</option>}</select></label>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn primary" onClick={() => startUpdate()} disabled={busy}>更新并构建快照</button>
              <span className="muted small">provider 需已配置 Token/本地目录；失败会显示 job 错误，不阻塞其他页面。填了代码就按代码导入，否则用数量上限（默认 20 只）。</span>
            </div>
            {job ? <div className="card progress-card"><span>{job.kind === "data_update" ? "数据更新" : "快照构建"} · {progress.job?.status ?? "排队"} · {progress.transport ?? "等待"}</span><div className="progress"><div className="progress-bar" style={{ width: `${Math.round((progress.job?.progress ?? 0) * 100)}%` }} /><span>{Math.round((progress.job?.progress ?? 0) * 100)}%</span></div><button className="btn ghost" onClick={() => { setJob(null); setNotice("已隐藏任务进度，后台任务仍可继续。"); }}>隐藏</button></div> : null}
            {error ? <p className="error" role="alert">{error}</p> : null}
            {notice ? <p className="success-text">{notice}</p> : null}
          </Panel>

          <Panel title="快照" subtitle="点击行查看质量报告；快照是不可变的研究输入" actions={<span className="muted small">{data.snapshots.length} 个 · 共 {bytes(data.storage.snapshot_bytes)}</span>}>
            {data.snapshots.length ? (
              <div className="table-wrap" data-testid="snapshot-table"><table><thead><tr><th>ID</th><th>证券</th><th>交易日</th><th>区间</th><th>体检</th><th>类型</th></tr></thead><tbody>{data.snapshots.map((snap: SnapshotStatus) => <tr key={snap.id} className={qualitySnapshot === snap.id ? "selected" : ""} onClick={() => setQualitySnapshot(snap.id)}><td className="mono truncate" title={snap.id}>{snap.id}</td><td className="num">{snap.n_sec}</td><td className="num">{snap.n_time}</td><td>{dateInt(snap.start)} – {dateInt(snap.end)}</td><td>{(snap.quality as { passed?: boolean }).passed === true ? <Badge tone="ok">通过</Badge> : (snap.quality as { passed?: boolean }).passed === false ? <Badge tone="warn">有警告</Badge> : <Badge tone="neutral">—</Badge>}</td><td>{snap.synthetic ? <Badge tone="info">SYNTHETIC</Badge> : snap.source}</td></tr>)}</tbody></table></div>
            ) : <EmptyState title="还没有快照" hint="用上面的「生成示例数据」或导入真实数据后自动构建快照。" action={<button className="btn primary" onClick={() => setWizard(true)}><Sparkles size={15} /> 生成示例数据</button>} />}
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn" onClick={() => void copy(data.data_root, "数据目录")}><Copy size={14} /> 复制数据路径</button>
              <button className="btn" onClick={() => void copy(`${data.data_root}/snapshots`, "快照目录")}><Copy size={14} /> 复制快照路径</button>
              <button className="btn ghost" onClick={() => setNotice("导入：将 Parquet/LocalFile 放入数据目录后运行数据更新；导出：快照目录可直接复制备份。")}>导入/导出提示</button>
            </div>
            {qualitySnapshot ? <div className="quality-panel"><div className="card-head"><h3>质量报告 <span className="mono small">{qualitySnapshot}</span></h3><button className="btn ghost" onClick={() => setQualitySnapshot(null)}>关闭</button></div>{qualityQuery.isLoading ? <Skeleton rows={3} /> : qualityQuery.error ? <p className="error">{qualityQuery.error.message}</p> : <pre className="validation">{JSON.stringify(qualityQuery.data?.report ?? qualityQuery.data?.quality ?? {}, null, 2)}</pre>}</div> : null}
          </Panel>

          <div className="grid kpis">
            <StatTile label="数据仓库" value={data.warehouse.rows.toLocaleString("zh-CN")} hint={`行 · ${bytes(data.warehouse.bytes)} · ${Object.keys(data.warehouse.datasets).length} 个数据集`} icon={Database} />
            <StatTile label="快照" value={data.snapshots.length} hint={bytes(data.storage.snapshot_bytes)} icon={ShieldCheck} />
            <StatTile label="实验产物" value={bytes(data.storage.experiments_bytes)} hint="experiments/ 可复现目录" />
            <StatTile label="可用空间" value={bytes(data.storage.free_bytes)} hint={data.data_root} icon={HardDrive} />
          </div>

          <Panel title="数据源与存储" subtitle="凭据只从本地环境读取；UI 不发起真实网络请求，也不记录 Token">
            <div className="provider-list">{data.providers.map((item) => <div key={item.id} className="provider-row"><div><strong>{item.name}</strong><small className="muted">{item.requires_token ? "需要 Token" : item.requires_network ? "需要网络" : "本地/公开"}</small></div><span className={item.available ? "badge success" : "badge"}>{item.available ? "可用" : "不可用"}</span></div>)}</div>
            <p className="muted small">manifest <span className="mono">{data.warehouse.manifest_hash.slice(0, 16)}…</span> · 快照字节 {bytes(data.storage.snapshot_bytes)} · 规则/费率 TODO(verify)。</p>
          </Panel>

          <Panel title={`V2 数据集`} subtitle={`${catalog.data?.version ?? "v2"} · 离线 schema`}>
            {catalog.data ? <div className="table-wrap"><table><thead><tr><th>名称</th><th>粒度</th><th>存储</th><th>类型</th><th>字段</th></tr></thead><tbody>{catalog.data.datasets.map((dataset) => <tr key={dataset.name}><td className="mono">{dataset.name}</td><td>{dataset.grain}</td><td>{dataset.storage}</td><td>{dataset.synthetic === true ? <Badge tone="info">SYNTHETIC</Badge> : dataset.synthetic === false ? "本地" : "—"}</td><td className="muted small">{dataset.fields.length}</td></tr>)}</tbody></table></div> : catalog.error ? <p className="error">{catalog.error.message}</p> : <Skeleton rows={3} />}
            <p className="muted small">{catalog.data?.notes?.[0] ?? "分钟线为合成视图；日线/快照为本地数据。"}</p>
          </Panel>
          {beginner ? <p className="muted small">新手提示：先点「生成示例数据」，看到回测后再导入真实数据；导入后先看「数据体检」是否通过。</p> : null}
        </>
      ) : <EmptyState title="本地服务已连接，但还没有数据状态" hint="先运行首次向导生成示例数据。" action={<button className="btn primary" onClick={() => setWizard(true)}><Sparkles size={15} /> 首次向导</button>} />}
      {wizard ? <Onboarding onDone={(runId) => { setWizard(false); void status.refetch(); void integrity.refetch(); navigate(`/experiments?run=${encodeURIComponent(runId)}`); }} onClose={() => setWizard(false)} /> : null}
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
