import { useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, Database, MinusCircle, PlugZap, ShieldCheck, Stethoscope, Wifi, XCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { configure, getApiBase, getToken } from "../api/client";
import { useDataStatus, useDoctor, useHealth, useLiveStatus, useMeta } from "../api/queries";
import { Badge, Panel, Segmented } from "../components";
import { applyAppearance, readAppearance, type Appearance } from "../lib/appearance";
import { doctorCheckLabel, doctorCountsSummary, doctorOverallBadge, doctorOverallLabel, doctorStatusColor } from "../lib/doctor";
import { dateInt } from "../lib/format";
import { ensureNotificationPermission } from "../lib/notify";
import { setBeginner, useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

function DoctorStatusIcon({ status }: { status: string }) {
  const style = { color: doctorStatusColor(status), flex: "0 0 auto" } as const;
  if (status === "pass") return <CheckCircle2 size={14} style={style} />;
  if (status === "warn") return <AlertTriangle size={14} style={style} />;
  if (status === "fail") return <XCircle size={14} style={style} />;
  return <MinusCircle size={14} style={style} />;
}

const INITIAL_APPEARANCE = readAppearance();

export default function SettingsPage() {
  const navigate = useNavigate();
  const [base, setBase] = useState(getApiBase());
  const [token, setToken] = useState(getToken());
  const [theme, setTheme] = useState<Appearance["theme"]>(INITIAL_APPEARANCE.theme);
  const [density, setDensity] = useState<Appearance["density"]>(INITIAL_APPEARANCE.density);
  const [colorMode, setColorMode] = useState<Appearance["colorMode"]>(INITIAL_APPEARANCE.colorMode);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState("");
  const [notifyState, setNotifyState] = useState<string>(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const beginner = useBeginner();
  const health = useHealth();
  const meta = useMeta();
  const data = useDataStatus();
  const live = useLiveStatus();
  const doctor = useDoctor();
  const [doctorError, setDoctorError] = useState("");

  const save = () => {
    configure(base, token);
    applyAppearance({ theme, density, colorMode });
    window.dispatchEvent(new Event("qc-settings"));
    setSaved(true);
    setTest("");
    void health.refetch(); void meta.refetch(); void data.refetch(); void live.refetch();
  };
  const check = async () => {
    setTest("测试中…");
    try {
      const result = await health.refetch();
      if (result.error) throw result.error;
      setTest(`已连接：${result.data?.engine_backend ?? "?"} · v${result.data?.version ?? "?"}`);
    } catch (error) { setTest(`连接失败：${error instanceof Error ? error.message : "unknown"}`); }
  };
  const runSelfCheck = async () => {
    setDoctorError("");
    try {
      const result = await doctor.refetch();
      if (result.error) throw result.error;
    } catch (error) { setDoctorError(`自检失败：${error instanceof Error ? error.message : "unknown"}`); }
  };
  const changeAppearance = (next: Partial<Appearance>) => {
    const value = applyAppearance(next);
    setTheme(value.theme); setDensity(value.density); setColorMode(value.colorMode);
    window.dispatchEvent(new Event("qc-settings"));
  };
  const liveEnabled = live.data?.enabled === true;
  const liveTone = liveEnabled ? "ok" as const : "warn" as const;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>设置</h1><p className="page-lead">服务连接、数据与网络、外观与新手模式；所有设置只存本机。</p></div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => void check()}><PlugZap size={15} /> 测试连接</button>
          <button className="btn primary" onClick={save}>保存设置</button>
        </div>
      </header>
      {saved ? <p className="success-text"><CheckCircle2 size={14} /> 已保存（仅本机 localStorage）</p> : null}
      {test ? <p className={test.startsWith("已连接") ? "success-text" : "error"}>{test}</p> : null}

      <div className="grid two-col">
        <div className="stack">
          <Panel title="本地服务" subtitle="qc serve 默认同源；分离部署时填完整地址">
            <div className="form-grid">
              <label>API 地址<input value={base} onChange={(event) => setBase(event.target.value)} placeholder="留空 = 同源（qc serve 托管 UI）" autoComplete="off" spellCheck={false} /></label>
              <label>Bearer Token<input value={token} onChange={(event) => setToken(event.target.value)} type="password" autoComplete="new-password" spellCheck={false} /></label>
            </div>
            <p className="muted small"><span className="mono">qc serve --open</span> 的 <span className="mono">?token=</span> 会自动写入 localStorage 并从 URL 移除；Token 不进入日志、不发送到第三方。</p>
            <div className="setting-row"><div className="setting-text"><strong>连接状态</strong><p>引擎 {health.data?.engine_backend ?? (health.isError ? "未连接" : "…")} · 版本 {health.data?.version ?? meta.data?.version ?? "—"} · 数据根 <span className="mono">{meta.data?.data_root ?? "—"}</span></p></div><Badge tone={health.isError ? "danger" : health.data ? "ok" : "neutral"} dot>{health.isError ? "未连接" : health.data ? "已连接" : "检测中"}</Badge></div>
          </Panel>

          <Panel title="数据与网络" subtitle="网络能力只在运行时显式开启；测试永远用录制 fixture">
            <div className="setting-row">
              <div className="setting-text"><strong>实时行情 / 东财导入</strong><p>网络默认关闭，全站不会发起外部请求。开启方式：启动 <span className="mono">qc serve</span> 前设置环境变量 <span className="mono">QC_ALLOW_NETWORK=1</span> 并重启。当前状态：{live.data?.state ?? "off"} · 来源 {live.data?.source ?? "none"}{live.data?.notice ? ` · ${live.data.notice}` : ""}</p></div>
              <div className="setting-control"><Badge tone={liveTone} dot>{liveEnabled ? "网络已开启" : "网络已关闭"}</Badge><button className="btn ghost" onClick={() => navigate("/data")}>去数据页 →</button></div>
            </div>
            <div className="setting-row">
              <div className="setting-text"><strong>数据源状态</strong><p>凭据只从本地环境/系统钥匙串读取；不可用的数据源不会出现在导入选项里。</p></div>
              <div className="setting-control"><Badge tone="neutral">{data.data?.providers.filter((item) => item.available).length ?? 0} / {data.data?.providers.length ?? 0} 可用</Badge></div>
            </div>
            {(data.data?.providers ?? []).map((provider) => <div className="provider-row" key={provider.id}><div><strong>{provider.name}</strong><small className="muted">{provider.requires_token ? "需 Token" : provider.requires_network ? "需网络" : "本地"}</small></div><span className={provider.available ? "badge success" : "badge"}>{provider.available ? "可用" : "不可用"}</span></div>)}
            <div className="setting-row"><div className="setting-text"><strong>最新快照</strong><p>{data.data?.snapshots[0] ? `${data.data.snapshots[0].id} · ${dateInt(data.data.snapshots[0].end)} · ${data.data.snapshots[0].synthetic ? "SYNTHETIC" : data.data.snapshots[0].source}` : "还没有快照；去数据页生成示例或导入真实数据。"}</p></div><button className="btn ghost" onClick={() => navigate("/data")}>数据页 →</button></div>
          </Panel>

          <Panel title="外观" subtitle="主题 / 密度 / 涨跌配色；改动立即生效">
            <div className="setting-row">
              <div className="setting-text"><strong>主题</strong><p>深浅色都使用同一套 tokens；对比度 ≥ 4.5:1。</p></div>
              <div className="setting-control"><Segmented ariaLabel="主题" value={theme} onChange={(value) => changeAppearance({ theme: value as Appearance["theme"] })} options={[{ value: "light", label: "浅色" }, { value: "dark", label: "深色" }]} /></div>
            </div>
            <div className="setting-row">
              <div className="setting-text"><strong>密度</strong><p>紧凑模式减少留白，适合小屏幕。</p></div>
              <div className="setting-control"><Segmented ariaLabel="密度" value={density} onChange={(value) => changeAppearance({ density: value as Appearance["density"] })} options={[{ value: "comfortable", label: "舒适" }, { value: "compact", label: "紧凑" }]} /></div>
            </div>
            <div className="setting-row">
              <div className="setting-text"><strong>涨跌配色</strong><p>红涨绿跌 / 绿涨红跌 / 色盲友好（蓝/橙）；只影响语义色。</p></div>
              <div className="setting-control"><Segmented ariaLabel="涨跌配色" value={colorMode} onChange={(value) => changeAppearance({ colorMode: value as Appearance["colorMode"] })} options={[{ value: "red-up", label: "红涨绿跌" }, { value: "green-up", label: "绿涨红跌" }, { value: "color-blind", label: "色盲友好" }]} /></div>
            </div>
            <div className="setting-row">
              <div className="setting-text"><strong>桌面提醒</strong><p>回测完成、模拟成交时显示本地 toast；授予浏览器通知权限后才发系统通知，不联网。</p></div>
              <div className="setting-control"><Badge tone="neutral">{notifyState === "granted" ? "已允许" : notifyState === "denied" ? "已拒绝/不支持" : notifyState}</Badge><button className="btn" onClick={async () => setNotifyState(await ensureNotificationPermission())}><Bell size={14} /> 启用提醒</button></div>
            </div>
          </Panel>

          <Panel title="新手模式" subtitle="默认开启；关闭后显示全部字段、导出、插件与 DSL 入口">
            <div className="setting-row">
              <div className="setting-text"><strong>{beginner ? "新手模式已开启" : "专业模式（新手模式已关闭）"}</strong><p>开启时：隐藏高级参数、术语配白话解释、每页突出「下一步」；关闭时展示全部字段与插件入口。状态存 localStorage <span className="mono">qc_beginner</span>。</p></div>
              <div className="setting-control">
                <button type="button" role="switch" aria-checked={beginner} aria-label="新手模式" className="switch" onClick={() => setBeginner(!beginner)} />
                <span className="muted small">{beginner ? "开" : "关"}</span>
              </div>
            </div>
            <p className="muted small">快捷键：⌘K / Ctrl-K 打开命令面板；Alt+1…9 切换页面；Esc 关闭弹层。设置保存后即时生效。</p>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="本地自检" subtitle="只读检查 Python/依赖/C++ 引擎/数据目录/端口；不联网、不改文件" actions={<button className="btn" onClick={() => void runSelfCheck()} disabled={doctor.isFetching}><Stethoscope size={15} /> {doctor.isFetching ? "自检中…" : "运行自检"}</button>}>
            {doctor.data ? <div className="row" style={{ gap: 8 }}><span className={doctorOverallBadge(doctor.data.status)}>{doctorOverallLabel(doctor.data.status)}</span><span className="muted small">{doctorCountsSummary(doctor.data.counts)}</span></div> : <p className="muted small">点击「运行自检」开始；无网络依赖。</p>}
            {doctorError ? <p className="error" role="alert">{doctorError}</p> : null}
            {doctor.data ? (
              <div className="provider-list" style={{ marginTop: 8 }}>
                {doctor.data.checks.map((item) => (
                  <div className="health-check" key={item.id}>
                    <DoctorStatusIcon status={item.status} />
                    <div className="health-check-body"><strong>{item.title}</strong><small>{item.detail}</small>{item.hint ? <small className="mono">{item.hint}</small> : null}</div>
                    <Badge tone={item.status === "pass" ? "ok" : item.status === "warn" ? "warn" : item.status === "fail" ? "danger" : "neutral"}>{doctorCheckLabel(item.status)}</Badge>
                  </div>
                ))}
                <p className="muted small mono" style={{ overflowWrap: "anywhere" }}>{doctor.data.version} · {doctor.data.engine_backend} · {doctor.data.generated_at} · {doctor.data.root}</p>
              </div>
            ) : null}
          </Panel>

          <Panel title="关于 QuantCore" subtitle="本地优先、零云依赖；仅研究与模拟">
            <div className="provider-list">
              <div className="provider-row"><span>版本</span><strong>{meta.data?.version ?? health.data?.version ?? "—"}</strong></div>
              <div className="provider-row"><span>引擎</span><strong>{meta.data?.engine_backend ?? health.data?.engine_backend ?? "—"}</strong></div>
              <div className="provider-row"><span>数据模式</span><strong>{meta.data?.synthetic_only ? "SYNTHETIC / 本地" : "本地快照"}</strong></div>
              <div className="provider-row"><span>下单能力</span><strong>无（BrokerGateway 禁用）</strong></div>
            </div>
            <p className="muted small"><ShieldCheck size={13} /> 仅研究与模拟，不包含真实下单、不连接券商、不上传策略与数据。规则/费率 TODO(verify)。{t.disclaimer}</p>
            <p className="muted small"><Wifi size={13} /> 网络能力默认关闭；开启后仅用于只读行情/公开数据导入，绝不用于交易。</p>
            <p className="muted small"><Database size={13} /> 合成数据均标注 SYNTHETIC；历史表现不代表未来，不构成投资建议。</p>
          </Panel>
        </div>
      </div>
      <p className="muted small">{t.disclaimer}</p>
    </div>
  );
}
