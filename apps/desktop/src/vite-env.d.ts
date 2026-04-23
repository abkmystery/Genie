/// <reference types="vite/client" />

declare global {
  interface Window {
    genieShell?: {
      setPanelOpen(open: boolean): Promise<void>;
      resizePanel(size: { width: number; height: number }): Promise<{ width: number; height: number }>;
      getLaunchProfile(): Promise<string | null>;
      ensureBackend(): Promise<{ ok: boolean; baseUrl: string; status: { state: string; last_error: string | null; base_url: string } }>;
      getBackendStatus(): Promise<{ state: string; last_error: string | null; base_url: string }>;
      openLogsFolder(): Promise<{ ok: boolean; dir: string }>;
      beginScreenCapture(): Promise<{ ok: boolean }>;
      endScreenCapture(): Promise<{ ok: boolean }>;
      setGuidanceOverlay(
        payload:
          | {
              target: { x: number; y: number; width: number; height: number; capture_width?: number | null; capture_height?: number | null; target_label: string; annotation?: string | null; render_style: "arrow_only" | "highlight_only" | "arrow_pulse" };
              title: string;
              stepLabel: string;
              statusLabel: string;
              showDebugLabels: boolean;
            }
          | null,
      ): Promise<void>;
      openRegionOverlay(payload: { captureId: string; width: number; height: number }): Promise<void>;
      sendRegionSelection(selection: { x: number; y: number; width: number; height: number } | null): void;
      onRegionSelection(
        handler: (selection: { x: number; y: number; width: number; height: number } | null) => void,
      ): () => void;
      onGuidanceOverlay(
        handler: (
          payload:
            | {
                target: { x: number; y: number; width: number; height: number; capture_width?: number | null; capture_height?: number | null; target_label: string; annotation?: string | null; render_style: "arrow_only" | "highlight_only" | "arrow_pulse" };
                title: string;
                stepLabel: string;
                statusLabel: string;
                showDebugLabels: boolean;
              }
            | null,
        ) => void,
      ): () => void;
    };
  }
}

export {};
