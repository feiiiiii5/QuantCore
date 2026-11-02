import { describe, expect, it } from "vitest";
import {
  doctorCheckLabel,
  doctorCountsSummary,
  doctorOverallBadge,
  doctorOverallLabel,
  doctorStatusColor,
  doctorSummary,
} from "./doctor";

describe("doctor helpers", () => {
  it("labels check and overall statuses in Chinese", () => {
    expect(doctorCheckLabel("pass")).toBe("通过");
    expect(doctorCheckLabel("warn")).toBe("警告");
    expect(doctorCheckLabel("fail")).toBe("失败");
    expect(doctorCheckLabel("skip")).toBe("跳过");
    expect(doctorCheckLabel("unknown")).toBe("unknown");
    expect(doctorOverallLabel("ok")).toBe("通过");
    expect(doctorOverallLabel("warn")).toBe("有警告");
    expect(doctorOverallLabel("fail")).toBe("有失败");
  });

  it("maps status colours and badge classes", () => {
    expect(doctorStatusColor("pass")).toBe("var(--success)");
    expect(doctorStatusColor("warn")).toBe("#d97706");
    expect(doctorStatusColor("fail")).toBe("var(--up)");
    expect(doctorStatusColor("nope")).toBe("var(--muted)");
    expect(doctorOverallBadge("ok")).toBe("badge success");
    expect(doctorOverallBadge("warn")).toBe("badge");
    expect(doctorOverallBadge("fail")).toBe("badge danger");
  });

  it("summarises counts and overall status", () => {
    const counts = { pass: 12, warn: 1, fail: 0, skip: 2 };
    expect(doctorCountsSummary(counts)).toBe("通过 12 · 警告 1 · 失败 0 · 跳过 2");
    expect(doctorSummary({ status: "warn", counts })).toBe("有警告 · 通过 12 · 警告 1 · 失败 0 · 跳过 2");
  });
});
