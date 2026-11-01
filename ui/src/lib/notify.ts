export interface ToastMessage {
  id: string;
  title: string;
  body?: string;
  kind: "info" | "success" | "error";
}

export function notify(input: Omit<ToastMessage, "id">): void {
  const message: ToastMessage = { ...input, id: `toast_${Date.now()}_${Math.random().toString(16).slice(2, 8)}` };
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ToastMessage>("qc-notify", { detail: message }));
    if ("Notification" in window && Notification.permission === "granted") {
      try { new Notification(message.title, { body: message.body }); } catch { /* browser may block */ }
    }
  }
}

export async function ensureNotificationPermission(): Promise<NotificationPermission> {
  if (typeof window === "undefined" || !("Notification" in window)) return "denied";
  if (Notification.permission === "granted" || Notification.permission === "denied") return Notification.permission;
  try { return await Notification.requestPermission(); } catch { return "denied"; }
}
