import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  api: {
    meta: vi.fn().mockResolvedValue({ version: "0.1.0", engine_backend: "cpp", synthetic_only: true, data_root: "", snapshots_root: "", experiments_root: "", token_required: true, ui_served: true, cors: false }),
    health: vi.fn().mockResolvedValue({ status: "ok", version: "0.1.0", engine_backend: "cpp", engine_available: true, panel_available: true, synthetic_only: true, cors: false }),
    dataStatus: vi.fn().mockResolvedValue({ data_root: "", warehouse: { exists: false, datasets: {}, rows: 0, bytes: 0, manifest_hash: "" }, snapshots: [], storage: { warehouse_bytes: 0, snapshot_bytes: 0, experiments_bytes: 0, free_bytes: 0 }, providers: [] }),
    jobs: vi.fn().mockResolvedValue([]),
    securities: vi.fn().mockResolvedValue([]),
    liveStatus: vi.fn().mockResolvedValue({ enabled: false, status: "disabled", market: { phase: "closed" } }),
    liveIndices: vi.fn().mockResolvedValue({ quotes: [] }),
  },
  getApiBase: () => "",
  getToken: () => "",
  configure: vi.fn(),
  isApiError: () => false,
  ApiError: class ApiError extends Error {},
}));

describe("App shell", () => {
  it("renders nav and disclaimer", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: 0 } } })}>
        <MemoryRouter initialEntries={["/settings"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("QuantCore")).toBeInTheDocument();
    expect(screen.getByText("回测")).toBeInTheDocument();
    expect(screen.getAllByText(/不构成投资建议/).length).toBeGreaterThan(0);
  });
});
