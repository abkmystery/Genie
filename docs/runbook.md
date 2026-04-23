# Runbook

## Environment Decisions

- Node: use `npm.cmd` on this Windows PowerShell environment because `npm.ps1` is blocked by execution policy.
- Python: use `py -3.11`.
- Desktop stack: Electron + React + TypeScript + Vite.
- Backend stack: FastAPI + SQLite + Pydantic.

## Happy Paths

### Demo Profile

In development, you can run the desktop app and it will start the local API automatically if it is not already running.

1. Start the desktop app:

```powershell
npm.cmd run dev --workspace @genie/desktop
```

2. First run shows the setup wizard. Choose **Demo**.

3. Use the panel to add files, analyze screen, or ask questions.

### Demo Mode With Real Gemma 4 (Bundled Demo Credential File)

For a one-click demo build, create a local (gitignored) file:

- `resources/private/demo-provider.json`

Then package with:

```powershell
npm.cmd run package:demo
```

Genie will use the bundled/remote/offline fallback chain automatically without asking users for a key.

### Local Profile

1. Start desktop and choose **Local** in the wizard.
2. Enter endpoint + optional token + model name.
3. You can change these later in Settings.

### Custom Profile

1. Start desktop and choose **Custom** in the wizard.
2. Enter endpoint + optional token + model name.
3. Genie persists the chosen profile and credentials without editing source code.

## Logs

- Packaged builds write logs to the app logs directory and provide an "Open Logs Folder" action in Settings.
- Traces are also available through the debug panel in the desktop app.
