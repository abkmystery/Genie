import { app, BrowserWindow, ipcMain, screen, session, shell } from "electron";
import fs from "node:fs";
import path from "node:path";
import { ensureBackendReady, getBackendBaseUrl, getBackendStatus, getLogsDir, stopBackend } from "./backend";

const DEV_URL = "http://127.0.0.1:5173";
const isDev = !app.isPackaged;
const LAUNCHER_SIZE = { width: 92, height: 92 };
const PANEL_SIZE = { width: 480, height: 760 };
const PANEL_MIN_SIZE = { width: 400, height: 620 };
const PANEL_MAX_SIZE = { width: 860, height: 980 };

let mainWindow: BrowserWindow | null = null;
let regionWindow: BrowserWindow | null = null;
let guidanceWindow: BrowserWindow | null = null;
type GuidancePayload = {
  target: {
    x: number;
    y: number;
    width: number;
    height: number;
    capture_width?: number | null;
    capture_height?: number | null;
    target_label: string;
    annotation?: string | null;
    render_style: string;
  };
  title: string;
  stepLabel: string;
  statusLabel: string;
  showDebugLabels: boolean;
};

let currentGuidanceOverlay: GuidancePayload | null = null;
let panelSize = { ...PANEL_SIZE };
let hiddenForCapture = false;

function appendElectronLog(line: string) {
  try {
    const dir = getLogsDir();
    const logFile = path.join(dir, "electron.log");
    fs.appendFileSync(logFile, `[${new Date().toISOString()}] ${line}\n`, { encoding: "utf-8" });
  } catch {
    // ignore
  }
}

function getCliProfile(): string | null {
  const arg = process.argv.find((value) => value.startsWith("--profile="));
  return arg ? arg.split("=")[1] ?? null : null;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function computeBounds(open: boolean, current?: Electron.Rectangle) {
  const size = open ? panelSize : LAUNCHER_SIZE;
  const display = current ? screen.getDisplayMatching(current).workArea : screen.getPrimaryDisplay().workArea;

  const anchorX = current ? current.x + current.width : display.x + display.width - 24;
  const anchorY = current ? current.y + current.height : display.y + display.height - 24;

  const x = clamp(anchorX - size.width, display.x, display.x + display.width - size.width);
  const y = clamp(anchorY - size.height, display.y, display.y + display.height - size.height);

  return {
    width: size.width,
    height: size.height,
    x,
    y,
  };
}

function normalizeGuidancePayload(payload: GuidancePayload): GuidancePayload {
  const display = screen.getPrimaryDisplay();
  const target = payload.target;
  const captureWidth = target.capture_width || 0;
  const captureHeight = target.capture_height || 0;
  const scaleX = captureWidth > 0 ? display.bounds.width / captureWidth : 1 / display.scaleFactor;
  const scaleY = captureHeight > 0 ? display.bounds.height / captureHeight : 1 / display.scaleFactor;

  return {
    ...payload,
    target: {
      ...target,
      x: Math.round(display.bounds.x + target.x * scaleX),
      y: Math.round(display.bounds.y + target.y * scaleY),
      width: Math.max(18, Math.round(target.width * scaleX)),
      height: Math.max(18, Math.round(target.height * scaleY)),
    },
  };
}

async function createWindow() {
  // Start backend in the background and let the renderer show a loading state immediately.
  void ensureBackendReady().catch((cause) => {
    appendElectronLog(`background backend startup failed: ${cause instanceof Error ? cause.message : String(cause)}`);
  });

  const bounds = computeBounds(false);
  mainWindow = new BrowserWindow({
    ...bounds,
    frame: false,
    transparent: true,
    resizable: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.setMovable(true);
  mainWindow.setAlwaysOnTop(true, "screen-saver");
  mainWindow.setMenuBarVisibility(false);

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    appendElectronLog(`renderer did-fail-load code=${errorCode} desc=${errorDescription} url=${validatedURL}`);
  });
  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    appendElectronLog(`renderer process gone reason=${details.reason} exitCode=${details.exitCode}`);
  });
  mainWindow.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    appendElectronLog(`console level=${level} ${sourceId}:${line} ${message}`);
  });

  if (isDev) {
    appendElectronLog(`loadURL ${DEV_URL}`);
    await mainWindow.loadURL(DEV_URL);
  } else {
    appendElectronLog("loadFile dist/index.html");
    await mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

ipcMain.handle("genie:set-panel-open", (_event, open: boolean) => {
  if (!mainWindow) {
    return;
  }
  const bounds = computeBounds(open, mainWindow.getBounds());
  mainWindow.setBounds(bounds, true);
  mainWindow.setAlwaysOnTop(true, "screen-saver");
  mainWindow.showInactive();
  mainWindow.moveTop();
});

ipcMain.handle("genie:resize-panel", (_event, nextSize: { width: number; height: number }) => {
  if (!mainWindow) {
    return;
  }
  panelSize = {
    width: clamp(Math.round(nextSize.width), PANEL_MIN_SIZE.width, PANEL_MAX_SIZE.width),
    height: clamp(Math.round(nextSize.height), PANEL_MIN_SIZE.height, PANEL_MAX_SIZE.height),
  };
  const bounds = computeBounds(true, mainWindow.getBounds());
  mainWindow.setBounds(bounds, true);
  return panelSize;
});

ipcMain.handle("genie:get-cli-profile", () => getCliProfile());

ipcMain.handle("genie:ensure-backend", async () => {
  await ensureBackendReady();
  return { ok: true, baseUrl: getBackendBaseUrl(), status: getBackendStatus() };
});

ipcMain.handle("genie:get-backend-status", () => getBackendStatus());

ipcMain.handle("genie:open-logs-folder", async () => {
  const dir = getLogsDir();
  await shell.openPath(dir);
  return { ok: true, dir };
});

ipcMain.handle("genie:begin-screen-capture", async () => {
  hiddenForCapture = true;
  if (guidanceWindow && !guidanceWindow.isDestroyed()) {
    guidanceWindow.setOpacity(0);
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setOpacity(0);
  }
  await new Promise((resolve) => setTimeout(resolve, 120));
  return { ok: true };
});

ipcMain.handle("genie:end-screen-capture", () => {
  hiddenForCapture = false;
  if (guidanceWindow && !guidanceWindow.isDestroyed()) {
    guidanceWindow.setOpacity(1);
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setOpacity(1);
    mainWindow.setAlwaysOnTop(true, "screen-saver");
    mainWindow.showInactive();
    mainWindow.moveTop();
  }
  return { ok: true };
});

async function ensureGuidanceWindow(bounds: Electron.Rectangle) {
  if (guidanceWindow && !guidanceWindow.isDestroyed()) {
    guidanceWindow.setBounds(bounds);
    return guidanceWindow;
  }

  guidanceWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    focusable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    fullscreen: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  guidanceWindow.setIgnoreMouseEvents(true, { forward: true });

  const query = new URLSearchParams({ overlay: "guidance" }).toString();
  if (isDev) {
    await guidanceWindow.loadURL(`${DEV_URL}/?${query}`);
  } else {
    await guidanceWindow.loadFile(path.join(__dirname, "../dist/index.html"), { search: `?${query}` });
  }

  guidanceWindow.webContents.on("did-finish-load", () => {
    guidanceWindow?.webContents.send("genie:guidance-overlay", currentGuidanceOverlay);
  });
  guidanceWindow.on("closed", () => {
    guidanceWindow = null;
  });
  return guidanceWindow;
}

ipcMain.handle("genie:set-guidance-overlay", async (_event, payload) => {
  currentGuidanceOverlay = payload ? normalizeGuidancePayload(payload) : null;
  if (!payload) {
    if (guidanceWindow) {
      guidanceWindow.close();
      guidanceWindow = null;
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setAlwaysOnTop(true, "screen-saver");
      mainWindow.showInactive();
      mainWindow.moveTop();
    }
    return;
  }

  const display = screen.getPrimaryDisplay();
  const targetWindow = await ensureGuidanceWindow(display.bounds);
  targetWindow.setOpacity(hiddenForCapture ? 0 : 1);
  targetWindow.webContents.send("genie:guidance-overlay", currentGuidanceOverlay);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setAlwaysOnTop(true, "screen-saver");
    mainWindow.showInactive();
    mainWindow.moveTop();
  }
});

ipcMain.handle(
  "genie:open-region-overlay",
  async (_event, payload: { captureId: string; width: number; height: number }) => {
    if (regionWindow) {
      regionWindow.close();
      regionWindow = null;
    }

    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);

    regionWindow = new BrowserWindow({
      x: display.bounds.x,
      y: display.bounds.y,
      width: display.bounds.width,
      height: display.bounds.height,
      frame: false,
      transparent: true,
      resizable: false,
      movable: false,
      alwaysOnTop: true,
      fullscreen: true,
      skipTaskbar: true,
      focusable: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    const query = new URLSearchParams({
      overlay: "region",
      captureId: payload.captureId,
      w: String(payload.width),
      h: String(payload.height),
    }).toString();

    if (isDev) {
      await regionWindow.loadURL(`${DEV_URL}/?${query}`);
    } else {
      await regionWindow.loadFile(path.join(__dirname, "../dist/index.html"), { search: `?${query}` });
    }

    regionWindow.on("closed", () => {
      regionWindow = null;
    });
  },
);

ipcMain.on(
  "genie:region-selection",
  (_event, selection: { x: number; y: number; width: number; height: number } | null) => {
  if (mainWindow) {
    mainWindow.webContents.send("genie:region-selection", selection);
  }
  if (regionWindow) {
    regionWindow.close();
    regionWindow = null;
  }
  },
);

app.whenReady().then(createWindow);

app.whenReady().then(() => {
  // Allow microphone capture in dev/demo builds. Production apps should scope this more tightly.
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    if ((permission as unknown as string) === "media") {
      callback(true);
      return;
    }
    callback(false);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  void stopBackend();
});
