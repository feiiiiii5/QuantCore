import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveQuotesPayload } from "./types";
import { useLiveQuotes } from "./queries";

const transport = vi.hoisted(() => ({
  quotes: vi.fn(),
  listeners: new Map<string, (message: { quotes: LiveQuotesPayload }) => void>(),
}));
vi.mock("./client", () => ({ api: { liveQuotes: transport.quotes } }));
vi.mock("../lib/liveStream", () => ({
  subscribeLiveQuotes: (codes: string[], listener: (message: { quotes: LiveQuotesPayload }) => void) => {
    const key = codes.join(",");
    transport.listeners.set(key, listener);
    return () => { transport.listeners.delete(key); };
  },
}));

function quote(code: string, price: number): LiveQuotesPayload {
  return { as_of: "2026-11-06T10:00:00+08:00", source: "fixture", stale: false, quotes: [{ code, price }] } as LiveQuotesPayload;
}
function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Provider({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("live quote identity and HTTP refresh", () => {
  beforeEach(() => {
    transport.quotes.mockReset();
    transport.listeners.clear();
  });

  it("never shows the previous security's streamed quote after switching codes", async () => {
    transport.quotes.mockImplementation(async ([code]: string[]) => quote(code, code === "600000" ? 10 : 20));
    const hook = renderHook(({ code }) => useLiveQuotes([code]), { initialProps: { code: "600000" }, wrapper: wrapper() });
    await waitFor(() => expect(hook.result.current.data?.quotes[0].code).toBe("600000"));
    act(() => transport.listeners.get("600000")!({ quotes: quote("600000", 11) }));
    await waitFor(() => expect(hook.result.current.data?.quotes[0].price).toBe(11));

    hook.rerender({ code: "000001" });
    expect(hook.result.current.data?.quotes[0].code).not.toBe("600000");
    await waitFor(() => expect(hook.result.current.data?.quotes[0].code).toBe("000001"));
    expect(transport.listeners.has("600000")).toBe(false);
  });

  it("refreshes over HTTP when WebSocket frames stop after a successful frame", async () => {
    vi.useFakeTimers();
    transport.quotes.mockResolvedValueOnce(quote("600000", 10)).mockResolvedValue(quote("600000", 12));
    const hook = renderHook(() => useLiveQuotes(["600000"]), { wrapper: wrapper() });
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(50); });
      expect(hook.result.current.data?.quotes[0].price).toBe(10);
      act(() => transport.listeners.get("600000")!({ quotes: quote("600000", 11) }));
      await act(async () => { await vi.advanceTimersByTimeAsync(50); });
      expect(hook.result.current.data?.quotes[0].price).toBe(11);
      await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
      expect(transport.quotes).toHaveBeenCalledTimes(2);
      expect(hook.result.current.data?.quotes[0].price).toBe(12);
    } finally {
      hook.unmount();
      vi.useRealTimers();
    }
  });
});
