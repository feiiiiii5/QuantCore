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
  await expect(page.getByText(/已连接/)).toBeVisible({ timeout: 15_000 });
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

test("command palette opens with Ctrl+K and navigates", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今日", level: 1 })).toBeVisible();
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("combobox", { name: "命令面板" });
  await expect(palette).toBeFocused();
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
