// QuantCore desktop shell (dev). It starts a local qc serve and renders the same UI.
// This is a research/simulation workbench; it never places real orders.
const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const path = require("node:path");
const crypto = require("node:crypto");

const ROOT = process.env.QC_REPO_ROOT || path.resolve(__dirname, "..");
const PORT = Number(process.env.QC_DESKTOP_PORT || 8787);
const TOKEN = process.env.QC_DESKTOP_TOKEN || crypto.randomBytes(18).toString("hex");
const EXTERNAL_URL = process.env.QC_DESKTOP_URL || "";
const HEADLESS = process.env.QC_HEADLESS === "1";
const SMOKE = process.env.QC_SMOKE === "1";
let server = null;

function health() {
  return new Promise((resolve) => {
    const request = http.get(`http://127.0.0.1:${PORT}/health`, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on("error", () => resolve(false));
    request.setTimeout(1000, () => { request.destroy(); resolve(false); });
  });
}

async function waitForServer(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await health()) return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

function startServer() {
  server = spawn("uv", ["run", "qc", "serve", "--port", String(PORT), "--token", TOKEN,
    "--ui-dir", path.join(ROOT, "ui", "dist"), "--no-open"], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, QC_SERVER_TOKEN: TOKEN },
  });
  server.stdout.on("data", (chunk) => process.stdout.write(`[qc] ${chunk}`));
  server.stderr.on("data", (chunk) => process.stderr.write(`[qc] ${chunk}`));
}

function stopServer() {
  if (server && !server.killed) {
    server.kill("SIGTERM");
    server = null;
  }
}

async function createWindow() {
  if (!EXTERNAL_URL) startServer();
  if (!EXTERNAL_URL && !(await waitForServer())) {
    if (SMOKE) {
      console.error("[desktop] server did not become healthy");
      app.exit(2);
      return;
    }
    dialog.showErrorBox("QuantCore", "本地 qc serve 未能启动；请先在仓库根目录运行 make setup。");
    app.quit();
    return;
  }
  const window = new BrowserWindow({
    width: 1440,
    height: 1000,
    show: !HEADLESS,
    title: "QuantCore — 本地量化研究",
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  window.webContents.on("did-fail-load", (_event, code, description) => {
    console.error(`[desktop] load failed: ${code} ${description}`);
    if (SMOKE) app.exit(3);
  });
  window.webContents.on("did-finish-load", () => {
    console.log("[desktop] UI loaded");
    if (SMOKE) setTimeout(() => { stopServer(); app.exit(0); }, 800);
  });
  const target = EXTERNAL_URL || `http://127.0.0.1:${PORT}`;
  const separator = target.includes("?") ? "&" : "?";
  await window.loadURL(`${target}${separator}token=${encodeURIComponent(TOKEN)}`);
}

app.whenReady().then(() => {
  createWindow().catch((error) => {
    console.error("[desktop] failed:", error);
    stopServer();
    app.exit(1);
  });
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) void createWindow(); });
});
app.on("before-quit", stopServer);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
