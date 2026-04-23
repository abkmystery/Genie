import { useEffect, useState } from "react";

import type { OverlayTarget } from "@genie/contracts";

interface GuidanceOverlayState {
  target: OverlayTarget;
  title: string;
  stepLabel: string;
  statusLabel: string;
  showDebugLabels: boolean;
}

export default function GuidanceOverlay() {
  const [overlay, setOverlay] = useState<GuidanceOverlayState | null>(null);

  useEffect(() => {
    return window.genieShell?.onGuidanceOverlay((payload) => {
      setOverlay(payload);
    });
  }, []);

  return (
    <div className="overlay-root guidance-root">
      {overlay?.target ? (
        <>
          <div
            className={`guidance-highlight ${overlay.target.render_style}`}
            style={{
              left: `${overlay.target.x}px`,
              top: `${overlay.target.y}px`,
              width: `${overlay.target.width}px`,
              height: `${overlay.target.height}px`,
            }}
          />
          {overlay.target.render_style !== "highlight_only" ? (
            <div
              className="guidance-arrow"
              style={{
                left: `${Math.max(18, overlay.target.x + overlay.target.width / 2 - 112)}px`,
                top: `${Math.max(18, overlay.target.y + overlay.target.height / 2 - 14)}px`,
              }}
            >
              <div className="guidance-arrow-line" />
              <div className="guidance-arrow-head" />
            </div>
          ) : null}
          <div
            className="guidance-crosshair"
            style={{
              left: `${overlay.target.x + overlay.target.width / 2 - 7}px`,
              top: `${overlay.target.y + overlay.target.height / 2 - 7}px`,
            }}
          />
          <div
            className="guidance-badge"
            style={{
              left: `${Math.min(window.innerWidth - 340, Math.max(18, overlay.target.x))}px`,
              top: `${Math.max(18, overlay.target.y + overlay.target.height + 12)}px`,
            }}
          >
            <strong>{overlay.stepLabel}</strong>
            <p>{overlay.target.annotation ?? overlay.target.target_label}</p>
            <small>{overlay.statusLabel}</small>
            {overlay.showDebugLabels ? <small>{overlay.target.target_label}</small> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
