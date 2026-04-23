import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function RegionOverlay() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const imageWidth = Number(params.get("w") ?? "0");
  const imageHeight = Number(params.get("h") ?? "0");

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [selection, setSelection] = useState<{ x: number; y: number; width: number; height: number } | null>(null);

  useEffect(() => {
    // Ensure key handling (Esc) works without requiring a click first.
    const timer = setTimeout(() => {
      document.querySelector<HTMLElement>(".overlay-root")?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const updateSelection = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragStart || !canvasRef.current) {
      return;
    }
    const rect = canvasRef.current.getBoundingClientRect();
    const currentX = clamp(event.clientX - rect.left, 0, rect.width);
    const currentY = clamp(event.clientY - rect.top, 0, rect.height);

    const left = Math.min(dragStart.x, currentX);
    const top = Math.min(dragStart.y, currentY);
    const width = Math.abs(currentX - dragStart.x);
    const height = Math.abs(currentY - dragStart.y);

    const scaleX = rect.width ? imageWidth / rect.width : 1;
    const scaleY = rect.height ? imageHeight / rect.height : 1;

    setSelection({
      x: Math.round(left * scaleX),
      y: Math.round(top * scaleY),
      width: Math.max(1, Math.round(width * scaleX)),
      height: Math.max(1, Math.round(height * scaleY)),
    });
  };

  return (
    <div
      className="overlay-root"
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          window.genieShell?.sendRegionSelection(null);
        }
      }}
    >
      <div
        className="overlay-canvas"
        ref={canvasRef}
        onMouseDown={(event) => {
          const rect = canvasRef.current?.getBoundingClientRect();
          if (!rect) return;
          setDragStart({
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
          });
          setSelection(null);
        }}
        onMouseMove={updateSelection}
        onMouseUp={() => setDragStart(null)}
      >
        {selection ? (
          <div
            className="overlay-selection"
            style={{
              left: `${(selection.x / imageWidth) * 100}%`,
              top: `${(selection.y / imageHeight) * 100}%`,
              width: `${(selection.width / imageWidth) * 100}%`,
              height: `${(selection.height / imageHeight) * 100}%`,
            }}
          />
        ) : null}
      </div>

      <div className="overlay-hud">
        <div className="overlay-card">
          <strong>Drag to select region</strong>
          <p>Press Esc to cancel. Click Use Region to confirm.</p>
        </div>
        <div className="overlay-actions">
          <button
            type="button"
            onClick={() => {
              window.genieShell?.sendRegionSelection(null);
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!selection}
            onClick={() => {
              if (!selection) return;
              window.genieShell?.sendRegionSelection(selection);
            }}
          >
            Use Region
          </button>
        </div>
      </div>
    </div>
  );
}
