import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { Play, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTemplates, useValidateStrategy } from "../api/queries";
import type { Template } from "../api/types";
import ParamForm, { defaultsFromSchema } from "../components/ParamForm";
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
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
