import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Launcher } from "../src/components/Launcher";

describe("Launcher", () => {
  it("renders the Genie trigger", () => {
    render(<Launcher open={false} onToggle={() => undefined} />);
    expect(screen.getByRole("button", { name: /open genie/i })).toBeTruthy();
  });
});
