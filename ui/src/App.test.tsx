import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App shell", () => {
  it("renders nav and disclaimer", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("QuantCore")).toBeInTheDocument();
    expect(screen.getByText("回测")).toBeInTheDocument();
    expect(screen.getByText(/不构成投资建议/)).toBeInTheDocument();
  });
});
