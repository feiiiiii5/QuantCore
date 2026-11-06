/** UI-API v2 core payload types. */

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface JsonSchema {
  title?: string;
  description?: string;
  type?: string;
  default?: unknown;
  enum?: unknown[];
  minimum?: number;
  maximum?: number;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
}

export interface Health {
  status: string;
  version: string;
  engine_backend: string;
  engine_available: boolean;
  panel_available: boolean;
  synthetic_only: boolean;
  cors: boolean;
}

export type DoctorCheckStatus = "pass" | "warn" | "fail" | "skip";

export type DoctorOverallStatus = "ok" | "warn" | "fail";

export interface DoctorCheck {
  id: string;
  title: string;
  status: DoctorCheckStatus;
  detail: string;
  hint: string;
  required: boolean;
}

export interface DoctorCounts {
  pass: number;
  warn: number;
  fail: number;
  skip: number;
}

/** Read-only local environment self-check (GET /api/doctor). */
export interface DoctorReport {
  status: DoctorOverallStatus;
  generated_at: string;
  version: string;
  engine_backend: string;
  engine_available: boolean;
  panel_available: boolean;
  root: string;
  counts: DoctorCounts;
  checks: DoctorCheck[];
}

export interface Meta {
  version: string;
  engine_backend: string;
  synthetic_only: boolean;
  data_root: string;
  snapshots_root: string;
  experiments_root: string;
  token_required: boolean;
  ui_served: boolean;
  cors: boolean;
}
