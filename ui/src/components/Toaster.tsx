import { useEffect } from "react";
import { Toaster as SonnerToaster, toast } from "sonner";
import type { ToastMessage } from "../lib/notify";

/**
 * sonner mount point + adapter for the legacy qc-notify events emitted by `notify()`.
 * lib/notify.ts stays untouched, so existing call sites keep working.
 */
export function Toaster() {
  useEffect(() => {
    const handler = (event: Event) => {
      const message = (event as CustomEvent<ToastMessage>).detail;
      if (!message || typeof message.title !== "string") return;
      const options = { id: message.id, description: message.body };
      if (message.kind === "success") toast.success(message.title, options);
      else if (message.kind === "error") toast.error(message.title, options);
      else toast(message.title, options);
    };
    window.addEventListener("qc-notify", handler);
    return () => window.removeEventListener("qc-notify", handler);
  }, []);
  return (
    <SonnerToaster
      position="bottom-right"
      closeButton
      visibleToasts={4}
      offset={16}
      toastOptions={{ className: "qc-toast" }}
    />
  );
}

export default Toaster;
