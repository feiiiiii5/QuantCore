import { useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, Database, MinusCircle, PlugZap, ShieldCheck, Stethoscope, Wifi, XCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { configure, getApiBase, getToken } from "../api/client";
import { useDataStatus, useDoctor, useHealth, useLiveStatus, useMeta } from "../api/queries";
import {
  Badge, Button, Callout, Field, Input, List, ListRow, ListSep, PageHeader, Panel, Segmented, Switch,
} from "../components";
import { applyAppearance, readAppearance, type Appearance } from "../lib/appearance";
import { doctorCheckLabel, doctorCountsSummary, doctorStatusColor } from "../lib/doctor";
import { dateInt } from "../lib/format";
import { ensureNotificationPermission } from "../lib/notify";
import { setBeginner, useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const INITIAL_APPEARANCE = readAppearance();

function DoctorIcon({ status }: { status: string }) {
  const style = { color: doctorStatusColor(status), flex: "0 0 auto" } as const;
  if (status === "pass") return <CheckCircle2 size={16} style={style} aria-hidden="true" />;
  if (status === "warn") return <AlertTriangle size={16} style={style} aria-hidden="true" />;
  if (status === "fail") return <XCircle size={16} style={style} aria-hidden="true" />;
  return <MinusCircle size={16} style={style} aria-hidden="true" />;
}

function doctorTone(status: string): "ok" | "warn" | "danger" | "neutral" {
  if (status === "pass") return "ok";
  if (status === "warn") return "warn";
  if (status === "fail") return "danger";
  return "neutral";
}

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
  const [doctorError, setDoctorError] = useState("");
  const beginner = useBeginner();
  const health = useHealth();
  const meta = useMeta();
  const data = useDataStatus();
  const live = useLiveStatus();
  const doctor = useDoctor();

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
  const connected = health.isError ? "danger" : health.data ? "ok" : "neutral";
  const connectedLabel = health.isError ? "未连接" : health.data ? "已连接" : "检测中";
  const latestSnapshot = data.data?.snapshots[0] ?? null;

  return (
    <div className="page">
      <PageHeader
        title="设置"
        subtitle="服务连接、数据与网络、外观与新手模式；所有设置只存本机，不上传、不联网。"
        actions={(
          <>
            <Button variant="secondary" icon={PlugZap} onClick={() => void check()}>测试连接</Button>
            <Button variant="primary" onClick={save}>保存设置</Button>
          </>
        )}
      />

      {saved ? <Callout tone="success" title="已保存（仅本机 localStorage）">连接地址、Token 与外观设置已生效；刷新页面后仍保留。</Callout> : null}
      {test ? <Callout tone={test.startsWith("已连接") ? "success" : "danger"} title={test} /> : null}

      <div className="grid grid-2">
        <div className="stack">
          <Panel title="本地服务" subtitle="qc serve 默认同源；分离部署时填完整地址">
            <div className="stack">
              <Field label="API 地址" hint="留空 = 同源（qc serve 托管 UI）">
                <Input value={base} onChange={(event) => setBase(event.target.value)} placeholder="留空 = 同源" autoComplete="off" spellCheck={false} aria-label="API 地址" />
              </Field>
              <Field label="Bearer Token" hint="由 qc serve --open 自动写入；不进入日志、不发送到第三方">
                <Input value={token} onChange={(event) => setToken(event.target.value)} type="password" autoComplete="new-password" spellCheck={false} placeholder="留空 = 无 Token" aria-label="Bearer Token" />
              </Field>
              <List inset>
                <ListRow title="连接状态" subtitle={health.isError ? "无法连接本地服务" : `引擎 ${health.data?.engine_backend ?? "…"} · 版本 ${health.data?.version ?? meta.data?.version ?? "—"}`} trailing={<Badge tone={connected} dot>{connectedLabel}</Badge>} />
                <ListRow title="数据根目录" subtitle={<span className="mono-wrap">{meta.data?.data_root ?? "—"}</span>} />
              </List>
            </div>
          </Panel>

          <Panel title="数据与网络" subtitle="网络能力只在运行时显式开启；测试永远用录制 fixture">
            <div className="stack">
              <Callout tone={liveEnabled ? "success" : "warn"} title={liveEnabled ? "网络已开启" : "网络默认关闭"} action={<Button variant="ghost" size="sm" onClick={() => navigate("/data")}>去数据页</Button>}>
                {liveEnabled
                  ? `实时行情已开启（来源 ${live.data?.source ?? "none"}）。公开数据只读，绝不用于交易。`
                  : "启动 qc serve 前设置环境变量 QC_ALLOW_NETWORK=1 并重启，才可开启实时行情与公开数据导入；未开启时全站不发起外部请求。"}
              </Callout>
              <List inset>
                <ListRow title="实时状态" subtitle={`${live.data?.state ?? "off"} · ${live.data?.source ?? "none"}${live.data?.notice ? ` · ${live.data.notice}` : ""}`} trailing={<Badge tone={liveEnabled ? "ok" : "warn"} dot>{liveEnabled ? "已开启" : "未开启"}</Badge>} />
                <ListRow title="最新快照" subtitle={latestSnapshot ? `${latestSnapshot.id} · ${dateInt(latestSnapshot.end)} · ${latestSnapshot.synthetic ? "SYNTHETIC" : latestSnapshot.source}` : "还没有快照；去数据页生成示例或导入真实数据"} trailing={<Button variant="ghost" size="sm" onClick={() => navigate("/data")}>数据页</Button>} />
                <ListSep />
                {(data.data?.providers ?? []).map((provider) => (
                  <ListRow
                    key={provider.id}
                    title={provider.name}
                    subtitle={provider.requires_token ? "需要 Token" : provider.requires_network ? "需要网络" : "本地 / 公开"}
                    trailing={<Badge tone={provider.available ? "ok" : "neutral"}>{provider.available ? "可用" : "不可用"}</Badge>}
                  />
                ))}
              </List>
            </div>
          </Panel>

          <Panel title="外观" subtitle="主题 / 密度 / 涨跌配色；改动立即生效">
            <div className="stack">
              <div className="row-between">
                <div><div className="switch-title">主题</div><div className="switch-desc">深浅色共用同一套 tokens，对比度 ≥ 4.5:1。</div></div>
                <Segmented ariaLabel="主题" value={theme} onChange={(value) => changeAppearance({ theme: value as Appearance["theme"] })} items={[{ value: "light", label: "浅色" }, { value: "dark", label: "深色" }]} />
              </div>
              <ListSep />
              <div className="row-between">
                <div><div className="switch-title">密度</div><div className="switch-desc">紧凑模式缩小行高与内边距，适合小屏幕。</div></div>
                <Segmented ariaLabel="密度" value={density} onChange={(value) => changeAppearance({ density: value as Appearance["density"] })} items={[{ value: "comfortable", label: "舒适" }, { value: "compact", label: "紧凑" }]} />
              </div>
              <ListSep />
              <div className="row-between">
                <div><div className="switch-title">涨跌配色</div><div className="switch-desc">只影响语义色，不改变数据本身。</div></div>
                <Segmented ariaLabel="涨跌配色" value={colorMode} onChange={(value) => changeAppearance({ colorMode: value as Appearance["colorMode"] })} items={[{ value: "red-up", label: "红涨绿跌" }, { value: "green-up", label: "绿涨红跌" }, { value: "color-blind", label: "色盲友好" }]} />
              </div>
              <ListSep />
              <div className="row-between">
                <div><div className="switch-title">桌面提醒</div><div className="switch-desc">回测完成、模拟成交时本地提醒；授予浏览器权限后才发系统通知，不联网。</div></div>
                <div className="settings-actions">
                  <Badge tone="neutral">{notifyState === "granted" ? "已允许" : notifyState === "denied" ? "已拒绝/不支持" : notifyState}</Badge>
                  <Button variant="secondary" size="sm" icon={Bell} onClick={async () => setNotifyState(await ensureNotificationPermission())}>启用提醒</Button>
                </div>
              </div>
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="新手模式" subtitle="默认开启；关闭后显示全部字段、导出、插件与 DSL 入口">
            <Switch
              id="beginner-mode"
              checked={beginner}
              onChange={(checked) => setBeginner(checked)}
              label={beginner ? "新手模式已开启" : "专业模式（新手模式已关闭）"}
              description="开启时隐藏高级参数、术语配白话解释、每页突出下一步；关闭时展示全部字段与插件入口。状态存 localStorage qc_beginner。"
              ariaLabel="新手模式"
            />
            <p className="page-note-sm" style={{ marginTop: "var(--sp-6)" }}>快捷键：⌘K / Ctrl-K 打开命令面板；Alt+1…9 切换页面；Esc 关闭弹层。</p>
          </Panel>

          <Panel
            title="本地自检"
            subtitle="只读检查 Python/依赖/C++ 引擎/数据目录/端口；不联网、不改文件"
            actions={<Button variant="secondary" size="sm" icon={Stethoscope} loading={doctor.isFetching} onClick={() => void runSelfCheck()}>{doctor.isFetching ? "自检中…" : "运行自检"}</Button>}
          >
            {doctor.data ? (
              <div className="stack">
                <div className="row">
                  <Badge tone={doctorTone(doctor.data.status)} dot>{doctor.data.status === "ok" ? "全部通过" : doctor.data.status === "warn" ? "有警告" : "有失败项"}</Badge>
                  <span className="page-note-sm">{doctorCountsSummary(doctor.data.counts)}</span>
                </div>
                <List inset>
                  {doctor.data.checks.map((item) => (
                    <ListRow
                      key={item.id}
                      leading={<DoctorIcon status={item.status} />}
                      title={item.title}
                      subtitle={<>{item.detail}{item.hint ? <span className="mono" style={{ display: "block" }}>{item.hint}</span> : null}</>}
                      trailing={<Badge tone={doctorTone(item.status)}>{doctorCheckLabel(item.status)}</Badge>}
                    />
                  ))}
                </List>
                <p className="page-note-sm mono-wrap">{doctor.data.version} · {doctor.data.engine_backend} · {doctor.data.generated_at} · {doctor.data.root}</p>
              </div>
            ) : (
              <p className="page-note-sm">点击「运行自检」开始；无网络依赖，只读检查本地环境。</p>
            )}
            {doctorError ? <Callout tone="danger" title={doctorError} /> : null}
          </Panel>

          <Panel title="关于 QuantCore" subtitle="本地优先、零云依赖；仅研究与模拟">
            <div className="stack">
              <List inset>
                <ListRow title="版本" trailing={<span className="settings-value">{meta.data?.version ?? health.data?.version ?? "—"}</span>} />
                <ListRow title="引擎" trailing={<span className="settings-value">{meta.data?.engine_backend ?? health.data?.engine_backend ?? "—"}</span>} />
                <ListRow title="数据模式" trailing={<span className="settings-value">{meta.data?.synthetic_only ? "SYNTHETIC / 本地" : "本地快照"}</span>} />
                <ListRow title="下单能力" trailing={<span className="settings-value">无（BrokerGateway 禁用）</span>} />
              </List>
              <Callout tone="info" icon={ShieldCheck} title="仅研究与模拟">
                不包含真实下单、不连接券商、不上传策略与数据。规则/费率 TODO(verify)。{t.disclaimer}
              </Callout>
              <p className="page-note-sm"><Wifi size={13} aria-hidden="true" /> 网络能力默认关闭；开启后仅用于只读行情与公开数据导入，绝不用于交易。</p>
              <p className="page-note-sm"><Database size={13} aria-hidden="true" /> 合成数据均标注 SYNTHETIC；历史表现不代表未来，不构成投资建议。</p>
            </div>
          </Panel>
        </div>
      </div>
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
