# Genie

Genie Phase 1, "Screen Companion", is a privacy-first desktop overlay assistant that stays available as a bottom-right launcher, opens a chat drawer, ingests local files, captures screen context, and answers with citations plus a trace/debug view.

This repo is intentionally split into a few replaceable parts:

- `apps/desktop`: Electron + React desktop shell and overlay UI.
- `services/local-api`: FastAPI orchestration layer that owns profiles, ingestion, retrieval, chat, screen context, and trace generation.
- `services/demo-gateway`: deployable demo-mode gateway scaffold with no embedded secrets.
- `packages/contracts`: shared TypeScript contracts and JSON schemas used by the desktop app and docs.
- `config/profiles`: public profile definitions for `demo`, `local`, and `custom`.

## Phase 1 Features

- Bottom-right Genie launcher and expandable panel.
- Text chat, mic button, optional spoken response flow.
- Current-screen capture and drag-to-select region flow.
- Guided Task mode with step cards, on-screen arrow guidance, conservative progress detection, and manual fallback controls.
- Source ingestion for `txt`, `md`, `pdf`, `docx`, `csv`, `xlsx`, `png`, `jpg`, `jpeg`, `webp`.
- Grounded answers using screen context, region context, and ingested sources.
- Structured evidence and developer-facing trace/debug details.
- Profile system with `demo`, `local`, and `custom`.
- Secure credential abstraction with an OS-keyring attempt and a loud dev fallback.
- Demo gateway scaffold with no server-side secrets committed.

## Guided Task Mode

Genie can now switch from answer mode into Guided Task mode when the user asks for help step by step, for example:

- `Guide me through this`
- `Show me where to click`
- `Walk me through this form`

When guidance starts, Genie:

1. builds a short task plan,
2. grounds the current step on the live screen,
3. renders an overlay arrow or highlight,
4. waits for confirmation or a conservative completion signal,
5. advances one step at a time.

If grounding fails, Genie falls back safely with `Re-scan`, `I can't find it`, and text-only recovery options.

## Quick Start

1. Install Node dependencies:

```powershell
npm.cmd install
```

2. Install Python dependencies:

```powershell
py -3.11 -m pip install -r services/local-api/requirements.txt
py -3.11 -m pip install -r services/demo-gateway/requirements.txt
```

3. Start the desktop app (it will start the local API automatically if needed):

```powershell
npm.cmd run dev --workspace @genie/desktop
```

If PowerShell blocks `npm.ps1`, always use `npm.cmd`.

## Commands

- Desktop dev: `npm.cmd run dev --workspace @genie/desktop`
- Desktop tests: `npm.cmd run test --workspace @genie/desktop`
- Desktop typecheck: `npm.cmd run typecheck --workspace @genie/desktop`
- Contracts build: `npm.cmd run build --workspace @genie/contracts`
- Backend tests: `py -3.11 -m pytest services/local-api/tests && py -3.11 -m pytest services/demo-gateway/tests`
- Root build: `npm.cmd run build`

## Profiles

- `demo`: uses bundled/remote demo credential file when available, otherwise offline fallback.
- `local`: user enters endpoint + optional token + model in the setup wizard or Settings.
- `custom`: user enters endpoint + optional token + model in the setup wizard or Settings; nothing requires a source edit.

Profile precedence on startup:

1. `--profile=demo|local|custom` passed to the desktop app.
2. Persisted setting from the local API storage layer.
3. Default fallback: `demo`.

## Security

- No real provider secrets are committed or bundled.
- The desktop app talks only to the local API.
- Custom credentials are stored behind a `SecureCredentialStore` abstraction.
- If OS-backed secure storage is unavailable, Genie falls back to a clearly marked development-only local file store and shows a warning in Settings.

More detail lives in [docs/security.md](docs/security.md) and [docs/release.md](docs/release.md).
