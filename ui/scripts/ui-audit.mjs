#!/usr/bin/env node
/** Local UI audit: screenshots + console/overflow/a11y checks for the redesigned UI.
 *
 * Usage: QC_BASE=http://127.0.0.1:8150 QC_TOKEN=test-token node scripts/ui-audit.mjs
 * Env: QC_BASE, QC_TOKEN, QC_OUT (default /tmp/qc-ui-audit).
 */
import { chromium } from "@playwright/test";

const base = process.env.QC_BASE || "http://127.0.0.1:8150";
const token = process.env.QC_TOKEN || "test-token";
const out = process.env.QC_OUT || "/tmp/qc-ui-audit";
const routes = ["/today", "/market", "/backtest", "/data", "/settings", "/paper", "/research", "/screener", "/strategy", "/experiments"];

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript(
  ({ value }) => {
    localStorage.setItem("qc_token", value);
    localStorage.setItem("qc_theme", "light");
    localStorage.setItem("qc_density", "comfortable");
    localStorage.setItem("qc_beginner", "0");
  },
  { value: token },
);
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push("pageerror: " + error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push("console: " + message.text().slice(0, 240));
});

const report = [];
for (const route of routes) {
  errors.length = 0;
  const response = await page.goto(base + route, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  const name = route.split("/").join("_").replace(/^_/, "");
  await page.screenshot({ path: out + "/" + name + ".png", fullPage: true });
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const label = (element) => {
      const text = (element.getAttribute("aria-label") || element.textContent || element.getAttribute("title") || "").trim();
      return text.replace(/\s+/g, " ").slice(0, 60);
    };
    const unnamedControls = [...document.querySelectorAll("button, a, [role=button], [role=switch], [role=tab]")]
      .filter((element) => !label(element)).length;
    const h1s = [...document.querySelectorAll("h1")].map((element) => element.textContent.trim());
    const images = [...document.querySelectorAll("img")].filter((element) => !element.getAttribute("alt")).length;
    const wideTables = [...document.querySelectorAll(".table-wrap")].filter((element) => element.scrollWidth > element.clientWidth + 2).length;
    return {
      title: document.title,
      h1: h1s,
      unnamedControls,
      images,
      overflow: doc.scrollWidth - doc.clientWidth,
      wideTables,
      charts: document.querySelectorAll(".chart-canvas canvas, .kline-canvas canvas").length,
      cards: document.querySelectorAll(".card").length,
      bodyFont: getComputedStyle(document.body).fontFamily,
    };
  });
  report.push({ route, status: response ? response.status() : null, ...metrics, errors: [...errors] });
}

// Dark mode uses its own context: addInitScript resets localStorage on every navigation.
const darkContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await darkContext.addInitScript(
  ({ value }) => {
    localStorage.setItem("qc_token", value);
    localStorage.setItem("qc_theme", "dark");
    localStorage.setItem("qc_density", "comfortable");
    localStorage.setItem("qc_beginner", "0");
  },
  { value: token },
);
const darkPage = await darkContext.newPage();
await darkPage.goto(base + "/today", { waitUntil: "networkidle" });
await darkPage.waitForTimeout(600);
await darkPage.screenshot({ path: out + "/today-dark.png", fullPage: true });
const dark = await darkPage.evaluate(() => ({
  theme: document.documentElement.dataset.theme,
  bg: getComputedStyle(document.body).backgroundColor,
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
}));
await darkContext.close();

await page.evaluate(() => localStorage.setItem("qc_theme", "light"));
await page.setViewportSize({ width: 390, height: 844 });
for (const route of ["/today", "/market"]) {
  await page.goto(base + route, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: out + "/mobile" + route.split("/").join("_") + ".png", fullPage: true });
  report.push({
    route: "mobile" + route,
    overflow: await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    errors: [],
  });
}

await browser.close();
console.log(JSON.stringify({ base, dark, report }, null, 2));
