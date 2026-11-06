import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const token = process.env.QC_E2E_TOKEN || "test-token";
const headers = { Authorization: `Bearer ${token}` };

test("historical account explains cash, share and pending-order adjustments", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.addInitScript((value) => {
    localStorage.setItem("qc_token", value);
    localStorage.removeItem("qc_api");
    localStorage.setItem("qc_beginner", "0");
  }, token);
  const imported = await request.post("/api/data/update", { headers, data: {
    provider: "local", local_dir: resolve(process.cwd(), "../tests/fixtures/paper-corporate"),
    start: "2026-01-05", end: "2026-01-08", reset: true, incremental: false, build_snapshot: true,
  } });
  expect(imported.status()).toBe(202);
  const jobId = (await imported.json()).job_id;
  let job;
  for (let index = 0; index < 300; index += 1) {
    job = await (await request.get(`/api/jobs/${jobId}`, { headers })).json();
    if (["done", "failed", "cancelled"].includes(job.status)) break;
    await new Promise((done) => setTimeout(done, 100));
  }
  expect(job.status).toBe("done");
  expect(job.result.synthetic).toBe(true);
  const created = await request.post("/api/paper/sessions", { headers, data: {
    snapshot: job.result.snapshot_id, initial_cash: 10000, name: "公司行为验收",
  } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id;
  const base = `/api/paper/sessions/${id}`;
  expect((await request.post(`${base}/orders`, { headers, data: { code: "600000", side: "buy", qty: 500 } })).status()).toBe(200);
  expect((await request.post(`${base}/step`, { headers, data: { days: 1 } })).ok()).toBeTruthy();
  expect((await request.post(`${base}/orders`, { headers, data: { code: "600000", side: "buy", qty: 100, order_type: "limit", limit_price: 1 } })).status()).toBe(200);
  const adjusted = await request.post(`${base}/step`, { headers, data: { days: 1 } });
  const detail = await adjusted.json();
  expect(detail.corporate_events[0]).toMatchObject({ cash: 250, qty_before: 500, qty_after: 1000 });
  await page.goto("/paper");
  await page.getByRole("button", { name: /^公司行为验收/ }).filter({ hasText: id.slice(0, 14) }).click();
  const events = page.getByRole("list", { name: "公司行为调整记录" });
  await expect(events).toContainText("现金变化 +¥250.00");
  await expect(events).toContainText("股数 500 → 1,000");
  await events.getByText("已撤销 1 笔相关委托").click();
  await expect(events).toContainText("未成交部分已撤销");
  await page.getByText("公司行为调整", { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/qc-paper-corporate.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByText("公司行为调整", { exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-paper-corporate-mobile.png" });
  expect(errors).toEqual([]);
});
