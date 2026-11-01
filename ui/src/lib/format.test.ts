import { describe, expect, it } from "vitest";
import { bytes, csvEscape, dateInt, fixedToYuan, money, monthKey, num, pct, signedPct, toCsv } from "./format";

describe("format helpers", () => {
  it("formats money and units", () => {
    expect(money(12345.6)).toBe("¥12,345.60");
    expect(fixedToYuan(123456)).toBe(12.3456);
    expect(pct(0.12345)).toBe("12.35%");
    expect(signedPct(0.01)).toBe("+1.00%");
    expect(num(1000, 0)).toBe("1,000");
  });
  it("formats dates and bytes", () => {
    expect(dateInt(20240105)).toBe("2024-01-05");
    expect(monthKey(20240105)).toBe("2024-01");
    expect(bytes(1536)).toBe("1.5 KB");
    expect(bytes(2_000_000)).toBe("2.0 MB");
  });
  it("escapes csv", () => {
    expect(csvEscape('a,b')).toBe('"a,b"');
    expect(csvEscape('a"b')).toBe('"a""b"');
    expect(toCsv([{ code: "000001", name: "a,b" }], ["code", "name"])).toBe('code,name\n000001,"a,b"');
  });
});
