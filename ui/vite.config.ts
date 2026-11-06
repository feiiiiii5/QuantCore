import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Dev proxy target (qc serve). Keep both sides loopback-only. */
const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
const API_TARGET = env?.QC_DEV_API || "http://127.0.0.1:8000";
const API_ORIGIN = new URL(API_TARGET).origin;

/** The backend validates the browser Origin against its own port, so the dev proxy
 * rewrites Origin to the qc serve origin (previously `pnpm dev` hit 403). */
const proxyOptions = {
  target: API_TARGET,
  changeOrigin: true,
  headers: { Origin: API_ORIGIN },
};

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": proxyOptions,
      "/health": proxyOptions,
      "/ws": { target: API_TARGET.replace("http", "ws"), ws: true, changeOrigin: true, headers: { Origin: API_ORIGIN } },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        // Shared runtime helpers must not pull the lazy Monaco bundle into every page.
        manualChunks(id) {
          if (id.includes("vite/preload-helper") || id.includes("commonjsHelpers")) return "runtime";
          const groups: Record<string, string[]> = {
            react: ["react", "react-dom", "react-router-dom"],
            charts: ["lightweight-charts"],
            motion: ["framer-motion"],
            overlays: ["@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu", "@radix-ui/react-popover", "@radix-ui/react-select", "@radix-ui/react-switch", "@radix-ui/react-tabs", "@radix-ui/react-toggle-group", "@radix-ui/react-tooltip", "sonner", "cmdk", "vaul"],
            editor: ["monaco-editor", "@monaco-editor/react"],
          };
          return Object.entries(groups).find(([, packages]) => packages.some((name) => id.includes(`/node_modules/${name}/`)))?.[0];
        },
      },
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], include: ["src/**/*.test.{ts,tsx}"], exclude: ["e2e/**", "node_modules/**"] },
});
