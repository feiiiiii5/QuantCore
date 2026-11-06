import { useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../api/client";
import type { Job } from "../api/types";

export type JobTransport = "ws" | "poll" | null;

function isJob(value: unknown): value is Job {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.id === "string" && typeof candidate.status === "string";
}

export interface JobProgress {
  job: Job | null;
  transport: JobTransport;
  error: string | null;
  reconnects: number;
}

/**
 * Follow a job over WS and fall back to HTTP polling. The hook owns every
 * socket/timer and always cleans up on unmount or job change.
 */
export function useJobProgress(jobId: string | null, onTerminal?: (job: Job) => void): JobProgress {
  const [state, setState] = useState<JobProgress>({ job: null, transport: null, error: null, reconnects: 0 });
  const terminalRef = useRef(onTerminal);
  terminalRef.current = onTerminal;

  useEffect(() => {
    setState({ job: null, transport: null, error: null, reconnects: 0 });
    if (!jobId) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let pollTimer: number | null = null;
    let attempt = 0;
    let terminal = false;

    const finish = (job: Job) => {
      if (terminal) return;
      terminal = true;
      clearTimers();
      socket?.close();
      setState((current) => ({ ...current, job, error: job.status === "failed" ? (job.error ?? "job failed") : null }));
      terminalRef.current?.(job);
    };
    const apply = (job: Job) => {
      if (disposed) return;
      setState((current) => ({ ...current, job, error: job.status === "failed" ? (job.error ?? "job failed") : null }));
      if (job.status === "done" || job.status === "failed" || job.status === "cancelled") finish(job);
    };
    const clearTimers = () => {
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (pollTimer !== null) window.clearInterval(pollTimer);
    };
    const startPolling = () => {
      if (disposed || terminal) return;
      setState((current) => ({ ...current, transport: "poll" }));
      const tick = async () => {
        try {
          const job = await api.job(jobId);
          apply(job);
        } catch (error) {
          if (!disposed) setState((current) => ({ ...current, error: error instanceof Error ? error.message : String(error) }));
        }
      };
      void tick();
      pollTimer = window.setInterval(() => { void tick(); }, 700);
    };
    const connect = () => {
      if (disposed || terminal) return;
      try {
        socket = new WebSocket(wsUrl(jobId));
      } catch {
        startPolling();
        return;
      }
      socket.onopen = () => {
        if (disposed) return;
        attempt = 0;
        setState((current) => ({ ...current, transport: "ws", error: null }));
      };
      socket.onmessage = (event: MessageEvent<unknown>) => {
        if (typeof event.data !== "string") return;
        try {
          const message: unknown = JSON.parse(event.data);
          if (!message || typeof message !== "object") return;
          const payload = message as Record<string, unknown>;
          if (isJob(payload.job)) {
            apply(payload.job);
            return;
          }
          const messageError = payload.error;
          if (payload.type === "error" && typeof messageError === "string") {
            setState((current) => ({ ...current, error: messageError }));
            return;
          }
        } catch {
          /* ignore malformed frames; polling remains available */
        }
      };
      socket.onerror = () => { socket?.close(); };
      socket.onclose = () => {
        socket = null;
        if (disposed || terminal) return;
        attempt += 1;
        setState((current) => ({ ...current, reconnects: attempt, transport: current.transport === "ws" ? null : current.transport }));
        if (attempt <= 3) {
          retryTimer = window.setTimeout(connect, 400 * 2 ** (attempt - 1));
        } else {
          startPolling();
        }
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimers();
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }
    };
  }, [jobId]);

  return state;
}
