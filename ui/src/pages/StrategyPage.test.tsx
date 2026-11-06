import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import StrategyPage from "./StrategyPage";

vi.mock("../api/client", () => ({ api: { templates: vi.fn(), onboardingPresets: vi.fn(), plugins: vi.fn(), validateStrategy: vi.fn() } }));
vi.mock("../monaco", () => ({}));
vi.mock("@monaco-editor/react", () => ({ default: () => null }));

describe("strategy parameter validation identity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.templates).mockResolvedValue([{
      id: "momentum", name: "动量", params_schema: { properties: { top_n: { type: "integer", title: "持仓数", minimum: 1, default: 10 } } },
    }] as never);
    vi.mocked(api.onboardingPresets).mockResolvedValue([]);
    vi.mocked(api.plugins).mockResolvedValue([]);
    vi.mocked(api.validateStrategy).mockResolvedValue({ valid: true } as never);
  });

  it("removes the previous valid verdict when parameters are edited", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><StrategyPage /></MemoryRouter>
    </QueryClientProvider>);
    const input = await screen.findByLabelText("持仓数");
    fireEvent.click(screen.getByRole("button", { name: "校验参数" }));
    expect(await screen.findByText("参数有效")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "0" } });
    expect(screen.queryByText("参数有效")).not.toBeInTheDocument();
    expect(screen.queryByText("参数通过 schema 校验")).not.toBeInTheDocument();
  });
});
