import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import "../monaco";
import { Play, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Template } from "../api/types";
import StatePanel from "../components/StatePanel";
import { zhCN as t } from "../i18n/zh-CN";

function defaults(template: Template | undefined): Record<string, unknown> {
  const output: Record<string, unknown> = {};
  for (const [key, spec] of Object.entries(template?.params_schema.properties || {})) {
    if (spec.default !== undefined) output[key] = spec.default;
  }
  return output;
}

export default function StrategyPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [validation, setValidation] = useState("");
  const [valid, setValid] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const template = useMemo(() => templates.find((item) => item.id === selected), [templates, selected]);

  useEffect(() => {
    api.templates().then((items) => {
      setTemplates(items);
      if (items[0]) { setSelected(items[0].id); setParamsText(JSON.stringify(defaults(items[0]), null, 2)); }
    }).catch((e) => setError(`${e}`));
  }, []);
  useEffect(() => {
    if (template) { setParamsText(JSON.stringify(defaults(template), null, 2)); setValid(null); setValidation(""); }
  }, [template]);

  const parseParams = () => {
    try { return JSON.parse(paramsText) as Record<string, unknown>; } catch (e) { throw new Error(`参数 JSON 无效：${e}`); }
  };
  const validate = async () => {
    setError(""); setValidation("");
    try {
      const result = await api.validateStrategy(selected, parseParams());
      setValid(result.valid);
      setValidation(result.valid ? "参数通过校验" : JSON.stringify(result.errors, null, 2));
    } catch (e) { setError(`${e}`); }
  };
  const run = () => {
    try {
      const params = parseParams();
      navigate(`/backtest?template=${encodeURIComponent(selected)}&params=${encodeURIComponent(JSON.stringify(params))}`);
    } catch (e) { setError(`${e}`); }
  };

  return (
    <>
      <div className="page-head"><div><h1>策略</h1><p>模板 · JSON Schema 参数 · 校验 · 版本与运行</p></div>
        <div className="button-row"><button className="btn" onClick={() => void validate()}><ShieldCheck size={15} /> 校验参数</button><button className="btn primary" onClick={run}><Play size={15} /> 运行回测</button></div>
      </div>
      <div className="grid strategy-layout">
        <div className="card template-list">
          <h3>内置模板</h3>
          {templates.map((item) => <button key={item.id} className={`template-item ${selected === item.id ? "active" : ""}`} onClick={() => setSelected(item.id)}><strong>{item.id}</strong><span>{item.description}</span></button>)}
          {!templates.length ? <StatePanel loading /> : null}
        </div>
        <div className="card">
          <div className="card-head"><h3>{selected || "策略"}</h3>{valid === true ? <span className="badge success">参数有效</span> : valid === false ? <span className="badge danger">参数无效</span> : null}</div>
          <p className="muted small">{template?.description}</p>
          <label className="field-label">参数 JSON（保存到实验元数据）</label>
          <div className="editor-frame">
            <Editor height="280px" defaultLanguage="json" value={paramsText} onChange={(value) => setParamsText(value || "{}")} options={{ minimap: { enabled: false }, fontSize: 13, automaticLayout: true, scrollBeyondLastLine: false }} />
          </div>
          {validation ? <pre className={`validation ${valid ? "success" : "error"}`}>{validation}</pre> : null}
          {error ? <p className="error">{error}</p> : null}
        </div>
      </div>
      <p className="muted small">{t.disclaimer}</p>
    </>
  );
}
