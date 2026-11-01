import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { Play, RefreshCw, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { usePlugins, useRunPlugin, useTemplates, useValidatePlugin, useValidateStrategy } from "../api/queries";
import type { PluginInfo, Template } from "../api/types";
import ParamForm, { defaultsFromSchema } from "../components/ParamForm";
import { useJobProgress } from "../hooks/useJobProgress";
import { notify } from "../lib/notify";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";
import "../monaco";

export default function StrategyPage() {
  const templates = useTemplates();
  const validate = useValidateStrategy();
  const navigate = useNavigate();
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [jsonText, setJsonText] = useState("{}");
  const [jsonError, setJsonError] = useState("");
  const [mode, setMode] = useState<"form" | "json">("form");
  const plugins = usePlugins();
  const validatePlugin = useValidatePlugin();
  const runPlugin = useRunPlugin();
  const [pluginName, setPluginName] = useState("");
  const [pluginParams, setPluginParams] = useState("{}");
  const [pluginJobId, setPluginJobId] = useState<string | null>(null);
  const pluginJob = useJobProgress(pluginJobId);
  const template = useMemo(() => templates.data?.find((item) => item.id === selected), [templates.data, selected]);

  useEffect(() => {
    const first = templates.data?.[0];
    if (!selected && first) setSelected(first.id);
  }, [selected, templates.data]);
  useEffect(() => {
    if (!template) return;
    const defaults = defaultsFromSchema(template.params_schema);
    setParams(defaults);
    setJsonText(JSON.stringify(defaults, null, 2));
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

  return (
    <>
      <div className="page-head">
        <div><h1>策略</h1><p>模板 · JSON Schema 自动表单 · Monaco · 参数校验 · 版本与运行</p></div>
        <div className="button-row"><button className="btn" onClick={onValidate} disabled={!selected || validate.isPending}><ShieldCheck size={15} /> {validate.isPending ? "校验中…" : "校验参数"}</button><button className="btn primary" onClick={run} disabled={!selected}><Play size={15} /> 运行回测</button></div>
      </div>
      {templates.isLoading ? <StatePanel loading /> : templates.error ? <StatePanel error={templates.error.message} onRetry={() => void templates.refetch()} /> : (
        <div className="grid strategy-layout">
          <div className="card template-list">
            <h3>内置模板 <span className="muted small">{templates.data?.length ?? 0}</span></h3>
            {(templates.data ?? []).map((item: Template) => (
              <button key={item.id} className={`template-item ${selected === item.id ? "active" : ""}`} onClick={() => setSelected(item.id)}>
                <strong>{item.name || item.id}</strong><span>{item.description}</span>
              </button>
            ))}
          </div>
          <div className="card">
            <div className="card-head"><h3>{template?.name || template?.id || "策略"}</h3>{validate.data?.valid === true ? <span className="badge success">参数有效</span> : validate.data && !validate.data.valid ? <span className="badge danger">参数无效</span> : null}</div>
            <p className="muted small">{template?.description}</p>
            <div className="tabs compact-tabs" role="tablist">
              <button role="tab" aria-selected={mode === "form"} className={mode === "form" ? "active" : ""} onClick={() => setMode("form")}>表单</button>
              <button role="tab" aria-selected={mode === "json"} className={mode === "json" ? "active" : ""} onClick={() => setMode("json")}>JSON</button>
            </div>
            {mode === "form" ? <ParamForm schema={template?.params_schema} value={params} onChange={updateParams} /> : (
              <div className="editor-frame"><Editor height="280px" defaultLanguage="json" value={jsonText} onChange={(value) => updateJson(value ?? "{}")} options={{ minimap: { enabled: false }, fontSize: 13, automaticLayout: true, scrollBeyondLastLine: false }} /></div>
            )}
            {jsonError ? <p className="error">JSON：{jsonError}</p> : null}
            {validate.error ? <p className="error">{validate.error.message}</p> : null}
            {validate.data && !validate.data.valid ? <pre className="validation error">{JSON.stringify(validate.data.errors, null, 2)}</pre> : null}
            {validate.data?.valid ? <p className="success-text">参数通过 pydantic schema 校验；默认值可继续调整。</p> : null}
          </div>
        </div>
      )}
      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head"><h3>本地策略插件 <span className="muted small">{plugins.data?.length ?? 0} 个 · data/strategies/*.py</span></h3><button className="btn ghost" onClick={() => void plugins.refetch()}><RefreshCw size={14} /> 刷新</button></div>
        <p className="muted small">放在本机 data/strategies/*.py 的策略模块；静态 AST 审计通过后可提交到后台任务运行。插件仅本机执行，不是安全沙箱，不要放不可信代码；不联网、不产生真实委托。</p>
        {plugins.error ? <p className="error">{plugins.error.message}</p> : null}
        <div className="grid two-col" style={{ marginTop: 8 }}>
          <div className="template-list">
            {(plugins.data ?? []).map((item: PluginInfo) => (
              <button key={item.name} className={`template-item ${pluginName === item.name ? "active" : ""}`} onClick={() => { setPluginName(item.name); validatePlugin.reset(); }}>
                <strong>{item.name} <span className={item.valid ? "badge success" : "badge danger"}>{item.valid ? "通过审计" : "审计失败"}</span></strong>
                <span>{item.description || item.interface}</span>
                <small className="muted">{item.version ? `v${item.version} · ` : ""}{item.bytes} bytes</small>
              </button>
            ))}
            {!plugins.isLoading && !(plugins.data ?? []).length ? <p className="muted small">暂无插件。把合法策略 .py 放到 data/strategies/ 后刷新（例如实现 Strategy 子类或 create_strategy()）。</p> : null}
          </div>
          <div>
            {selectedPlugin ? (
              <>
                <div className="card-head"><h3>{selectedPlugin.name}</h3><span className="muted small">{selectedPlugin.interface}</span></div>
                {selectedPlugin.issues.length ? <pre className="validation error">{selectedPlugin.issues.map((issue) => `L${issue.line}: ${issue.message}`).join("\n")}</pre> : null}
                <label className="field-label">插件参数 JSON（当前记录到实验 metadata；插件自身参数请用默认值/PLUGIN_INFO）</label>
                <textarea className="code-input" rows={3} value={pluginParams} onChange={(event) => setPluginParams(event.target.value)} spellCheck={false} />
                <div className="button-row" style={{ marginTop: 8 }}>
                  <button className="btn" disabled={validatePlugin.isPending} onClick={() => validatePlugin.mutate(selectedPlugin.name)}><ShieldCheck size={15} /> {validatePlugin.isPending ? "审计中…" : "审计"}</button>
                  <button className="btn primary" disabled={!selectedPlugin.valid || runPlugin.isPending} onClick={runLocalPlugin}><Play size={15} /> {runPlugin.isPending ? "提交中…" : "运行插件回测"}</button>
                </div>
                {validatePlugin.data ? <p className={validatePlugin.data.valid ? "success-text" : "error"}>{validatePlugin.data.valid ? "静态审计通过，可提交回测。" : `审计失败：${validatePlugin.data.issues.length} 个问题`}</p> : null}
                {runPlugin.error ? <p className="error">{runPlugin.error.message}</p> : null}
                {pluginJobId ? <div className="progress"><div className="progress-bar" style={{ width: `${Math.round((pluginJob.job?.progress || 0) * 100)}%` }} /><span>{pluginJob.job?.status ?? "pending"} · {Math.round((pluginJob.job?.progress || 0) * 100)}%</span></div> : null}
              </>
            ) : <StatePanel empty emptyHint="从左侧选择插件；或添加本地 .py 策略模块。" />}
          </div>
        </div>
      </div>
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
