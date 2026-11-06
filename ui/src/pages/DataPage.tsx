import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, Copy, Database, HardDrive, Network, RefreshCw, ShieldCheck, Sparkles, Upload, XCircle,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  useBuildSnapshot, useCompleteOnboardingStep, useDataCatalog, useDataIntegrity, useDataStatus,
  useLiveStatus, useQuality, useUpdateData,
} from "../api/queries";
import { api, getApiBase, isApiError } from "../api/client";
import type { DataIntegrity, Job, ProviderInfo, SnapshotStatus } from "../api/types";
import {
  Badge, Button, Callout, Dialog, EmptyState, Field, Input, List, ListRow, PageHeader, Panel, ProgressBar, Select,
  Skeleton, StatTile,
} from "../components";
import { useJobProgress } from "../hooks/useJobProgress";
import { bytes, dateInt } from "../lib/format";
import { useBeginner, useUIStore } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

interface DataJob { id: string; kind: "data_update" | "snapshot_build" }

function savedDataJob(key: string): { job: DataJob | null; error: string } {
  const raw = sessionStorage.getItem(key);
  if (!raw) return { job: null, error: "" };
  try {
    const saved = JSON.parse(raw) as DataJob;
    if (!saved || typeof saved.id !== "string" || !saved.id || !["data_update", "snapshot_build"].includes(saved.kind)) throw new Error("invalid job");
    return { job: saved, error: "" };
  } catch {
    sessionStorage.removeItem(key);
    return { job: null, error: "无法恢复上次数据任务：保存的记录无效。请检查数据与快照，必要时重新提交。" };
  }
}

function CheckIcon({ status }: { status: string }) {
  if (status === "pass") return <CheckCircle2 size={16} style={{ color: "var(--ok)", flex: "0 0 auto" }} aria-hidden="true" />;
  if (status === "warn") return <AlertTriangle size={16} style={{ color: "var(--warn)", flex: "0 0 auto" }} aria-hidden="true" />;
  return <XCircle size={16} style={{ color: "var(--danger)", flex: "0 0 auto" }} aria-hidden="true" />;
}

function checkTone(status: string): "ok" | "warn" | "danger" {
  return status === "pass" ? "ok" : status === "warn" ? "warn" : "danger";
}

function IntegrityHero({ integrity, onRetry }: { integrity: ReturnType<typeof useDataIntegrity>; onRetry: () => void }) {
  if (integrity.isLoading) return <Panel title="数据体检" subtitle="覆盖率 / 缺口 / 准确性 / 跨源抽样"><Skeleton rows={4} /></Panel>;
  if (integrity.isError) {
    const notReady = isApiError(integrity.error) && integrity.error.status === 404;
    return (
      <Panel title="数据体检" subtitle="数据可信是回测可信的前提">
        <EmptyState
          title={notReady ? "数据体检后端未就绪" : "数据体检加载失败"}
          hint={notReady ? "GET /api/data/integrity 尚未上线；页面已降级显示，不影响导入与快照。升级后端后刷新即可。" : integrity.error.message}
          action={<Button variant="secondary" onClick={onRetry}>重试</Button>}
        />
      </Panel>
    );
  }
  const data = integrity.data as DataIntegrity;
  const tone = data.status === "ok" ? "ok" : data.status === "warn" ? "warn" : "danger";
  const accuracyTotal = data.accuracy.ohlc_violations + data.accuracy.volume_amount_mismatch + data.accuracy.limit_violations + data.accuracy.adjustment_breaks;
  return (
    <Panel
      title="数据体检"
      subtitle="覆盖率 / 缺口 / 准确性 / 跨源抽样；不通过时结果页会降级提示"
      actions={<><Badge tone={tone} dot>{data.status === "ok" ? "体检通过" : data.status === "warn" ? "有警告" : "未通过"}</Badge><Button variant="ghost" size="sm" icon={RefreshCw} onClick={onRetry} disabled={integrity.isFetching}>刷新</Button></>}
    >
      <div className="stack">
        <div className="health-hero">
          <div className="health-figures">
            <div className="health-figure"><span>覆盖率</span><strong>{data.coverage.coverage_pct.toFixed(2)}%</strong><small>{data.coverage.present_cells.toLocaleString("zh-CN")} / {data.coverage.expected_cells.toLocaleString("zh-CN")} 个数据格</small></div>
            <div className="health-figure"><span>证券数</span><strong>{data.coverage.symbols}</strong><small>交易日 {data.coverage.trading_days}</small></div>
            <div className="health-figure"><span>缺口交易日</span><strong>{data.gaps.missing_days}</strong><small>{data.gaps.symbols_with_gaps} 只证券存在缺口</small></div>
            <div className="health-figure"><span>准确性异常</span><strong>{accuracyTotal}</strong><small>OHLC {data.accuracy.ohlc_violations} · 量额 {data.accuracy.volume_amount_mismatch} · 涨跌停 {data.accuracy.limit_violations} · 复权 {data.accuracy.adjustment_breaks}</small></div>
          </div>
          <div className="stack-tight" style={{ alignItems: "flex-end", textAlign: "right" }}>
            <div>{data.snapshot ? <Badge tone="neutral">{data.snapshot.id.slice(0, 20)}{data.snapshot.synthetic ? " · SYNTHETIC" : ` · ${data.snapshot.source}`}</Badge> : <Badge tone="neutral">无快照</Badge>}</div>
            <div className="page-note-sm">生成于 {data.generated_at.slice(0, 19).replace("T", " ")}</div>
            <div className="page-note-sm">只读检查，不联网、不修改数据。</div>
          </div>
        </div>

        {data.checks.length ? (
          <List inset>
            {data.checks.map((check) => (
              <ListRow
                key={check.id}
                leading={<CheckIcon status={check.status} />}
                title={check.title}
                subtitle={check.detail}
                trailing={<Badge tone={checkTone(check.status)}>{check.status === "pass" ? "通过" : check.status === "warn" ? "警告" : "失败"}</Badge>}
              />
            ))}
          </List>
        ) : null}

        {data.gaps.examples.length ? (
          <div className="stack-tight">
            <div className="row-between"><span className="switch-title">缺口 Top</span><span className="page-note-sm">修复建议：重新导入缺失区间或检查停牌/退市；缺口较多时不要直接相信回测结论。</span></div>
            <div className="row">
              {data.gaps.examples.slice(0, 12).map((gap, index) => <Badge key={`${gap.code}-${gap.date}-${index}`} tone="neutral">{gap.code} {dateInt(gap.date)}</Badge>)}
            </div>
          </div>
        ) : null}

        <p className="page-note-sm">跨源抽样：检查 {data.cross_source.checked} · 匹配 {data.cross_source.matched}{data.cross_source.max_rel_diff != null ? ` · 最大相对差 ${data.cross_source.max_rel_diff.toFixed(4)}` : ""}{data.cross_source.source ? ` · 对照源 ${data.cross_source.source}` : ""}。{data.cross_source.note}</p>
        <p className="page-note-sm">{data.note}</p>
      </div>
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
  const openOnboarding = useUIStore((state) => state.openOnboarding);
  const [jobStorageKey] = useState(() => `qc_data_job:${getApiBase()}`);
  const [saved] = useState(() => savedDataJob(jobStorageKey));
  const [job, setJob] = useState<DataJob | null>(saved.job);
  const [restoring, setRestoring] = useState(Boolean(saved.job));
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [restoredStatus, setRestoredStatus] = useState<Job | null>(null);
  const [progressHidden, setProgressHidden] = useState(false);
  const [qualitySnapshot, setQualitySnapshot] = useState<string | null>(null);
  const qualityQuery = useQuality(qualitySnapshot);
  const [error, setError] = useState(saved.error);
  const [notice, setNotice] = useState("");
  const [provider, setProvider] = useState("synthetic");
  const [updateMode, setUpdateMode] = useState("incremental");
  const [start, setStart] = useState("2022-01-04");
  const [end, setEnd] = useState("2024-12-31");
  const [nSec, setNSec] = useState("40");
  const [localDir, setLocalDir] = useState("");
  const [codes, setCodes] = useState("");
  const [limit, setLimit] = useState("20");
  const handled = useRef<string>("");
  const healthMarked = useRef(false);
  const sameApi = jobStorageKey === `qc_data_job:${getApiBase()}`;
  const progress = useJobProgress(!restoring && sameApi ? job?.id ?? null : null);
  const currentJob = progress.job ?? restoredStatus;
  const completeStep = useCompleteOnboardingStep();

  useEffect(() => {
    if (!sameApi) { setJob(null); setRestoring(false); setError("API 地址已变更，请重新进入数据页查看该服务的任务。"); return; }
    if (job) sessionStorage.setItem(jobStorageKey, JSON.stringify(job));
    else sessionStorage.removeItem(jobStorageKey);
  }, [job, jobStorageKey, sameApi]);
  useEffect(() => {
    if (!saved.job || !sameApi) return;
    let disposed = false;
    setError("");
    void api.job(saved.job.id).then((remote) => {
      if (disposed) return;
      if (remote.id !== saved.job!.id || remote.kind !== saved.job!.kind) {
        setJob(null); setError("无法恢复上次数据任务：任务类型不匹配。请检查数据与快照，必要时重新提交。");
      } else setRestoredStatus(remote);
      setRestoring(false);
    }).catch((reason: unknown) => {
      if (disposed) return;
      if (isApiError(reason) && reason.status === 404) {
        setJob(null); setRestoring(false);
        setError("无法恢复上次数据任务：任务已不存在。请检查数据与快照，必要时重新提交。");
      } else setError(`恢复任务连接失败：${reason instanceof Error ? reason.message : "服务暂不可用"}；任务记录已保留，可重试。`);
    });
    return () => { disposed = true; };
  }, [saved.job, restoreAttempt, sameApi]);

  // Onboarding step "data_health" is not auto-detected by the backend; mark it once
  // the integrity report loads (idempotent, failures are ignored).
  useEffect(() => {
    if (healthMarked.current || !integrity.data) return;
    healthMarked.current = true;
    completeStep.mutate("data_health", { onError: () => undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [integrity.data]);

  useEffect(() => {
    if (!sameApi || !currentJob || !job || currentJob.id !== job.id || handled.current === `${job.id}:${currentJob.status}`) return;
    handled.current = `${job.id}:${currentJob.status}`;
    if (currentJob.status === "done") {
      const snapshotId = currentJob.result?.snapshot_id;
      if (typeof snapshotId === "string" && snapshotId) {
        setNotice(`${job.kind === "data_update" ? "数据更新与快照构建完成" : "快照构建完成"}：${snapshotId}`);
      } else setError("任务完成但未返回快照 ID；请刷新快照列表，必要时点击「构建快照」重试。");
      void status.refetch();
      void integrity.refetch();
      setJob(null);
    } else if (currentJob.status === "failed" || currentJob.status === "cancelled") {
      setError(currentJob.status === "cancelled"
        ? "任务已取消。已经写入的数据和快照会保留，请检查下方快照列表；如缺少快照，可点击「构建快照」重试。"
        : currentJob.error || "任务失败");
      void status.refetch();
      void integrity.refetch();
      setJob(null);
    }
  }, [currentJob, job, status, integrity, sameApi]);

  const copy = async (text: string, label: string) => {
    try { await navigator.clipboard.writeText(text); setNotice(`已复制${label}：${text}`); }
    catch { setNotice(`${label}：${text}（浏览器拒绝剪贴板，可手动复制）`); }
  };
  const startUpdate = (providerId = provider) => {
    setError(""); setNotice(""); setProgressHidden(false);
    const payload: Record<string, unknown> = { provider: providerId, start, end, incremental: updateMode === "incremental", build_snapshot: true };
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
      onError: (reason) => { setError(reason.message); },
    });
  };
  const startSnapshot = () => {
    setError(""); setNotice(""); setProgressHidden(false);
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
  const qualityText = qualityQuery.data ? JSON.stringify(qualityQuery.data.report ?? qualityQuery.data.quality ?? {}, null, 2) : "";

  /** Provider availability copy: missing provider (404/older backend) vs present-but-disabled. */
  const providerStatus = (provider: ProviderInfo | null): { text: string; tone: "ok" | "warn" | "neutral" } => {
    if (!provider) return { text: "后端未就绪", tone: "neutral" };
    if (provider.available) return { text: "可用", tone: "ok" };
    if (provider.requires_token) return { text: "需配置 Token", tone: "warn" };
    if (provider.requires_network) return { text: "需联网（QC_ALLOW_NETWORK=1）", tone: "warn" };
    return { text: "不可用", tone: "neutral" };
  };
  const providerRow = (options: {
    id: string; icon: typeof Sparkles; title: string; subtitle: string; actionLabel: string;
    provider: ProviderInfo | null; disabled: boolean; onImport: () => void; primary?: boolean;
  }) => {
    const Icon = options.icon;
    const status = providerStatus(options.provider);
    return (
      <ListRow
        leading={<Icon size={18} aria-hidden="true" />}
        title={options.title}
        subtitle={options.subtitle}
        action={(
          <div className="settings-actions">
            <Badge tone={status.tone}>{status.text}</Badge>
            <Button variant={options.primary ? "primary" : "secondary"} size="sm" icon={Upload} disabled={busy || options.disabled} onClick={options.onImport}>{options.actionLabel}</Button>
          </div>
        )}
      />
    );
  };

  return (
    <div className="page">
      <PageHeader
        title="数据"
        subtitle="先看数据体检，再导入真实数据；数据可信是回测可信的前提。"
        actions={(
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={() => void status.refetch()} disabled={status.isFetching}>刷新</Button>
            <Button variant="secondary" icon={Sparkles} onClick={openOnboarding}>首次向导</Button>
            <Button variant="primary" onClick={startSnapshot} disabled={busy}>构建快照</Button>
          </>
        )}
      />

      {status.isLoading ? <Skeleton rows={5} /> : status.error ? (
        <EmptyState title="无法连接本地服务" hint={status.error.message} action={<Button variant="secondary" onClick={() => void status.refetch()}>重试</Button>} />
      ) : data ? (
        <div className="stack">
          <IntegrityHero integrity={integrity} onRetry={() => void integrity.refetch()} />

          <Panel
            title="导入真实数据"
            subtitle="网络默认关闭；真实数据导入需在服务端显式开启（QC_ALLOW_NETWORK=1）"
            actions={<Badge tone={networkOn ? "ok" : "warn"} dot>{networkOn ? "网络已开启" : "网络默认关闭"}</Badge>}
            className="responsive-list"
          >
            <div className="stack">
              <Callout tone={networkOn ? "info" : "warn"} title={networkOn ? "网络已开启" : "网络未开启"}>
                启动 <span className="mono">qc serve</span> 前设置 <span className="mono">QC_ALLOW_NETWORK=1</span> 并重启；测试永远用录制 fixture。未开启时页面不会发起任何外部请求。全市场导入约 30–45 分钟，建议先导几只试试；公开数据不得再分发，导入后先看「数据体检」通过再回测。
                <Button variant="ghost" size="sm" onClick={() => navigate("/settings")}>去设置查看 →</Button>
              </Callout>

              <List inset>
                {providerRow({
                  id: "synthetic", icon: Sparkles, title: "一键示例（SYNTHETIC）", subtitle: "合成面板 → 不可变快照 → 示例回测；零网络，只用于演示，不代表真实市场。",
                  actionLabel: "生成示例", provider: { id: "synthetic", name: "Synthetic", requires_token: false, requires_network: false, available: true, capabilities: {} },
                  disabled: false, onImport: openOnboarding, primary: true,
                })}
                {providerRow({
                  id: "sina", icon: Network, title: "新浪财经（免 Token）", subtitle: "公开行情日线，免 Token；需开启网络。全市场较慢，建议先用「先试几只」导入 5 只验证链路。",
                  actionLabel: "导入新浪日线", provider: sina, disabled: !sina?.available, onImport: () => startUpdate("sina"), primary: true,
                })}
                {providerRow({
                  id: "eastmoney", icon: Network, title: "东方财富（备用）", subtitle: "备用公开日线源，免 Token；需要开启网络。新浪不可用时可切换。",
                  actionLabel: "导入东财日线", provider: eastmoney, disabled: !eastmoney?.available, onImport: () => startUpdate("eastmoney"),
                })}
                {providerRow({
                  id: "tushare", icon: Database, title: "Tushare（需 Token）", subtitle: "需在服务端设置 TUSHARE_TOKEN；免费额度有限，适合补充历史数据。",
                  actionLabel: "导入 Tushare", provider: tushare, disabled: !tushare?.available, onImport: () => startUpdate("tushare"),
                })}
                {providerRow({
                  id: "local", icon: HardDrive, title: "本地文件", subtitle: "把 Parquet/CSV 放到本机目录后导入；不联网，适合自有数据。",
                  actionLabel: "导入本地目录", provider: local, disabled: !local?.available || !localDir.trim(), onImport: () => startUpdate("local"),
                })}
              </List>

              <div className="grid grid-3">
                <Field label="更新方式" hint={updateMode === "incremental" ? "沿用同一数据来源、证券范围和生成参数，追加或更新日期。" : "取数与质量检查通过后替换当前数据仓库；已保存的快照与实验保留。"}>
                  <Select value={updateMode} onChange={(event) => setUpdateMode(event.target.value)} aria-label="更新方式" options={[
                    { value: "incremental", label: "增量更新（同一来源与范围）" },
                    { value: "replace", label: "替换数据（重新导入）" },
                  ]} />
                </Field>
                <Field label="开始日期"><Input value={start} onChange={(event) => setStart(event.target.value)} placeholder="YYYY-MM-DD" aria-label="开始日期" /></Field>
                <Field label="结束日期"><Input value={end} onChange={(event) => setEnd(event.target.value)} placeholder="YYYY-MM-DD" aria-label="结束日期" /></Field>
                <Field label="本地目录" hint="仅「本地文件」导入使用"><Input value={localDir} onChange={(event) => setLocalDir(event.target.value)} placeholder="/path/to/data" aria-label="本地数据目录" /></Field>
                <Field label="先试几只（代码，逗号分隔）" hint="留空则按数量上限导入；建议先导 5 只验证链路"><Input value={codes} onChange={(event) => setCodes(event.target.value)} placeholder="600000,000001" aria-label="先试几只（代码，逗号分隔）" /></Field>
                <Field label="数量上限（留空默认 20）"><Input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" aria-label="数量上限" /></Field>
                <Field label="证券数（synthetic）"><Input value={nSec} onChange={(event) => setNSec(event.target.value)} inputMode="numeric" aria-label="证券数（synthetic）" /></Field>
                <Field label="数据源（高级）">
                  <Select value={provider} onChange={(event) => setProvider(event.target.value)} options={providers.length ? providers.map((item) => ({ value: item.id, label: `${item.name}${item.available ? "" : item.requires_token ? "（需 Token）" : item.requires_network ? "（需联网）" : "（不可用）"}`, disabled: !item.available })) : [{ value: "synthetic", label: "Synthetic" }]} aria-label="数据源（高级）" />
                </Field>
              </div>
              <div className="row">
                <Button variant="primary" onClick={() => startUpdate()} disabled={busy}>更新并构建快照</Button>
                <span className="page-note-sm">provider 需已配置 Token/本地目录；失败会显示 job 错误，不阻塞其他页面。填了代码就按代码导入，否则用数量上限（默认 20 只）。</span>
              </div>

              {job && !progressHidden ? (
                <div className="stack-tight">
                  <ProgressBar value={Math.round((currentJob?.progress ?? 0) * 100)} label={`${job.kind === "data_update" ? "数据更新与快照" : "快照构建"} · ${restoring ? "恢复任务连接" : currentJob?.status ?? "排队"} · ${progress.transport ?? "等待"}`} />
                  <div><Button variant="ghost" size="sm" onClick={() => setProgressHidden(true)}>隐藏</Button></div>
                </div>
              ) : null}
              {job ? <p className="page-note-sm">任务在本地服务中继续执行，切页不会中断{job.kind === "data_update" ? "导入与快照构建" : "快照构建"}。{progressHidden ? <Button variant="ghost" size="sm" onClick={() => setProgressHidden(false)}>显示进度</Button> : null}</p> : null}
              {job && restoring && error ? <Button variant="secondary" onClick={() => setRestoreAttempt((value) => value + 1)}>重试任务连接</Button> : null}
              {error ? <Callout tone="danger" title={error} /> : null}
              {notice ? <Callout tone="success" title={notice} /> : null}
            </div>
          </Panel>

          <Panel
            title="快照"
            subtitle="点击行查看质量报告；快照是不可变的研究输入"
            actions={<span className="page-note-sm">{data.snapshots.length} 个 · 共 {bytes(data.storage.snapshot_bytes)}</span>}
          >
            {data.snapshots.length ? (
              <div className="table-wrap" data-testid="snapshot-table">
                <table>
                  <thead><tr><th>ID</th><th className="num">证券</th><th className="num">交易日</th><th>区间</th><th>体检</th><th>类型</th></tr></thead>
                  <tbody>
                    {data.snapshots.map((snap: SnapshotStatus) => (
                      <tr key={snap.id} className="table-row-hover" onClick={() => setQualitySnapshot(snap.id)}>
                        <td className="mono truncate" title={snap.id}>{snap.id}</td>
                        <td className="num">{snap.n_sec}</td>
                        <td className="num">{snap.n_time}</td>
                        <td>{dateInt(snap.start)} – {dateInt(snap.end)}</td>
                        <td>{(snap.quality as { passed?: boolean }).passed === true ? <Badge tone="ok">通过</Badge> : (snap.quality as { passed?: boolean }).passed === false ? <Badge tone="warn">有警告</Badge> : <Badge tone="neutral">—</Badge>}</td>
                        <td>{snap.synthetic ? <Badge tone="info">SYNTHETIC</Badge> : snap.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <EmptyState title="还没有快照" hint="用上面的「生成示例」或导入真实数据后自动构建快照。" action={<Button variant="primary" icon={Sparkles} onClick={openOnboarding}>生成示例数据</Button>} />}
            <div className="row" style={{ marginTop: "var(--sp-5)" }}>
              <Button variant="secondary" size="sm" icon={Copy} onClick={() => void copy(data.data_root, "数据目录")}>复制数据路径</Button>
              <Button variant="secondary" size="sm" icon={Copy} onClick={() => void copy(`${data.data_root}/snapshots`, "快照目录")}>复制快照路径</Button>
              <Button variant="ghost" size="sm" onClick={() => setNotice("导入：将 Parquet/LocalFile 放入数据目录后运行数据更新；导出：快照目录可直接复制备份。")}>导入/导出提示</Button>
            </div>
          </Panel>

          <div className="metric-grid">
            <StatTile label="数据仓库" value={data.warehouse.rows.toLocaleString("zh-CN")} hint={`行 · ${bytes(data.warehouse.bytes)} · ${Object.keys(data.warehouse.datasets).length} 个数据集`} icon={Database} />
            <StatTile label="快照" value={data.snapshots.length} hint={bytes(data.storage.snapshot_bytes)} icon={ShieldCheck} />
            <StatTile label="实验产物" value={bytes(data.storage.experiments_bytes)} hint="experiments/ 可复现目录" />
            <StatTile label="可用空间" value={bytes(data.storage.free_bytes)} hint={data.data_root} icon={HardDrive} />
          </div>

          <Panel title="数据源与存储" subtitle="凭据只从本地环境读取；UI 不发起真实网络请求，也不记录 Token">
            <div className="stack">
              {data.providers.map((item) => {
                const status = providerStatus(item);
                return (
                  <div key={item.id} className="provider-row">
                    <div className="provider-row-main"><strong>{item.name}</strong><small>{item.requires_token ? "需要 Token" : item.requires_network ? "需要网络" : "本地/公开"}</small></div>
                    <Badge tone={status.tone}>{status.text}</Badge>
                  </div>
                );
              })}
              <p className="page-note-sm">manifest <span className="mono">{data.warehouse.manifest_hash.slice(0, 16)}…</span> · 快照字节 {bytes(data.storage.snapshot_bytes)} · 规则/费率 TODO(verify)。</p>
            </div>
          </Panel>

          <Panel title="V2 数据集" subtitle={`${catalog.data?.version ?? "v2"} · 离线 schema`}>
            {catalog.data ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>名称</th><th>粒度</th><th>存储</th><th>类型</th><th className="num">字段</th></tr></thead>
                  <tbody>{catalog.data.datasets.map((dataset) => <tr key={dataset.name}><td className="mono">{dataset.name}</td><td>{dataset.grain}</td><td>{dataset.storage}</td><td>{dataset.synthetic === true ? <Badge tone="info">SYNTHETIC</Badge> : dataset.synthetic === false ? "本地" : "—"}</td><td className="num">{dataset.fields.length}</td></tr>)}</tbody>
                </table>
              </div>
            ) : catalog.error ? <p className="error-text">{catalog.error.message}</p> : <Skeleton rows={3} />}
            <p className="page-note-sm">{catalog.data?.notes?.[0] ?? "分钟线为合成视图；日线/快照为本地数据。"}</p>
          </Panel>
          {beginner ? <p className="page-note-sm">新手提示：先点「生成示例」看到回测后，再导入真实数据；导入后先看「数据体检」是否通过。</p> : null}
        </div>
      ) : (
        <EmptyState title="本地服务已连接，但还没有数据状态" hint="先运行首次向导生成示例数据。" action={<Button variant="primary" icon={Sparkles} onClick={openOnboarding}>首次向导</Button>} />
      )}

      <Dialog open={qualitySnapshot !== null} onOpenChange={(open) => { if (!open) setQualitySnapshot(null); }} title="质量报告" description={qualitySnapshot ?? undefined} size="lg" footer={<Button variant="secondary" onClick={() => setQualitySnapshot(null)}>关闭</Button>}>
        {qualityQuery.isLoading ? <Skeleton rows={4} /> : qualityQuery.error ? <p className="error-text">{qualityQuery.error.message}</p> : <pre className="quality-json">{qualityText}</pre>}
      </Dialog>

      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
