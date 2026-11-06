import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useJobProgress } from "./useJobProgress";

vi.mock("../api/client", () => ({ wsUrl: () => "ws://localhost/job", api: { job: vi.fn() } }));

afterEach(() => vi.unstubAllGlobals());

it("consumes the terminal job in an error frame without reconnecting", () => {
  let socket: { onmessage?: (event: { data: string }) => void; close: ReturnType<typeof vi.fn> };
  class Socket {
    close = vi.fn();
    constructor() { socket = this; }
  }
  vi.stubGlobal("WebSocket", Socket);
  const terminal = vi.fn();
  const { result, unmount } = renderHook(() => useJobProgress("job_1", terminal));
  const job = { id: "job_1", status: "failed", error: "invalid configuration", progress: 0.2 };
  act(() => socket.onmessage?.({ data: JSON.stringify({ type: "error", error: job.error, job }) }));
  expect(result.current.job?.status).toBe("failed");
  expect(result.current.error).toBe(job.error);
  expect(terminal).toHaveBeenCalledExactlyOnceWith(job);
  expect(socket!.close).toHaveBeenCalled();
  unmount();
});
