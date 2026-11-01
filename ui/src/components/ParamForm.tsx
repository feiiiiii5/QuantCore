import type { JsonSchema } from "../api/types";

interface Props {
  schema: JsonSchema | undefined;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  disabled?: boolean;
}

type FieldKind = "number" | "integer" | "boolean" | "string" | "enum" | "array" | "unknown";

function enumValues(schema: JsonSchema): unknown[] | null {
  if (Array.isArray(schema.enum)) return schema.enum;
  for (const candidate of schema.anyOf ?? []) {
    if (Array.isArray(candidate.enum)) return candidate.enum;
  }
  return null;
}

function fieldKind(schema: JsonSchema): FieldKind {
  if (enumValues(schema)) return "enum";
  const types = [schema.type, ...(schema.anyOf ?? []).map((item) => item.type)]
    .filter((type): type is string => Boolean(type) && type !== "null");
  const type = types[0];
  if (type === "number" || type === "integer" || type === "boolean" || type === "string" || type === "array") return type;
  return "unknown";
}

export function defaultsFromSchema(schema: JsonSchema | undefined): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(schema?.properties ?? {})) {
    if (field.default !== undefined) result[key] = field.default;
  }
  return result;
}

export default function ParamForm({ schema, value, onChange, disabled }: Props) {
  const properties = Object.entries(schema?.properties ?? {});
  if (!properties.length) return <p className="muted small">该模板没有可调参数，直接运行即可。</p>;
  const required = new Set(schema?.required ?? []);
  const update = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  return (
    <div className="param-form">
      {properties.map(([key, field]) => {
        const kind = fieldKind(field);
        const current = value[key];
        const label = field.title || key;
        const id = `param-${key}`;
        return (
          <label className="param-field" key={key} htmlFor={id}>
            <span>{label}{required.has(key) ? <em className="required">*</em> : null}</span>
            {kind === "boolean" ? (
              <input id={id} type="checkbox" checked={current === true} onChange={(event) => update(key, event.target.checked)} disabled={disabled} />
            ) : kind === "enum" ? (
              <select id={id} value={current == null ? "" : String(current)} onChange={(event) => {
                const match = enumValues(field)?.find((option) => String(option) === event.target.value);
                update(key, match ?? event.target.value);
              }} disabled={disabled}>
                {current == null ? <option value="">未设置</option> : null}
                {enumValues(field)?.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}
              </select>
            ) : kind === "number" || kind === "integer" ? (
              <input
                id={id}
                type="number"
                value={typeof current === "number" ? current : ""}
                min={field.minimum}
                max={field.maximum}
                step={kind === "integer" ? 1 : "any"}
                onChange={(event) => update(key, event.target.value === "" ? null : Number(event.target.value))}
                disabled={disabled}
              />
            ) : kind === "array" ? (
              <textarea
                id={id}
                rows={2}
                value={Array.isArray(current) ? JSON.stringify(current) : ""}
                onChange={(event) => {
                  try { update(key, JSON.parse(event.target.value) as unknown); } catch { update(key, event.target.value.split(",").map((item) => item.trim()).filter(Boolean)); }
                }}
                disabled={disabled}
              />
            ) : (
              <input id={id} value={current == null ? "" : String(current)} onChange={(event) => update(key, event.target.value)} disabled={disabled} />
            )}
            {field.description ? <small>{field.description}</small> : null}
          </label>
        );
      })}
    </div>
  );
}
