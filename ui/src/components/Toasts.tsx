import { Toaster } from "./Toaster";

/** v1 compatibility wrapper: App.tsx imports `Toasts`; it now mounts sonner. */
export default function Toasts() {
  return <Toaster />;
}
