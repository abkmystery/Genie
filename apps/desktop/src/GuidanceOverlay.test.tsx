import { render, screen } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it } from "vitest";

import GuidanceOverlay from "./GuidanceOverlay";

describe("GuidanceOverlay", () => {
  it("renders and clears overlay state from shell events", async () => {
    let listener: ((payload: unknown) => void) | null = null;
    window.genieShell = {
      onGuidanceOverlay: (handler) => {
        listener = handler as (payload: unknown) => void;
        return () => {
          listener = null;
        };
      },
    } as typeof window.genieShell;

    render(<GuidanceOverlay />);

    await act(async () => {
      listener?.({
        target: {
          x: 100,
          y: 120,
          width: 90,
          height: 28,
          target_label: "Submit",
          annotation: "Click Submit",
          render_style: "arrow_pulse",
        },
        title: "Submit the form",
        stepLabel: "Step 1 of 3",
        statusLabel: "Grounded",
        showDebugLabels: false,
      });
    });

    expect(screen.getByText("Step 1 of 3")).not.toBeNull();
    expect(screen.getByText("Click Submit")).not.toBeNull();

    await act(async () => {
      listener?.(null);
    });

    expect(screen.queryByText("Step 1 of 3")).toBeNull();
  });
});
