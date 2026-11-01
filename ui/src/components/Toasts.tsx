import { useEffect, useState } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { ToastMessage } from "../lib/notify";

const icons = { info: Info, success: CheckCircle2, error: XCircle };

export default function Toasts() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  useEffect(() => {
    const handler = (event: Event) => {
      const message = (event as CustomEvent<ToastMessage>).detail;
      if (!message) return;
      setMessages((current) => [...current.slice(-3), message]);
      window.setTimeout(() => setMessages((current) => current.filter((item) => item.id !== message.id)), 5000);
    };
    window.addEventListener("qc-notify", handler);
    return () => window.removeEventListener("qc-notify", handler);
  }, []);
  if (!messages.length) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {messages.map((message) => {
        const Icon = icons[message.kind];
        return (
          <div key={message.id} className={`toast ${message.kind}`}>
            <Icon size={16} />
            <div><strong>{message.title}</strong>{message.body ? <small>{message.body}</small> : null}</div>
            <button className="icon-btn" aria-label="关闭通知" onClick={() => setMessages((current) => current.filter((item) => item.id !== message.id))}><X size={13} /></button>
          </div>
        );
      })}
    </div>
  );
}
