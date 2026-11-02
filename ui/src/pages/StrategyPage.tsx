import { useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { Braces, Play, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useOnboardingPresets, usePlugins, useRunPlugin, useTemplates, useValidatePlugin, useValidateStrategy } from "../api/queries";
import type { PluginInfo, StrategyPreset, Template } from "../api/types";
import {
  Badge, Button, Callout, EmptyState, List, ListRow, PageHeader, Panel, ParamForm, ProgressBar, Sheet, Skeleton,
  Tag, Textarea, defaultsFromSchema,
} from "../components";
import { useJobProgress } from "../hooks/useJobProgress";
import { notify } from "../lib/notify";
import { setBeginner, useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "../monaco";
import "./pages.css";

export default function StrategyPage() {
  const templates = useTemplates();
  const validate = useValidateStrategy();
  const navigate = useNavigate();
  const beginner = useBeginner();
  const presets = useOnboardingPresets();
  const presetParamsRef = useRef<Record<string, unknown> | null>(null);
  const [selected, setSelected] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [jsonText, setJsonText] = useState("{}");
  const [jsonError, setJsonError] = useState("");
  const [jsonOpen, setJsonOpen] = useState(false);
  const plugins = usePlugins();
  const validatePlugin = useValidatePlugin();
  const runPlugin = useRunPlugin();
  const [pluginName, setPluginName] = useState("");
  const [pluginParams, setPluginParams] = useState("{}");
  const [pluginJobId, setPluginJobId] = useState<string | null>(null);
  const pluginJob = useJobProgress(pluginJobId);
  const template = useMemo(() => templates.data?.find((item) => item.id === selected), [templates.data, selected]);
  const activePreset = useMemo(() => presets.data?.find((item) => item.id === selectedPreset) ?? null, [presets.data, selectedPreset]);

  useEffect(() => {
    const first = templates.data?.[0];
    if (!selected && first) setSelected(first.id);
  }, [selected, templates.data]);
  useEffect(() => {
    if (!template) return;
    const next = presetParamsRef.current ?? defaultsFromSchema(template.params_schema);
    presetParamsRef.current = null;
    setParams(next);
    setJsonText(JSON.stringify(next, null, 2));
    setJsonError("");
    validate.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template]);
  useEffect(() => {
    if (!pluginName && plugins.data?.length) setPluginName(plugins.data[0].name);
  }, [pluginName, plugins.data]);
  useEffect(() => {
    if (pluginJob.job?.status === "done") {
      const runId = typeof pluginJob.job.result?.run_id === "string" ? pluginJob.job.result.run_id : "";
      notify({ title: "插件回测完成", body: runId ? `实验 ${runId.slice(-8)}` : "结果已写入实验", kind: "success" });
      if (runId) navigate(`/experiments?run=${encodeURIComponent(runId)}`);
    }
  }, [pluginJob.job, navigate]);
  const selectedPlugin = plugins.data?.find((item) => item.name === pluginName) ?? null;
  const runLocalPlugin = () => {
    if (!selectedPlugin) return;
    setJsonError("");
    try {
      const parsed: unknown = JSON.parse(pluginParams);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("插件参数必须是 JSON 对象");
      runPlugin.mutate({ name: selectedPlugin.name, payload: { params: parsed } }, { onSuccess: (accepted) => setPluginJobId(accepted.job_id) });
    } catch (error) { setJsonError(error instanceof Error ? error.message : "插件参数 JSON 无效"); }
  };
  const updateParams = (next: Record<string, unknown>) => { setParams(next); setJsonText(JSON.stringify(next, null, 2)); setJsonError(""); };
  const updateJson = (text: string) => {
    setJsonText(text);
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("参数必须是 JSON 对象");
      setParams(parsed as Record<string, unknown>);
      setJsonError("");
    } catch (error) { setJsonError(error instanceof Error ? error.message : "JSON 无效"); }
  };
  const onValidate = () => {
    if (!selected) return;
    validate.mutate({ template: selected, params });
  };
  const run = () => {
    try {
      const parsed: unknown = JSON.parse(jsonText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("参数必须是 JSON 对象");
      navigate(`/backtest?template=${encodeURIComponent(selected)}&params=${encodeURIComponent(JSON.stringify(parsed))}`);
    } catch (error) { setJsonError(error instanceof Error ? error.message : "JSON 无效"); }
  };
  const applyPreset = (preset: StrategyPreset) => {
    presetParamsRef.current = preset.template === selected ? null : (preset.params ?? {});
    setSelectedPreset(preset.id);
    setSelected(preset.template);
    setParams(preset.params ?? {});
    setJsonText(JSON.stringify(preset.params ?? {}, null, 2));
    setJsonError("");
    validate.reset();
  };

  return (
    <div className="page">
      <PageHeader
        title="策略"
        subtitle="从白话模板开始，理解风险与适合人群；校验参数后直接回测。"
        actions={(
          <>
            <Button variant="secondary" icon={ShieldCheck} loading={validate.isPending} disabled={!selected} onClick={onValidate}>{validate.isPending ? "校验中…" : "校验参数"}</Button>
            <Button variant="primary" icon={Play} disabled={!selected} onClick={run}>运行回测</Button>
          </>
        )}
      />

      {templates.isLoading ? <Skeleton rows={4} /> : templates.error ? (
        <EmptyState title="策略模板加载失败" hint={templates.error.message} action={<Button variant="secondary" onClick={() => void templates.refetch()}>重试</Button>} />
      ) : !templates.data?.length ? <EmptyState title="没有可用模板" hint="检查后端 /api/strategies/templates。" /> : (
        <div className="stack">
          <Panel title="策略模板（白话版）" subtitle={presets.data?.length ? `${presets.data.length} 个预设 · 白话说明 + 风险 + 适合人群` : "预设加载中；也可用下方内置模板"} actions={presets.isError ? <Badge tone="warn">预设加载失败，可用内置模板</Badge> : null}>
            {presets.isLoading ? <Skeleton rows={3} /> : presets.data?.length ? (
              <div className="grid grid-3">
                {presets.data.map((preset) => (
                  <button key={preset.id} type="button" className="template-card" aria-pressed={selectedPreset === preset.id} onClick={() => applyPreset(preset)}>
                    <span className="template-name">{preset.name}</span>
                    <span className="template-desc">{preset.tagline}。{preset.description}</span>
                    <span className="template-meta">适合：{preset.suitable_for} · 周期 {preset.horizon}</span>
                    <span className="template-foot">
                      <Badge tone={selectedPreset === preset.id ? "info" : "neutral"}>{selectedPreset === preset.id ? "已选择" : preset.template}</Badge>
                    </span>
                    <span className="template-risk">风险：{preset.risk_note}</span>
                  </button>
                ))}
              </div>
            ) : <p className="page-note-sm">预设暂不可用；用下面的「内置模板」继续。</p>}
          </Panel>

          <Panel title="内置模板" subtitle={`${templates.data.length} 个 · 原始模板与参数 schema`} actions={<span className="page-note-sm">点击切换</span>}>
            <div className="row">
              {templates.data.map((item: Template) => (
                <Tag key={item.id} active={selected === item.id && !selectedPreset} onClick={() => { presetParamsRef.current = null; setSelectedPreset(""); setSelected(item.id); }}>{item.name || item.id}</Tag>
              ))}
            </div>
          </Panel>

          <Panel
            title={activePreset?.name || template?.name || template?.id || "策略参数"}
            subtitle={activePreset ? `${activePreset.tagline} · 适合：${activePreset.suitable_for}` : template?.description || "选择模板后编辑参数"}
            actions={(
              <>
                {validate.data?.valid === true ? <Badge tone="ok">参数有效</Badge> : validate.data && !validate.data.valid ? <Badge tone="danger">参数无效</Badge> : null}
                {!beginner ? <Button variant="ghost" size="sm" icon={Braces} onClick={() => setJsonOpen(true)}>编辑 JSON</Button> : null}
              </>
            )}
          >
            <div className="stack">
              <ParamForm schema={template?.params_schema} value={params} onChange={updateParams} />
              {jsonError ? <p className="error-text">JSON：{jsonError}</p> : null}
              {validate.error ? <p className="error-text">{validate.error.message}</p> : null}
              {validate.data && !validate.data.valid ? <pre className="quality-json">{JSON.stringify(validate.data.errors, null, 2)}</pre> : null}
              {validate.data?.valid ? <Callout tone="success" title="参数通过 schema 校验">可以点右上角「运行回测」；费用/成交/风险等执行配置在回测页设置。</Callout> : null}
              <p className="page-note-sm">参数只影响策略逻辑；执行配置（费用/成交/风险）在回测页设置。{beginner ? " 新手模式已隐藏 JSON 编辑与插件入口，可在设置中切换专业模式。" : ""}</p>
            </div>
          </Panel>

          {beginner ? (
            <Panel title="专业入口" subtitle="Monaco JSON 编辑与本地策略插件在专业模式显示">
              <div className="stack">
                <p className="page-note">本地插件 <span className="mono">data/strategies/*.py</span> 仅本机执行、不联网、不产生真实委托；静态审计通过后可提交回测。</p>
                <div><Button variant="secondary" icon={Sparkles} onClick={() => setBeginner(false)}>切换到专业模式</Button></div>
              </div>
            </Panel>
          ) : (
            <Panel
              title="本地策略插件"
              subtitle={`${plugins.data?.length ?? 0} 个 · data/strategies/*.py · 仅本机执行，不是安全沙箱`}
              actions={<Button variant="ghost" size="sm" icon={RefreshCw} onClick={() => void plugins.refetch()}>刷新</Button>}
            >
              <div className="stack">
                <Callout tone="warn" title="仅本机运行">插件不要放不可信代码；不联网、不产生真实委托。静态 AST 审计通过后可提交到后台任务。</Callout>
                {plugins.error ? <p className="error-text">{plugins.error.message}</p> : null}
                <div className="grid grid-2">
                  <List inset>
                    {(plugins.data ?? []).map((item: PluginInfo) => (
                      <ListRow
                        key={item.name}
                        title={<>{item.name} <Badge tone={item.valid ? "ok" : "danger"}>{item.valid ? "通过审计" : "审计失败"}</Badge></>}
                        subtitle={item.description || item.interface}
                        selected={pluginName === item.name}
                        onClick={() => { setPluginName(item.name); validatePlugin.reset(); }}
                      />
                    ))}
                    {!plugins.isLoading && !(plugins.data ?? []).length ? <ListRow title="暂无插件" subtitle="把合法策略 .py 放到 data/strategies/ 后刷新（例如实现 Strategy 子类或 create_strategy()）" /> : null}
                  </List>
                  <div className="stack">
                    {selectedPlugin ? (
                      <>
                        <div className="row-between">
                          <div><div className="switch-title">{selectedPlugin.name}</div><div className="switch-desc">{selectedPlugin.interface}</div></div>
                          <Badge tone={selectedPlugin.valid ? "ok" : "danger"}>{selectedPlugin.valid ? "通过审计" : "审计失败"}</Badge>
                        </div>
                        {selectedPlugin.issues.length ? <pre className="quality-json">{selectedPlugin.issues.map((issue) => `L${issue.line}: ${issue.message}`).join("\n")}</pre> : null}
                        <label className="field-label" htmlFor="plugin-params">插件参数 JSON（记录到实验 metadata；插件自身参数请用默认值/PLUGIN_INFO）</label>
                        <Textarea id="plugin-params" rows={3} value={pluginParams} onChange={(event) => setPluginParams(event.target.value)} spellCheck={false} />
                        <div className="row">
                          <Button variant="secondary" icon={ShieldCheck} loading={validatePlugin.isPending} onClick={() => validatePlugin.mutate(selectedPlugin.name)}>{validatePlugin.isPending ? "审计中…" : "审计"}</Button>
                          <Button variant="primary" icon={Play} loading={runPlugin.isPending} disabled={!selectedPlugin.valid} onClick={runLocalPlugin}>{runPlugin.isPending ? "提交中…" : "运行插件回测"}</Button>
                        </div>
                        {validatePlugin.data ? <p className={validatePlugin.data.valid ? "success-text" : "error-text"}>{validatePlugin.data.valid ? "静态审计通过，可提交回测。" : `审计失败：${validatePlugin.data.issues.length} 个问题`}</p> : null}
                        {runPlugin.error ? <p className="error-text">{runPlugin.error.message}</p> : null}
                        {pluginJobId ? <ProgressBar value={Math.round((pluginJob.job?.progress ?? 0) * 100)} label={pluginJob.job?.status ?? "pending"} /> : null}
                      </>
                    ) : <EmptyState title="还没有选择插件" hint="从左侧选择插件；或把本地 .py 策略模块放到 data/strategies/ 后刷新。" />}
                  </div>
                </div>
              </div>
            </Panel>
          )}
        </div>
      )}

      <Sheet open={jsonOpen} onOpenChange={setJsonOpen} side="right" title="策略参数 JSON" description={template?.id ? `模板 ${template.id} · 保存后同步到表单` : undefined} footer={<Button variant="primary" onClick={() => setJsonOpen(false)}>完成</Button>}>
        <div className="stack">
          {jsonError ? <p className="error-text">JSON：{jsonError}</p> : null}
          <div className="json-editor-frame">
            <Editor height="380px" defaultLanguage="json" value={jsonText} onChange={(value) => updateJson(value ?? "{}")} options={{ minimap: { enabled: false }, fontSize: 13, automaticLayout: true, scrollBeyondLastLine: false }} />
          </div>
        </div>
      </Sheet>

      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
