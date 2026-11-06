import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const token = process.env.QC_E2E_TOKEN || "test-token";
const AUTH = { Authorization: "Bearer " + token };

interface PrepareOptions { beginner?: boolean; theme?: "light" | "dark" }

async function prepare(page: Page, options: PrepareOptions = {}) {
  const beginner = options.beginner ?? false;
  await page.addInitScript(
    ({ value, beginnerMode, theme }) => {
      localStorage.setItem("qc_token", value);
      localStorage.removeItem("qc_api");
      localStorage.setItem("qc_theme", theme);
      localStorage.setItem("qc_density", "comfortable");
      localStorage.setItem("qc_beginner", beginnerMode ? "1" : "0");
    },
    { value: token, beginnerMode: beginner, theme: options.theme ?? "light" },
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push("pageerror: " + error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push("console: " + message.text());
  });
  return errors;
}

async function bootstrap(request: APIRequestContext, nSec = 30, seed = 41) {
  const response = await request.post("/api/onboarding/bootstrap", {
    headers: AUTH,
    data: { n_sec: nSec, start: "2023-01-03", end: "2024-12-31", seed },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

/** Create one real experiment through the job queue (used by experiments/research tests). */
async function createExperiment(request: APIRequestContext): Promise<string> {
  const response = await request.post("/api/backtest", {
    headers: AUTH,
    data: { template: "momentum", params: { top_n: 5, lookback: 60 } },
  });
  expect(response.status()).toBe(202);
  const jobId = String((await response.json()).job_id);
  for (let i = 0; i < 240; i += 1) {
    const status = await request.get("/api/jobs/" + jobId, { headers: AUTH });
    const payload = await status.json();
    if (payload.status === "done") {
      const full = await request.get("/api/jobs/" + jobId + "/result", { headers: AUTH });
      const result = await full.json();
      return String(result.result?.run_id ?? payload.result?.run_id ?? "");
    }
    if (payload.status === "failed") throw new Error("backtest job failed: " + payload.error);
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error("backtest job did not finish");
}

test("cost scenarios preserve fractional multipliers through native backtests", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  const runId = await createExperiment(request);
  const experiment = await request.get(`/api/experiments/${runId}/result`, { headers: AUTH });
  expect((await experiment.json()).engine_backend).toBe("cpp");
  await page.goto(`/experiments?run=${encodeURIComponent(runId)}`);
  await page.getByRole("link", { name: "继续研究" }).click();
  await expect(page).toHaveURL(new RegExp(`/research\\?run=${runId}`));
  const table = page.getByRole("table", { name: "成本情景指标", exact: true });
  for (const multipliers of [[0, 0.5, 1, 2, 3], [0.25, 0.5, 1.5], [0.5]]) {
    if (multipliers.length !== 5) await page.getByLabel("成本倍数", { exact: true }).fill(multipliers.join(", "));
    const pending = page.waitForResponse((response) => response.url().endsWith("/api/research/cost_sensitivity") && response.request().method() === "POST");
    await page.getByRole("button", { name: "成本敏感性", exact: true }).click();
    const response = await pending;
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    expect(result.run_id).toBe(runId);
    expect(result.points.map((point: { multiplier: number }) => point.multiplier)).toEqual(multipliers);
    await expect(table).toBeVisible();
    await expect(table.locator("tbody tr")).toHaveCount(multipliers.length);
    for (const [index, point] of result.points.entries()) {
      const row = table.locator("tbody tr").nth(index);
      await expect(row.getByRole("rowheader")).toHaveText(`${point.multiplier}×`);
      const fees = `¥${(point.total_fees / 10000).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      await expect(row.getByRole("cell")).toHaveText([
        `${(point.total_return * 100).toFixed(2)}%`,
        `${(point.annualized_return * 100).toFixed(2)}%`,
        point.sharpe.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        `${(point.max_drawdown * 100).toFixed(2)}%`,
        fees,
      ]);
    }
    if (multipliers.length === 5) {
      await page.getByRole("region", { name: "成本敏感性结果" }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: "/tmp/qc-cost-sensitivity.png" });
      await page.setViewportSize({ width: 390, height: 844 });
      await expect(table).toBeVisible();
      await page.getByRole("region", { name: "成本敏感性结果" }).scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      await page.screenshot({ path: "/tmp/qc-cost-sensitivity-mobile.png" });
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
  }
  expect(errors).toEqual([]);
});

test("today dashboard shows market, watchlist, beginner progress and data health", async ({ page, request }) => {
  const errors = await prepare(page, { beginner: true });
  await bootstrap(request);
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await expect(page.locator(".index-card")).toHaveCount(4);
  await expect(page.getByText("市场状态").first()).toBeVisible();
  await expect(page.getByText("我的自选").first()).toBeVisible();
  await expect(page.getByText("新手进度").first()).toBeVisible();
  await expect(page.getByText("最近研究").first()).toBeVisible();
  await expect(page.getByText("数据体检").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /开始一次研究/ })).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-today.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("market page renders indices, breadth, readings and K-line (offline snapshot)", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/market");
  await expect(page.getByRole("heading", { name: "行情", level: 1 })).toBeVisible();
  await expect(page.locator(".index-card")).toHaveCount(4);
  await expect(page.locator(".breadth")).toContainText("上涨");
  await expect(page.locator(".kline-canvas canvas").first()).toBeVisible();
  await expect(page.getByText(/实时行情未开启|离线快照/).first()).toBeVisible();
  await page.getByRole("button", { name: "分钟", exact: true }).click();
  await expect(page.getByTestId("minute-panel")).toContainText("SYNTHETIC_MINUTE");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-market.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("screener runs and hands the result to a backtest", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/screener");
  await expect(page.getByRole("heading", { name: "选股", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /运行选股/ }).first().click();
  await expect(page.locator(".vtable-row, .table tbody tr").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /用这个结果回测/ }).click();
  await expect(page).toHaveURL(/\/backtest\?screener=/);
  await page.screenshot({ path: "/tmp/qc-screener.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("backtest wizard runs a job and renders conclusion-first results", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/backtest");
  await expect(page.getByRole("heading", { name: "回测", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /运行回测/ }).first().click();
  await expect(page.getByText("总收益").first()).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".stat-tile, .kpi").first()).toBeVisible();
  const tradesTab = page.getByRole("tab", { name: "交易明细" });
  await tradesTab.click();
  await expect(page.locator(".vtable-row, .table tbody tr").first()).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-backtest.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("data page shows integrity first and keeps import/snapshot entry points", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/data");
  await expect(page.getByRole("heading", { name: "数据", level: 1 })).toBeVisible();
  await expect(page.getByText("数据体检").first()).toBeVisible();
  await expect(page.getByText("导入真实数据").first()).toBeVisible();
  await expect(page.getByText(/新浪财经/).first()).toBeVisible();
  await expect(page.locator(".provider-row, .list-row").first()).toBeVisible();
  await page.getByLabel("更新方式", { exact: true }).selectOption("replace");
  await page.getByLabel("证券数（synthetic）", { exact: true }).fill("12");
  const updateResponse = page.waitForResponse((response) => response.url().endsWith("/api/data/update") && response.request().method() === "POST");
  let snapshotRequests = 0;
  page.on("request", (request) => { if (request.url().endsWith("/api/data/snapshot") && request.method() === "POST") snapshotRequests += 1; });
  await page.getByRole("button", { name: "更新并构建快照", exact: true }).click();
  const imported = await updateResponse;
  expect(imported.request().postDataJSON().incremental).toBe(false);
  expect(imported.request().postDataJSON().build_snapshot).toBe(true);
  expect(imported.status()).toBe(202);
  const jobId = (await imported.json()).job_id;
  await page.getByRole("link", { name: "回测", exact: true }).first().click();
  await expect(page).toHaveURL(/\/backtest/);
  await page.getByRole("link", { name: "数据", exact: true }).first().click();
  let completed;
  for (let index = 0; index < 300; index += 1) {
    completed = await (await request.get(`/api/jobs/${jobId}`, { headers: AUTH })).json();
    if (["done", "failed", "cancelled"].includes(completed.status)) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  expect(completed.status).toBe("done");
  await expect(page.getByText(completed.result.snapshot_id).first()).toBeVisible({ timeout: 20_000 });
  expect(snapshotRequests).toBe(0);
  const overview = await request.get("/api/market/overview", { headers: AUTH });
  expect((await overview.json()).snapshot.n_sec).toBe(12);
  await page.screenshot({ path: "/tmp/qc-data.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("experiments list renders cards and keeps local tags/notes", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await createExperiment(request);
  await page.goto("/experiments");
  await expect(page.getByRole("heading", { name: "实验", level: 1 })).toBeVisible();
  await expect(page.locator(".exp-card").first()).toBeVisible({ timeout: 20_000 });
  await page.locator(".exp-card").first().click();
  const tags = page.getByLabel(/标签/);
  if (await tags.count()) {
    await tags.fill("e2e, 动量");
    await page.getByLabel(/笔记/).fill("本地笔记 e2e");
    await page.reload();
    await page.locator(".exp-card").first().click();
    await expect(page.getByLabel(/标签/)).toHaveValue("e2e, 动量");
    await expect(page.getByLabel(/笔记/)).toHaveValue("本地笔记 e2e");
  }
  await page.screenshot({ path: "/tmp/qc-experiments.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("strategy and settings pages render, connect and pass self-check", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/strategy");
  await expect(page.getByRole("heading", { name: "策略", level: 1 })).toBeVisible();
  await expect(page.getByText(/策略模板/).first()).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-strategy.png", fullPage: true });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "设置", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /测试连接/ }).click();
  await expect(page.getByText(/^已连接：cpp/)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /运行自检/ }).click();
  await expect(page.getByText(/自检|通过|警告/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("switch", { name: "新手模式" }).first()).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-settings.png", fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("research factor analysis gives a conclusion before charts", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "研究", level: 1 })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "研究视图" })).toBeVisible();
  await page.getByRole("button", { name: /运行诊断/ }).click();
  await expect(page.locator(".conclusion, .callout").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".chart-canvas canvas").first()).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "/tmp/qc-research.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("research sweep and walk-forward run inside tabs", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/research");
  await page.getByRole("tab", { name: /参数扫描/ }).click();
  await page.getByRole("button", { name: /运行扫描/ }).click();
  await expect(page.getByText("扫描结果").first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("combobox", { name: /模式/ }).selectOption("random");
  await page.getByLabel("抽样数").fill("4");
  await page.getByRole("button", { name: /运行扫描/ }).click();
  await expect(page.getByText(/随机 4\/4/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: /滚动验证/ }).click();
  await page.getByRole("button", { name: /运行滚动验证/ }).click();
  await expect(page.getByText(/4 折/).first()).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: "/tmp/qc-sweep.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("dark theme renders without overflow", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.goto("/today");
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "切换主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-dark.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("onboarding demo button creates a snapshot and an experiment", async ({ page }) => {
  const errors = await prepare(page, { beginner: true });
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /一键示例/ }).first().click();
  await expect(page.getByText(/快照|示例/).first()).toBeVisible({ timeout: 90_000 });
  await page.goto("/experiments");
  await expect(page.getByRole("heading", { name: "实验", level: 1 })).toBeVisible();
  await expect(page.locator(".exp-card").first()).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "/tmp/qc-onboarding.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("qc serve --open token URL bootstraps auth and is cleaned", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootstrap(request);
  await page.goto("/?token=" + encodeURIComponent(token));
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30_000 });
  expect(new URL(page.url()).searchParams.get("token")).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("qc_token"))).toBe(token);
  expect(errors).toEqual([]);
});

test("initial UI load meets the local performance budget", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  const started = Date.now();
  await page.goto("/today");
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 15_000 });
  const elapsed = Date.now() - started;
  const encoded = await page.evaluate(() =>
    performance
      .getEntriesByType("resource")
      .filter((entry) => (entry as PerformanceResourceTiming).name.endsWith(".js"))
      .reduce((sum, entry) => sum + ((entry as PerformanceResourceTiming).encodedBodySize || 0), 0),
  );
  expect(elapsed).toBeLessThan(5000);
  expect(encoded).toBeLessThan(2_000_000);
  expect(errors).toEqual([]);
});

test("global search and command palette find securities and navigate", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  const securities = await request.get("/api/market/securities?limit=100", { headers: AUTH });
  const target = (await securities.json()).at(-1);
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "打开命令面板" }).click();
  const palette = page.getByRole("combobox", { name: "命令面板" });
  await expect(palette).toBeFocused();
  await palette.fill(target.code);
  await page.locator("[cmdk-item]").filter({ hasText: target.code }).click();
  await expect(page).toHaveURL(`/market?code=${target.code}`);
  await expect(page.locator(".kline-canvas canvas").first()).toBeVisible();
  await expect(palette).not.toBeVisible();
  await page.keyboard.press("Control+k");
  await palette.fill("回测");
  await expect(page.locator("[cmdk-item]").first()).toBeVisible({ timeout: 10_000 });
  await page.locator("[cmdk-item]").first().click();
  await expect(page).toHaveURL(/\/backtest/);
  expect(errors).toEqual([]);
});

test("keyboard shortcuts jump between pages", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await page.keyboard.press("Alt+2");
  await expect(page).toHaveURL(/\/market/);
  expect(errors).toEqual([]);
});

test("mobile layout has no horizontal overflow and shows the tab bar", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await expect(page.locator(".mobile-tabbar, nav[aria-label=移动导航]")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("paper trading session creates, steps and renders the virtual account", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request, 30, 41);
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "模拟交易", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /创建会话/ }).click();
  await expect(page.getByText("总权益")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("持仓市值")).toBeVisible();
  await expect(page.getByText("提交模拟委托")).toBeVisible({ timeout: 15_000 });
  const securities = await request.get("/api/market/securities?limit=1", { headers: AUTH });
  const rows = await securities.json();
  const firstCode = String(rows[0]?.code || "600000");
  await page.getByLabel("代码").fill(firstCode);
  await page.getByLabel("数量").fill("100");
  await page.getByRole("button", { name: /提交委托/ }).click();
  await expect(page.getByText(/待成交|部分成交|已成交/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /下一交易日/ }).click();
  await expect(page.getByText("持仓市值")).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-paper.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("local strategy plugin lists, audits and runs in professional mode", async ({ page, request }) => {
  const errors = await prepare(page);
  await bootstrap(request, 24, 61);
  const source = [
    "PLUGIN_INFO = {'description': 'demo equal weight', 'version': '1'}",
    "import numpy as np",
    "from quantcore.strategy.base import Strategy",
    "",
    "class DemoPlugin(Strategy):",
    "    name = 'demo_plugin'",
    "    def generate_weights(self, panel):",
    "        weights = np.full((panel.n_time, panel.n_sec), np.nan)",
    "        for index in range(0, panel.n_time, 20):",
    "            weights[index] = 1.0 / panel.n_sec",
    "        return weights",
  ].join("\n");
  const put = await request.put("/api/strategies/files/demo_plugin.py", { headers: AUTH, data: { content: source } });
  expect(put.ok()).toBeTruthy();
  await page.goto("/strategy");
  await expect(page.getByText("demo_plugin", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByText("demo_plugin", { exact: false }).first().click();
  await page.getByRole("button", { name: "审计", exact: true }).click();
  await expect(page.getByText(/静态审计通过|审计失败/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /运行插件回测/ }).click();
  await page.waitForURL(/\/experiments/, { timeout: 60_000 });
  await page.screenshot({ path: "/tmp/qc-plugin.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("live paper account accepts virtual orders and waits when the quote source is off", async ({ page, request }) => {
  const errors = await prepare(page);
  await page.goto("/paper");
  await page.getByRole("combobox", { name: "行情模式" }).selectOption("live");
  await page.getByRole("textbox", { name: "会话名称", exact: true }).fill("浏览器实时模拟");
  const created = page.waitForResponse((response) => response.url().endsWith("/api/paper/sessions") && response.request().method() === "POST");
  await page.getByRole("button", { name: "创建会话", exact: true }).click();
  const session = await (await created).json();
  expect(session.mode).toBe("live");
  expect(session.snapshot).toBeNull();
  await expect(page.getByRole("button", { name: "刷新实时账户", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "代码", exact: true }).fill("600000");
  const submitted = page.waitForResponse((response) => response.url().endsWith(`/api/paper/sessions/${session.id}/orders`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "提交委托", exact: true }).click();
  expect((await submitted).ok()).toBeTruthy();
  await page.getByRole("button", { name: "刷新实时账户", exact: true }).click();
  const response = await request.get(`/api/paper/sessions/${session.id}`, { headers: AUTH });
  const detail = await response.json();
  expect(detail.session.mode).toBe("live");
  expect(detail.orders).toHaveLength(1);
  expect(detail.orders[0].status).toBe("pending");
  expect(detail.positions).toHaveLength(0);
  expect(detail.trades).toHaveLength(0);
  expect(detail.live.state).not.toBe("live");
  await page.screenshot({ path: "/tmp/qc-live-paper.png", fullPage: true });
  expect(errors).toEqual([]);
});
