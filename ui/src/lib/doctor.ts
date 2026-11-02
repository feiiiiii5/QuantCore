import type { DoctorReport } from "../api/types";

export type DoctorCheckStatus = "pass" | "warn" | "fail" | "skip";
export type DoctorOverallStatus = "ok" | "warn" | "fail";

const CHECK_LABELS: Record<DoctorCheckStatus, string> = {
  pass: "通过",
  warn: "警告",
  fail: "失败",
  skip: "跳过",
};

const OVERALL_LABELS: Record<DoctorOverallStatus, string> = {
  ok: "通过",
  warn: "有警告",
  fail: "有失败",
};

const CHECK_COLORS: Record<DoctorCheckStatus, string> = {
  pass: "var(--success)",
  warn: "#d97706",
  fail: "var(--up)",
  skip: "var(--muted)",
};

const OVERALL_BADGES: Record<DoctorOverallStatus, string> = {
  ok: "badge success",
  warn: "badge",
  fail: "badge danger",
};

/** Chinese label for one check status; unknown values fall back to the raw status. */
export function doctorCheckLabel(status: string): string {
  return CHECK_LABELS[status as DoctorCheckStatus] ?? status;
}

/** Chinese label for the aggregate report status (ok/warn/fail). */
export function doctorOverallLabel(status: string): string {
  return OVERALL_LABELS[status as DoctorOverallStatus] ?? status;
}

/** Icon colour per check status (pass/warn/fail/skip). */
export function doctorStatusColor(status: string): string {
  return CHECK_COLORS[status as DoctorCheckStatus] ?? "var(--muted)";
}

/** Existing badge classes used for the aggregate status. */
export function doctorOverallBadge(status: string): string {
  return OVERALL_BADGES[status as DoctorOverallStatus] ?? "badge";
}

/** One-line counts summary, e.g. "通过 12 · 警告 1 · 失败 0 · 跳过 2". */
export function doctorCountsSummary(counts: DoctorReport["counts"]): string {
  return `通过 ${counts.pass} · 警告 ${counts.warn} · 失败 ${counts.fail} · 跳过 ${counts.skip}`;
}

/** Aggregate summary for the card header. */
export function doctorSummary(report: Pick<DoctorReport, "status" | "counts">): string {
  return `${doctorOverallLabel(report.status)} · ${doctorCountsSummary(report.counts)}`;
}
