import { expect, test, type Page } from "@playwright/test";

const token = process.env.QC_E2E_TOKEN || "test-token";

async function prepare(page: Page) {
  await page.addInitScript((value: string) => {
    localStorage.setItem("qc_token", value);
    localStorage.removeItem("qc_api");
    localStorage.setItem("qc_theme", "light");
    localStorage.setItem("qc_density", "comfortable");
  }, token);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
  return errors;
}

test("market page renders indices, breadth and K-line", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "行情" })).toBeVisible();
  await expect(page.locator(".index-card")).toHaveCount(4);
  await expect(page.locator(".kline-canvas canvas").first()).toBeVisible();
  await expect(page.locator(".breadth")).toContainText("上涨");
  await expect(page.locator(".profile-strip")).toContainText("交易所");
  await expect(page.locator(".profile-strip")).toContainText("最近成交额");
  await page.screenshot({ path: "/tmp/qc-market.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("screener runs and shows matched rows", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/screener");
  await expect(page.getByRole("heading", { name: "选股" })).toBeVisible();
  await page.getByRole("button", { name: /运行选股/ }).click();
  await expect(page.locator(".vtable-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".card-head").last()).toContainText("只");
  await page.screenshot({ path: "/tmp/qc-screener.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("backtest submits a job and renders equity/trades", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/backtest?template=momentum&params=%7B%22top_n%22%3A5%2C%22lookback%22%3A60%7D");
  await expect(page.getByRole("heading", { name: "回测" })).toBeVisible();
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(page.getByText("总收益")).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".chart-block canvas")).toBeVisible();
  await expect(page.locator(".vtable-row").first()).toBeVisible();
  await page.locator(".vtable-row").first().click();
  await expect(page.getByRole("heading", { name: "交易解释" })).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-backtest.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("experiments and data pages connect to the local service", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/experiments");
  await expect(page.getByRole("heading", { name: "实验" })).toBeVisible();
  await expect(page.locator("body")).toContainText("运行记录");
  await page.screenshot({ path: "/tmp/qc-experiments.png", fullPage: true });
  await page.goto("/data");
  await expect(page.getByRole("heading", { name: "数据", exact: true })).toBeVisible();
  await expect(page.getByText("数据仓库")).toBeVisible();
  await expect(page.locator(".provider-row").first()).toBeVisible();
  const snapshotRow = page.locator(".card table tbody tr").first();
  if (await snapshotRow.count()) {
    await snapshotRow.click();
    await expect(page.getByRole("heading", { name: /质量报告/ })).toBeVisible({ timeout: 15000 });
  }
  await page.screenshot({ path: "/tmp/qc-data.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("experiment tags and notes persist locally", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/experiments");
  await expect(page.locator(".experiment-item").first()).toBeVisible({ timeout: 30000 });
  await page.locator(".experiment-item").first().click();
  const tags = page.getByLabel(/标签（逗号分隔，本地）/);
  const notes = page.getByLabel(/笔记（本地）/);
  await tags.fill("e2e, 动量");
  await notes.fill("本地笔记 e2e");
  await page.reload();
  await expect(page.locator(".experiment-item").first()).toBeVisible({ timeout: 30000 });
  await expect(page.getByLabel(/标签（逗号分隔，本地）/)).toHaveValue("e2e, 动量");
  await expect(page.getByLabel(/笔记（本地）/)).toHaveValue("本地笔记 e2e");
  expect(errors).toEqual([]);
});

test("strategy and settings pages render without overflow", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/strategy");
  await expect(page.getByRole("heading", { name: "策略", level: 1 })).toBeVisible();
  await expect(page.getByText("内置模板")).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-strategy.png", fullPage: true });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await page.getByRole("button", { name: /测试连接/ }).click();
  await expect(page.getByText(/已连接/)).toBeVisible({ timeout: 15000 });
  await page.screenshot({ path: "/tmp/qc-settings.png", fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("research factor analysis renders IC, quantiles and decay", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "研究", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /运行诊断/ }).click();
  await expect(page.getByRole("heading", { name: "IC 均值", exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "分层平均收益" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "因子衰减（RankIC）" })).toBeVisible();
  await expect(page.locator(".grid.kpis .card")).toHaveCount(4);
  await page.getByRole("button", { name: "计算相关性" }).click();
  await expect(page.getByRole("heading", { name: "因子相关性矩阵" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/平均 \|ρ\|/)).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-research.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("research sweep, walk-forward and attribution tabs run", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/research");
  await page.getByRole("tab", { name: /参数扫描/ }).click();
  await page.getByRole("button", { name: /运行扫描/ }).click();
  await expect(page.getByRole("heading", { name: /扫描结果/ })).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("模式").selectOption("random");
  await page.getByLabel("抽样数").fill("4");
  await page.getByRole("button", { name: /运行扫描/ }).click();
  await expect(page.getByText(/随机 4\/4/)).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: "/tmp/qc-sweep.png", fullPage: true });
  await page.getByRole("tab", { name: /滚动验证/ }).click();
  await page.getByRole("button", { name: /运行滚动验证/ }).click();
  await expect(page.getByRole("heading", { name: /4 折/ })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("tab", { name: /归因/ }).click();
  await page.getByRole("button", { name: /运行行业归因/ }).click();
  await expect(page.getByRole("heading", { name: /行业贡献/ })).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: "/tmp/qc-attribution.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("dark theme renders without overflow", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/");
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "切换主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-dark.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("onboarding creates a demo snapshot and experiment", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "行情", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /一键示例/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "三步开始" })).toBeVisible();
  await page.getByRole("button", { name: /生成示例数据与快照/ }).click();
  await expect(page.getByRole("button", { name: /下一步/ })).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: /下一步/ }).click();
  await page.getByRole("button", { name: /运行示例回测/ }).click();
  await expect(page).toHaveURL(/\/experiments/, { timeout: 120_000 });
  await expect(page.getByRole("heading", { name: "实验", exact: true })).toBeVisible();
  await page.screenshot({ path: "/tmp/qc-onboarding.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("qc serve --open token URL bootstraps auth and is cleaned", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/?token=${encodeURIComponent(token)}`);
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30000 });
  expect(new URL(page.url()).searchParams.get("token")).toBeNull();
  const stored = await page.evaluate(() => localStorage.getItem("qc_token"));
  expect(stored).toBe(token);
  expect(errors).toEqual([]);
});

test("initial UI load meets the local performance budget", async ({ page }) => {
  const errors = await prepare(page);
  const started = Date.now();
  await page.goto("/");
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 15000 });
  const elapsed = Date.now() - started;
  const encoded = await page.evaluate(() => performance.getEntriesByType("resource")
    .filter((entry) => (entry as PerformanceResourceTiming).name.endsWith(".js"))
    .reduce((sum, entry) => sum + ((entry as PerformanceResourceTiming).encodedBodySize || 0), 0));
  expect(elapsed).toBeLessThan(5000);
  expect(encoded).toBeLessThan(2_000_000);
  expect(errors).toEqual([]);
});

test("global search focuses with Ctrl+K and filters securities locally", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/");
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30000 });
  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", { name: "全局搜索" });
  await expect(search).toBeFocused();
  await search.fill("000001");
  await expect(page.locator(".search-hit").first()).toBeVisible({ timeout: 10000 });
  await page.locator(".search-hit").first().click();
  await expect(page).toHaveURL(/code=000001/);
  await expect(page.locator(".kline-legend")).toContainText("000001");
  expect(errors).toEqual([]);
});

test("mobile layout has no horizontal overflow", async ({ page }) => {
  const errors = await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "行情" })).toBeVisible();
  await expect(page.locator(".index-card").first()).toBeVisible({ timeout: 30000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "/tmp/qc-mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("paper trading session creates, steps and renders the virtual account", async ({ page, request }) => {
  const errors = await prepare(page);
  const auth = { Authorization: `Bearer ${token}` };
  const bootstrap = await request.post("/api/onboarding/bootstrap", {
    headers: auth,
    data: { n_sec: 30, start: "2023-01-03", end: "2024-12-31", seed: 41 },
  });
  expect(bootstrap.ok()).toBeTruthy();
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "模拟交易" })).toBeVisible();
  await expect(page.getByRole("button", { name: /创建会话/ })).toBeEnabled();
  await page.getByRole("button", { name: /创建会话/ }).click();
  await expect(page.getByText("总权益")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("持仓市值")).toBeVisible();
  const securitiesResponse = await request.get("/api/market/securities?limit=1", { headers: auth });
  const securities = await securitiesResponse.json();
  const firstCode = String(securities[0]?.code || "600000");
  await page.getByLabel("代码").fill(firstCode);
  await page.getByLabel("数量").fill("100");
  await page.getByRole("button", { name: /提交委托/ }).click();
  await expect(page.getByText(/pending|已提交/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /下一交易日/ }).click();
  await expect(page.getByText("持仓市值")).toBeVisible();
  await expect(page.getByText("虚拟账户仅用于研究")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "/tmp/qc-paper.png", fullPage: true });
});

test("research robustness computes deflated Sharpe without overflow", async ({ page }) => {
  const errors = await prepare(page);
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "研究" })).toBeVisible();
  await page.getByRole("tab", { name: /稳健性/ }).click();
  await expect(page.getByRole("button", { name: /Deflated Sharpe/ })).toBeVisible();
  await page.getByRole("button", { name: /Deflated Sharpe/ }).click();
  await expect(page.getByText(/观测 \d+ 日/)).toBeVisible({ timeout: 45_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "/tmp/qc-robustness.png", fullPage: true });
});

test("local strategy plugin lists, audits and runs through the job queue", async ({ page, request }) => {
  const errors = await prepare(page);
  const auth = { Authorization: `Bearer ${token}` };
  const bootstrap = await request.post("/api/onboarding/bootstrap", {
    headers: auth,
    data: { n_sec: 24, start: "2023-01-03", end: "2024-12-31", seed: 61 },
  });
  expect(bootstrap.ok()).toBeTruthy();
  const source = [
    'PLUGIN_INFO = {"description": "demo equal weight", "version": "1"}',
    "import numpy as np",
    "from quantcore.strategy.base import Strategy",
    "",
    "class DemoPlugin(Strategy):",
    '    name = "demo_plugin"',
    "    def generate_weights(self, panel):",
    "        weights = np.full((panel.n_time, panel.n_sec), np.nan)",
    "        for index in range(0, panel.n_time, 20):",
    "            weights[index] = 1.0 / panel.n_sec",
    "        return weights",
  ].join("\n");
  const put = await request.put("/api/strategies/files/demo_plugin.py", { headers: auth, data: { content: source } });
  expect(put.ok()).toBeTruthy();
  await page.goto("/strategy");
  await expect(page.getByRole("heading", { name: "策略", level: 1 })).toBeVisible();
  await expect(page.getByText("demo_plugin", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByText("demo_plugin", { exact: false }).first().click();
  await page.getByRole("button", { name: "审计", exact: true }).click();
  await expect(page.getByText(/静态审计通过|审计失败/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /运行插件回测/ }).click();
  await page.waitForURL(/\/experiments/, { timeout: 60_000 });
  expect(errors).toEqual([]);
  await page.screenshot({ path: "/tmp/qc-plugin.png", fullPage: true });
});

test("paper portfolio aggregates two simulated sessions", async ({ page, request }) => {
  const errors = await prepare(page);
  const auth = { Authorization: `Bearer ${token}` };
  const bootstrap = await request.post("/api/onboarding/bootstrap", { headers: auth, data: { n_sec: 24, start: "2023-01-03", end: "2024-12-31", seed: 71 } });
  expect(bootstrap.ok()).toBeTruthy();
  const ids: string[] = [];
  for (const name of ["组合策略A", "组合策略B"]) {
    const created = await request.post("/api/paper/sessions", { headers: auth, data: { initial_cash: 1_000_000, name } });
    expect(created.status()).toBe(201);
    const id = String((await created.json()).id);
    ids.push(id);
    const step = await request.post(`/api/paper/sessions/${id}/step`, { headers: auth, data: { days: 2 } });
    expect(step.ok()).toBeTruthy();
  }
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "模拟交易" })).toBeVisible();
  await expect(page.getByText("多策略组合视图")).toBeVisible();
  await page.getByRole("checkbox", { name: /组合策略A/ }).check();
  await page.getByRole("checkbox", { name: /组合策略B/ }).check();
  await page.getByLabel("组合策略A 权重").fill("0.5");
  await page.getByLabel("组合策略B 权重").fill("0.5");
  await page.getByRole("button", { name: "计算组合" }).click();
  await expect(page.getByText("组合收益")).toBeVisible({ timeout: 30_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "/tmp/qc-portfolio.png", fullPage: true });
  void ids;
});
