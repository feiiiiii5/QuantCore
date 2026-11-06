import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { applyAppearance } from "./lib/appearance";
import "./styles.css";

// Apply the persisted theme/density/colour mode before the first paint (no flash).
applyAppearance();

// `qc serve --open` appends ?token=...; persist it and remove it from the URL/referrer.
const initial = new URLSearchParams(window.location.search);
const urlToken = initial.get("token");
if (urlToken) {
  localStorage.setItem("qc_token", urlToken);
  initial.delete("token");
  const query = initial.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
}

// A hosted test frontend needs an explicit connection to the visitor's local service.
if (import.meta.env.VITE_QC_DEFAULT_API_BASE && !localStorage.getItem("qc_token") && window.location.pathname === "/") {
  window.history.replaceState(null, "", "/settings");
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 0, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
