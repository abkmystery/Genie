import { app } from "electron";
import fs from "node:fs";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";

const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

type BackendState = "stopped" | "starting" | "ready" | "failed";

let backendProcess: ChildProcess | null = null;
let backendState: BackendState = "stopped";
let backendLastError: string | null = null;
let ensurePromise: Promise<void> | null = null;

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true });
}

function nowIso() {
  return new Date().toISOString();
}

function writeLog(logFile: string, line: string) {
  try {
    fs.appendFileSync(logFile, `[${nowIso()}] ${line}\n`, { encoding: "utf-8" });
  } catch {
    // ignore
  }
}

async function healthOk(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`, { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

function resolveRepoRoot(): string {
  // In dev, __dirname is apps/desktop/dist-electron; go up to repo root.
  return path.resolve(__dirname, "..", "..", "..");
}

function resolveBackendCommand(): { cmd: string; args: string[]; cwd?: string } {
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, "backend", "genie-local-api.exe");
    return { cmd: exe, args: [] };
  }

  const repoRoot = resolveRepoRoot();
  // Use the Windows Python launcher when available; it's common on dev machines.
  const cmd = process.platform === "win32" ? "py" : "python3";
  const args =
    process.platform === "win32"
      ? ["-3.11", "-m", "uvicorn", "app.main:app", "--app-dir", path.join(repoRoot, "services", "local-api"), "--host", "127.0.0.1", "--port", "8765"]
      : ["-m", "uvicorn", "app.main:app", "--app-dir", path.join(repoRoot, "services", "local-api"), "--host", "127.0.0.1", "--port", "8765"];
  return { cmd, args, cwd: repoRoot };
}

export function getBackendBaseUrl() {
  return DEFAULT_BASE_URL;
}

export function getLogsDir() {
  const dir = path.join(app.getPath("userData"), "logs");
  ensureDir(dir);
  return dir;
}

export function getBackendStatus() {
  return { state: backendState, last_error: backendLastError, base_url: DEFAULT_BASE_URL };
}

export async function ensureBackendReady(): Promise<void> {
  if (backendState === "ready") return;
  if (ensurePromise) return ensurePromise;

  ensurePromise = (async () => {
    const baseUrl = DEFAULT_BASE_URL;
    const logsDir = getLogsDir();
    const logFile = path.join(logsDir, "backend-launch.log");

    backendLastError = null;
    backendState = "starting";
    writeLog(logFile, "backend health check started");

    if (await healthOk(baseUrl)) {
      backendState = "ready";
      writeLog(logFile, "backend already running");
      return;
    }

    const { cmd, args, cwd } = resolveBackendCommand();
    writeLog(logFile, `backend spawn attempted cmd=${cmd}`);

    const env = {
      ...process.env,
      GENIE_DATA_DIR: path.join(app.getPath("userData"), "data"),
      GENIE_DB_PATH: path.join(app.getPath("userData"), "data", "genie.db"),
      GENIE_LOG_DIR: logsDir,
      GENIE_RESOURCES_DIR: app.isPackaged ? process.resourcesPath : path.join(resolveRepoRoot(), "resources"),
      GENIE_PROFILE_CONFIG_DIR: app.isPackaged
        ? path.join(process.resourcesPath, "config", "profiles")
        : path.join(resolveRepoRoot(), "config", "profiles"),
      // Never require demo secrets via env vars in the desktop client.
      GENIE_DEMO_GATEWAY_URL: "",
    };

    try {
      backendProcess = spawn(cmd, args, {
        cwd,
        env,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (cause) {
      backendState = "failed";
      backendLastError = cause instanceof Error ? cause.message : String(cause);
      writeLog(logFile, `backend spawn failed: ${backendLastError}`);
      throw cause;
    }

    backendProcess.stdout?.on("data", (chunk) => writeLog(logFile, `stdout: ${String(chunk).trimEnd()}`));
    backendProcess.stderr?.on("data", (chunk) => writeLog(logFile, `stderr: ${String(chunk).trimEnd()}`));
    backendProcess.on("exit", (code) => {
      writeLog(logFile, `backend exited code=${code ?? "unknown"}`);
      backendProcess = null;
      if (backendState !== "ready") {
        backendState = "failed";
      } else {
        backendState = "stopped";
      }
    });

    const startDeadlineMs = Date.now() + 25_000;
    while (Date.now() < startDeadlineMs) {
      if (await healthOk(baseUrl)) {
        backendState = "ready";
        writeLog(logFile, "backend ready");
        return;
      }
      await new Promise((r) => setTimeout(r, 250));
    }

    backendState = "failed";
    backendLastError = "Backend did not become ready in time.";
    writeLog(logFile, `backend failed: ${backendLastError}`);
    throw new Error(backendLastError);
  })().finally(() => {
    ensurePromise = null;
  });

  return ensurePromise;
}

export async function stopBackend() {
  const logsDir = getLogsDir();
  const logFile = path.join(logsDir, "backend-launch.log");
  if (!backendProcess) return;

  writeLog(logFile, "backend stop requested");
  try {
    backendProcess.kill();
  } catch {
    // ignore
  }
  backendProcess = null;
  backendState = "stopped";
}
