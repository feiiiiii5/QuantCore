/** Shared live-quote WebSocket hub (one socket per code set, with backoff).
 *
 * The backend exposes /ws/live { type, status, indices, quotes }; instead of polling every
 * page we multiplex subscribers onto one socket per unique code list.  If the connection
 * cannot be established the hooks fall back to HTTP polling, so the UI is never stuck.
 */
import { wsLiveUrl } from "../api/client";
import type { LiveQuotesPayload, LiveStatus } from "../api/types";

export interface LiveStreamMessage {
  type: "snapshot";
  status: LiveStatus;
  indices: { as_of: string | null; source: string; stale: boolean; quotes: unknown[] };
  quotes: LiveQuotesPayload;
}

type Listener = (message: LiveStreamMessage) => void;

interface Stream {
  socket: WebSocket | null;
  listeners: Set<Listener>;
  timer: number | null;
  retries: number;
  codes: string[];
}

const streams = new Map<string, Stream>();

function streamKey(codes: string[]): string {
  return codes.slice().sort().join(",");
}

function scheduleReconnect(key: string, stream: Stream): void {
  if (stream.listeners.size === 0 || stream.timer != null) return;
  const delay = Math.min(30_000, 1000 * 2 ** Math.min(stream.retries, 5));
  stream.retries += 1;
  stream.timer = window.setTimeout(() => {
    stream.timer = null;
    open(key, stream);
  }, delay);
}

function open(key: string, stream: Stream): void {
  if (stream.listeners.size === 0 || stream.socket) return;
  let socket: WebSocket;
  try {
    const suffix = stream.codes.length ? "&codes=" + encodeURIComponent(stream.codes.join(",")) : "";
    socket = new WebSocket(wsLiveUrl() + suffix);
  } catch {
    scheduleReconnect(key, stream);
    return;
  }
  stream.socket = socket;
  socket.onopen = () => {
    if (stream.socket !== socket) return;
    stream.retries = 0;
  };
  socket.onmessage = (event) => {
    if (stream.socket !== socket) return;
    try {
      const message = JSON.parse(String(event.data)) as LiveStreamMessage;
      if (message && message.type === "snapshot" && message.quotes) {
        stream.listeners.forEach((listener) => listener(message));
      }
    } catch {
      /* ignore malformed frames; polling fallback still covers the UI */
    }
  };
  socket.onclose = () => {
    if (stream.socket !== socket) return;
    stream.socket = null;
    scheduleReconnect(key, stream);
  };
  socket.onerror = () => {
    if (stream.socket !== socket) return;
    try { socket.close(); } catch { /* noop */ }
  };
}

function ensure(codes: string[]): Stream {
  const key = streamKey(codes);
  const existing = streams.get(key);
  if (existing) {
    existing.codes = codes;
    return existing;
  }
  const stream: Stream = { socket: null, listeners: new Set(), timer: null, retries: 0, codes };
  streams.set(key, stream);
  return stream;
}

/** Subscribe to live quote frames for a code list; returns the unsubscribe function. */
export function subscribeLiveQuotes(codes: string[], listener: Listener): () => void {
  if (typeof window === "undefined") return () => undefined;
  const key = streamKey(codes);
  const stream = ensure(codes);
  stream.listeners.add(listener);
  // Register the listener before connecting: open() skips sockets without subscribers.
  open(key, stream);
  return () => {
    stream.listeners.delete(listener);
    if (stream.listeners.size > 0) return;
    if (stream.timer != null) window.clearTimeout(stream.timer);
    stream.timer = null;
    try { stream.socket?.close(); } catch { /* noop */ }
    stream.socket = null;
    streams.delete(key);
  };
}

/** Replace every shared connection after saving a different API base or bearer token. */
export function resetLiveStreams(): void {
  for (const [key, stream] of streams) {
    if (stream.timer != null) window.clearTimeout(stream.timer);
    stream.timer = null;
    stream.retries = 0;
    const previous = stream.socket;
    stream.socket = null;
    try { previous?.close(); } catch { /* noop */ }
    open(key, stream);
  }
}

/** True when at least one shared socket is connected (used by pages for a live badge). */
export function liveStreamConnected(): boolean {
  for (const stream of streams.values()) {
    if (stream.socket && stream.socket.readyState === WebSocket.OPEN) return true;
  }
  return false;
}
