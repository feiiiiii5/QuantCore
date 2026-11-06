import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import DataPage from "./DataPage";

vi.mock("../api/client", () => ({
  api: {
    dataStatus: vi.fn(), dataCatalog: vi.fn(), dataIntegrity: vi.fn(), liveStatus: vi.fn(), quality: vi.fn(),
    updateData: vi.fn(), buildSnapshot: vi.fn(), completeOnboardingStep: vi.fn(),
  },
  isApiError: () => false,
  wsUrl: (id: string) => `ws://localhost/${id}`,
}));

class Socket {
  static sockets = new Map<string, Socket>();
  onmessage?: (event: { data: string }) => void;
  close = vi.fn();
  constructor(url: string) { Socket.sockets.set(url.split("/").pop()!, this); }
  emit(id: string, status: string) { this.onmessage?.({ data: JSON.stringify({ job: { id, status, progress: 1 } }) }); }
}

describe("data import and snapshot job handoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Socket.sockets.clear();
    vi.stubGlobal("WebSocket", Socket);
    vi.mocked(api.dataStatus).mockResolvedValue({
      data_root: "data", providers: [], snapshots: [],
      warehouse: { rows: 0, bytes: 0, datasets: {}, manifest_hash: "" },
      storage: { snapshot_bytes: 0, experiments_bytes: 0, free_bytes: 1000 },
    } as never);
    vi.mocked(api.dataCatalog).mockResolvedValue({ datasets: [] } as never);
    vi.mocked(api.dataIntegrity).mockRejectedValue(new Error("体检尚无快照"));
    vi.mocked(api.liveStatus).mockResolvedValue({ enabled: false } as never);
    vi.mocked(api.updateData).mockResolvedValue({ job_id: "update_1" } as never);
    vi.mocked(api.buildSnapshot).mockResolvedValue({ job_id: "snapshot_2" } as never);
  });
  afterEach(() => vi.unstubAllGlobals());

  it.each([false, true])("keeps following the snapshot until that job itself finishes (hidden=%s)", async (hidden) => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(vi.mocked(api.updateData).mock.calls[0]?.[0]).toMatchObject({ incremental: true }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    if (hidden) fireEvent.click(screen.getByRole("button", { name: "隐藏" }));
    await act(async () => { Socket.sockets.get("update_1")!.emit("update_1", "done"); });
    await waitFor(() => expect(Socket.sockets.has("snapshot_2")).toBe(true));

    expect(screen.queryByText("快照构建完成")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).toBeDisabled();
    await act(async () => { Socket.sockets.get("snapshot_2")!.emit("snapshot_2", "done"); });
    expect(await screen.findByText("快照构建完成")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).not.toBeDisabled();
  });

  it("can explicitly replace the warehouse when changing the data source or universe", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("更新方式"), { target: { value: "replace" } });
    expect(screen.getByText(/取数与质量检查通过后替换当前数据仓库/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(vi.mocked(api.updateData).mock.calls[0]?.[0]).toMatchObject({ provider: "synthetic", incremental: false }));
  });
});
