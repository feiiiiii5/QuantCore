import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("shows a clear title and hint", () => {
    render(<EmptyState title="还没有实验" hint="先运行一次回测" />);
    expect(screen.getByText("还没有实验")).toBeInTheDocument();
    expect(screen.getByText("先运行一次回测")).toBeInTheDocument();
  });
});
