import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import DataPage from "./DataPage";

const connection = vi.hoisted(() => ({ base: "http://backend-a" }));
vi.mock("../api/client", () => ({
  api: {
    dataStatus: vi.fn(), dataCatalog: vi.fn(), dataIntegrity: vi.fn(), liveStatus: vi.fn(), quality: vi.fn(),
    updateData: vi.fn(), buildSnapshot: vi.fn(), completeOnboardingStep: vi.fn(), job: vi.fn(),
  },
  isApiError: (error: unknown) => error instanceof Error && "status" in error,
  getApiBase: () => connection.base,
  wsUrl: (id: string) => `ws://localhost/${id}`,
}));

class Socket {
  static sockets = new Map<string, Socket>();
  onmessage?: (event: { data: string }) => void;
  close = vi.fn();
  constructor(url: string) { Socket.sockets.set(url.split("/").pop()!, this); }
  emit(id: string, status: string, result?: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify({ job: { id, status, progress: 1, result } }) }); }
}

describe("data import and snapshot job handoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    connection.base = "http://backend-a";
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
    vi.mocked(api.job).mockImplementation(async (id) => ({ id, kind: "data_update", status: "running", progress: 0.5 }) as never);
  });
  afterEach(() => vi.unstubAllGlobals());

  it.each([false, true])("follows the server-owned import and snapshot as one job (hidden=%s)", async (hidden) => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(vi.mocked(api.updateData).mock.calls[0]?.[0]).toMatchObject({ incremental: true, build_snapshot: true }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    if (hidden) fireEvent.click(screen.getByRole("button", { name: "隐藏" }));
    expect(screen.getByRole("button", { name: "更新并构建快照" })).toBeDisabled();
    await act(async () => { Socket.sockets.get("update_1")!.emit("update_1", "done", { snapshot_id: "snapshot_combined" }); });
    expect(await screen.findByText(/数据更新与快照构建完成.*snapshot_combined/)).toBeInTheDocument();
    expect(api.buildSnapshot).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).not.toBeDisabled();
  });

  it("submits the full server workflow before leaving the page, without a client-side second job", async () => {
    const view = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    expect(vi.mocked(api.updateData).mock.calls[0]?.[0]).toMatchObject({ build_snapshot: true });
    view.unmount();
    act(() => Socket.sockets.get("update_1")!.emit("update_1", "done", { snapshot_id: "snapshot_combined" }));
    expect(api.updateData).toHaveBeenCalledTimes(1);
    expect(api.buildSnapshot).not.toHaveBeenCalled();
  });

  it("keeps standalone snapshot creation available as a retry", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "构建快照" }));
    await waitFor(() => expect(Socket.sockets.has("snapshot_2")).toBe(true));
    await act(async () => { Socket.sockets.get("snapshot_2")!.emit("snapshot_2", "done", { snapshot_id: "snapshot_manual" }); });
    expect(await screen.findByText(/快照构建完成.*snapshot_manual/)).toBeInTheDocument();
    expect(api.updateData).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    expect(screen.queryByText(/数据更新与快照构建完成/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).toBeDisabled();
    await act(async () => { Socket.sockets.get("update_1")!.emit("update_1", "done", { snapshot_id: "snapshot_next" }); });
    expect(await screen.findByText(/数据更新与快照构建完成.*snapshot_next/)).toBeInTheDocument();
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

  it("refreshes committed snapshots after cancellation and explains how to recover", async () => {
    const status = {
      data_root: "data", providers: [], snapshots: [],
      warehouse: { rows: 0, bytes: 0, datasets: {}, manifest_hash: "" },
      storage: { snapshot_bytes: 0, experiments_bytes: 0, free_bytes: 1000 },
    };
    vi.mocked(api.dataStatus).mockResolvedValueOnce(status as never).mockResolvedValue({
      ...status, snapshots: [{ id: "snapshot_committed", n_sec: 8, n_time: 640, start: 20240318, end: 20261106, quality: { passed: true }, synthetic: false, source: "SINA" }],
    } as never);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    await act(async () => { Socket.sockets.get("update_1")!.emit("update_1", "cancelled"); });
    expect(await screen.findByText(/任务已取消.*已经写入的数据和快照会保留/)).toBeInTheDocument();
    expect(await screen.findByText("snapshot_committed")).toBeInTheDocument();
    expect(api.dataStatus).toHaveBeenCalledTimes(2);
    expect(api.dataIntegrity).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "构建快照" })).not.toBeDisabled();
    expect(api.buildSnapshot).not.toHaveBeenCalled();
  });

  it("restores the same API's active job after remount and refreshes lists at completion", async () => {
    const mount = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    const first = mount();
    fireEvent.click(await screen.findByRole("button", { name: "更新并构建快照" }));
    await waitFor(() => expect(Socket.sockets.has("update_1")).toBe(true));
    const oldSocket = Socket.sockets.get("update_1");
    first.unmount();
    mount();
    await waitFor(() => expect(api.job).toHaveBeenCalledWith("update_1"));
    await waitFor(() => expect(Socket.sockets.get("update_1")).not.toBe(oldSocket));
    expect(screen.getByRole("button", { name: "更新并构建快照" })).toBeDisabled();
    const reads = vi.mocked(api.dataStatus).mock.calls.length;
    await act(async () => { Socket.sockets.get("update_1")!.emit("update_1", "done", { snapshot_id: "snapshot_restored" }); });
    expect(await screen.findByText(/数据更新与快照构建完成.*snapshot_restored/)).toBeInTheDocument();
    expect(api.dataStatus).toHaveBeenCalledTimes(reads + 1);
    expect(sessionStorage.getItem("qc_data_job:http://backend-a")).toBeNull();
    expect(api.updateData).toHaveBeenCalledTimes(1);
    expect(api.buildSnapshot).not.toHaveBeenCalled();
  });

  it("never resumes another API base's saved job", async () => {
    sessionStorage.setItem("qc_data_job:http://backend-a", JSON.stringify({ id: "update_a", kind: "data_update" }));
    connection.base = "http://backend-b";
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    expect(await screen.findByRole("button", { name: "更新并构建快照" })).not.toBeDisabled();
    expect(api.job).not.toHaveBeenCalled();
    expect(Socket.sockets.has("update_a")).toBe(false);
    expect(sessionStorage.getItem("qc_data_job:http://backend-a")).not.toBeNull();
  });

  it.each(["missing", "invalid kind"])("clears a restored %s job with a recovery message", async (failure) => {
    sessionStorage.setItem("qc_data_job:http://backend-a", JSON.stringify({ id: "update_old", kind: "data_update" }));
    if (failure === "missing") vi.mocked(api.job).mockRejectedValue(Object.assign(new Error("job not found"), { status: 404 }));
    else vi.mocked(api.job).mockResolvedValue({ id: "update_old", kind: "backtest", status: "running" } as never);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    expect(await screen.findByText(/无法恢复上次数据任务.*检查数据与快照/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).not.toBeDisabled();
    expect(sessionStorage.getItem("qc_data_job:http://backend-a")).toBeNull();
  });

  it("keeps an offline job for retry and consumes an already-finished restored result", async () => {
    sessionStorage.setItem("qc_data_job:http://backend-a", JSON.stringify({ id: "update_saved", kind: "data_update" }));
    vi.mocked(api.job).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      id: "update_saved", kind: "data_update", status: "done", progress: 1, result: { snapshot_id: "snapshot_offpage" },
    } as never);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><DataPage /></MemoryRouter>
    </QueryClientProvider>);
    const retry = await screen.findByRole("button", { name: "重试任务连接" });
    expect(sessionStorage.getItem("qc_data_job:http://backend-a")).not.toBeNull();
    expect(screen.getByRole("button", { name: "更新并构建快照" })).toBeDisabled();
    fireEvent.click(retry);
    expect(await screen.findByText(/数据更新与快照构建完成.*snapshot_offpage/)).toBeInTheDocument();
    expect(sessionStorage.getItem("qc_data_job:http://backend-a")).toBeNull();
    expect(api.job).toHaveBeenCalledTimes(2);
    expect(api.updateData).not.toHaveBeenCalled();
    expect(api.buildSnapshot).not.toHaveBeenCalled();
  });
});
