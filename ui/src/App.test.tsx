import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  api: {
    meta: vi.fn().mockResolvedValue({ version: "0.1.0", engine_backend: "cpp", synthetic_only: true, data_root: "", snapshots_root: "", experiments_root: "", token_required: true, ui_served: true, cors: false }),
    health: vi.fn().mockResolvedValue({ status: "ok", version: "0.1.0", engine_backend: "cpp", engine_available: true, panel_available: true, synthetic_only: true, cors: false }),
  },
  getApiBase: () => "",
  getToken: () => "",
  configure: vi.fn(),
}));

describe("App shell", () => {
  it("renders nav and disclaimer", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/settings"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("QuantCore")).toBeInTheDocument();
    expect(screen.getByText("回测")).toBeInTheDocument();
    expect(screen.getAllByText(/不构成投资建议/).length).toBeGreaterThan(0);
  });
});
