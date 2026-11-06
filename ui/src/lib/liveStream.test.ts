import { createElement as h } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { configure } from "../api/client";
import SettingsPage from "../pages/SettingsPage";
import { subscribeLiveQuotes } from "./liveStream";

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = Socket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn(() => { this.readyState = 3; });
  constructor(readonly url: string) { Socket.instances.push(this); }
}

const oldBase = "http://127.0.0.1:8000";
const newBase = "http://127.0.0.1:9100";
const quoteKey = ["live", "quotes", "600000"];
let client: QueryClient;
let subscriptions: (() => void)[] = [];

afterEach(() => {
  subscriptions.forEach((unsubscribe) => unsubscribe());
  subscriptions = [];
  client?.clear();
  Socket.instances = [];
  vi.unstubAllGlobals();
});

function frame(source: string): MessageEvent {
  return new MessageEvent("message", {
    data: JSON.stringify({ type: "snapshot", status: {}, indices: {}, quotes: { source, quotes: [] } }),
  });
}

describe("saving a different authenticated connection", () => {
  it("clears old results, replaces the shared socket and ignores late old frames and closes", async () => {
    configure(oldBase, "old-token");
    vi.stubGlobal("WebSocket", Socket);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const body = url.endsWith("/health") || url.endsWith("/api/meta")
        ? { version: "test", engine_backend: "cpp", data_root: "data" }
        : url.endsWith("/api/live/status") ? { enabled: false } : { snapshots: [], providers: [] };
      return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    }));
    client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    client.setQueryData(["experiments", 100], [{ run_id: "old-server-run" }]);
    subscriptions.push(subscribeLiveQuotes(["600000"], (message) => {
      client.setQueryData(quoteKey, message.quotes);
    }));
    const oldSocket = Socket.instances[0];
    const oldMessage = oldSocket.onmessage!;
    const oldClose = oldSocket.onclose!;
    oldMessage(frame("old"));
    expect(client.getQueryData(quoteKey)).toMatchObject({ source: "old" });

    render(h(QueryClientProvider, { client }, h(MemoryRouter, null, h(SettingsPage))));
    fireEvent.change(screen.getByLabelText("API 地址"), { target: { value: newBase } });
    fireEvent.change(screen.getByLabelText("Bearer Token"), { target: { value: "new-token" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(oldSocket.close).toHaveBeenCalledOnce());
    expect(client.getQueryData(["experiments", 100])).toBeUndefined();
    expect(client.getQueryData(quoteKey)).toBeUndefined();
    const newSocket = Socket.instances[1];
    expect(newSocket.url).toContain("127.0.0.1:9100/ws/live?token=new-token");

    // Events queued by the old connection must neither publish nor detach the new socket.
    oldMessage(frame("late-old"));
    oldClose();
    expect(client.getQueryData(quoteKey)).toBeUndefined();
    subscriptions.push(subscribeLiveQuotes(["600000"], () => undefined));
    expect(Socket.instances).toHaveLength(2);
    newSocket.onmessage!(frame("new"));
    expect(client.getQueryData(quoteKey)).toMatchObject({ source: "new" });
  });
});
