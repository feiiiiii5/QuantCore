import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ParamForm, { defaultsFromSchema } from "./ParamForm";

describe("ParamForm", () => {
  it("builds defaults and edits numbers/booleans", () => {
    const onChange = vi.fn();
    const schema = {
      properties: {
        top_n: { title: "持仓数", type: "integer", minimum: 1, default: 10 },
        enabled: { title: "启用", type: "boolean", default: true },
      },
    };
    expect(defaultsFromSchema(schema)).toEqual({ top_n: 10, enabled: true });
    render(<ParamForm schema={schema} value={{ top_n: 10, enabled: true }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/持仓数/), { target: { value: "20" } });
    expect(onChange).toHaveBeenLastCalledWith({ top_n: 20, enabled: true });
    fireEvent.click(screen.getByLabelText(/启用/));
    expect(onChange).toHaveBeenLastCalledWith({ top_n: 10, enabled: false });
  });
  it("renders enum options", () => {
    render(<ParamForm schema={{ properties: { mode: { title: "模式", type: "string", enum: ["monthly", "weekly"] } } }} value={{}} onChange={() => undefined} />);
    expect(screen.getByRole("option", { name: "monthly" })).toBeInTheDocument();
  });
});
