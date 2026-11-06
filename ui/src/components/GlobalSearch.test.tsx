import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { SecurityRow } from "../api/types";
import GlobalSearch from "./GlobalSearch";
import CommandPalette from "./CommandPalette";

vi.mock("../api/client", () => ({ api: { securities: vi.fn() } }));

const outsideFirstPage = {
  sec_id: "SH.600999", code: "600999", name: "全市场外页证券", industry: "银行", board: "MAIN", change_pct: 0,
} as SecurityRow;

function Location() {
  const location = useLocation();
  return <output aria-label="当前位置">{location.pathname}{location.search}</output>;
}

describe("global security search", () => {
  beforeEach(() => {
    vi.mocked(api.securities).mockReset();
    vi.mocked(api.securities).mockImplementation(async (query) => ["600999", "银行", "MAIN"].includes(query ?? "") ? [outsideFirstPage] : []);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("searches the whole snapshot and opens the chosen security's market page", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter initialEntries={["/today"]}><GlobalSearch /><Location /></MemoryRouter>
    </QueryClientProvider>);

    expect(api.securities).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("combobox", { name: "全局搜索" }), { target: { value: "600999" } });
    fireEvent.click(await screen.findByRole("option", { name: /全市场外页证券/ }));
    expect(screen.getByLabelText("当前位置")).toHaveTextContent("/market?code=600999");
    await waitFor(() => expect(api.securities).toHaveBeenCalledWith("600999", 8, undefined));
  });

  it.each(["600999", "银行", "MAIN"])("finds securities through the command palette by %s", async (query) => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter initialEntries={["/today"]}><CommandPalette open onClose={() => undefined} /><Location /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.change(screen.getByRole("combobox", { name: "命令面板" }), { target: { value: query } });
    fireEvent.click(await screen.findByRole("option", { name: /全市场外页证券/ }));
    expect(screen.getByLabelText("当前位置")).toHaveTextContent("/market?code=600999");
    expect(api.securities).toHaveBeenCalledWith(query, 6, undefined);
  });
});
