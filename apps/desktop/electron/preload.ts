import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("genieShell", {
  setPanelOpen: (open: boolean) => ipcRenderer.invoke("genie:set-panel-open", open),
  resizePanel: (size: { width: number; height: number }) => ipcRenderer.invoke("genie:resize-panel", size),
  getLaunchProfile: (): Promise<string | null> => ipcRenderer.invoke("genie:get-cli-profile"),
  ensureBackend: () => ipcRenderer.invoke("genie:ensure-backend"),
  getBackendStatus: () => ipcRenderer.invoke("genie:get-backend-status"),
  openLogsFolder: () => ipcRenderer.invoke("genie:open-logs-folder"),
  beginScreenCapture: () => ipcRenderer.invoke("genie:begin-screen-capture"),
  endScreenCapture: () => ipcRenderer.invoke("genie:end-screen-capture"),
  setGuidanceOverlay: (
    payload:
          | {
          target: { x: number; y: number; width: number; height: number; capture_width?: number | null; capture_height?: number | null; target_label: string; annotation?: string | null; render_style: "arrow_only" | "highlight_only" | "arrow_pulse" };
          title: string;
          stepLabel: string;
          statusLabel: string;
          showDebugLabels: boolean;
        }
      | null,
  ) => ipcRenderer.invoke("genie:set-guidance-overlay", payload),
  openRegionOverlay: (payload: { captureId: string; width: number; height: number }) =>
    ipcRenderer.invoke("genie:open-region-overlay", payload),
  sendRegionSelection: (selection: { x: number; y: number; width: number; height: number } | null) =>
    ipcRenderer.send("genie:region-selection", selection),
  onRegionSelection: (handler: (selection: { x: number; y: number; width: number; height: number } | null) => void) => {
    const listener = (_event: unknown, selection: { x: number; y: number; width: number; height: number } | null) => {
      handler(selection);
    };
    ipcRenderer.on("genie:region-selection", listener);
    return () => ipcRenderer.removeListener("genie:region-selection", listener);
  },
  onGuidanceOverlay: (
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
  ) => {
    const listener = (
      _event: unknown,
      payload:
        | {
            target: { x: number; y: number; width: number; height: number; capture_width?: number | null; capture_height?: number | null; target_label: string; annotation?: string | null; render_style: "arrow_only" | "highlight_only" | "arrow_pulse" };
            title: string;
            stepLabel: string;
            statusLabel: string;
            showDebugLabels: boolean;
          }
        | null,
    ) => {
      handler(payload);
    };
    ipcRenderer.on("genie:guidance-overlay", listener);
    return () => ipcRenderer.removeListener("genie:guidance-overlay", listener);
  },
});
