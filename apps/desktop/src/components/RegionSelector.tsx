import { useRef, useState, type MouseEvent } from "react";

import type { RegionSelection } from "@genie/contracts";

import { captureImageUrl } from "../lib/api";

interface RegionSelectorProps {
  captureId: string;
  imageWidth: number;
  imageHeight: number;
  onConfirm(selection: RegionSelection): void;
  onCancel(): void;
}

export function RegionSelector({ captureId, imageWidth, imageHeight, onConfirm, onCancel }: RegionSelectorProps) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [selection, setSelection] = useState<RegionSelection | null>(null);

  const updateSelection = (event: MouseEvent<HTMLDivElement>) => {
    if (!dragStart || !imageRef.current) {
      return;
    }
    const rect = imageRef.current.getBoundingClientRect();
    const currentX = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
    const currentY = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
    const left = Math.min(dragStart.x, currentX);
    const top = Math.min(dragStart.y, currentY);
    const width = Math.abs(currentX - dragStart.x);
    const height = Math.abs(currentY - dragStart.y);
    const scaleX = imageWidth / rect.width;
    const scaleY = imageHeight / rect.height;
    setSelection({
      x: Math.round(left * scaleX),
      y: Math.round(top * scaleY),
      width: Math.max(1, Math.round(width * scaleX)),
      height: Math.max(1, Math.round(height * scaleY)),
    });
  };

  return (
    <section className="tab-section region-selector">
      <div className="section-header">
        <div>
          <h3>Select a region</h3>
          <p>Drag over the captured screen preview to create a region context.</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" disabled={!selection} onClick={() => selection && onConfirm(selection)}>
            Use Region
          </button>
        </div>
      </div>

      <div
        className="selection-canvas"
        onMouseDown={(event) => {
          const rect = imageRef.current?.getBoundingClientRect();
          if (!rect) {
            return;
          }
          setDragStart({
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
          });
          setSelection(null);
        }}
        onMouseMove={updateSelection}
        onMouseUp={() => setDragStart(null)}
      >
        <img ref={imageRef} alt="Captured screen" src={captureImageUrl(captureId)} />
        {selection ? (
          <div
            className="selection-box"
            style={{
              left: `${(selection.x / imageWidth) * 100}%`,
              top: `${(selection.y / imageHeight) * 100}%`,
              width: `${(selection.width / imageWidth) * 100}%`,
              height: `${(selection.height / imageHeight) * 100}%`,
            }}
          />
        ) : null}
      </div>
    </section>
  );
}
