# Genie

Genie is a privacy-first desktop AI companion built for the Kaggle Gemma 4 Good Hackathon. It helps people understand complex websites, forms, portals, and workflows by seeing the current screen, grounding answers in local files, and guiding the next step with human-in-the-loop overlays.

The core product idea is simple: Genie does not take over the computer. It explains, cites, points, and waits for the user to stay in control.

## Competition Positioning

Genie is designed for Digital Equity, Future of Education, and Safety & Trust use cases:

- It helps users complete real digital tasks instead of chatting in isolation.
- It uses Gemma 4 for multimodal screen and document reasoning.
- It keeps private files local to the desktop orchestration layer.
- It supports an optional local Gemma 4 runner for edge-style experimentation.
- It avoids autonomous clicking, typing, form submission, file mutation, and hidden background control.

## What Genie Does

- Opens as a one-click Windows desktop companion with a draggable launcher and resizable panel.
- Answers questions about the current screen and selected screen regions.
- Ingests local files and cites evidence in answers.
- Supports `.txt`, `.md`, `.csv`, `.xlsx`, `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, and `.webp`.
- Provides Guided Task mode with step cards and visible arrow/highlight overlays.
- Records short explicit screen-tracking sessions and summarizes only actions taken after recording starts.
- Supports Demo, Local, and Custom provider profiles without source-code edits.
- Shows provider status, citations, and debug traces so judges can verify live model behavior.

## How Gemma 4 Is Implemented

Genie keeps Gemma 4 behind provider interfaces so Demo, Local, and Custom modes are swappable.

Primary code paths:

- `services/local-api/app/providers/model_provider.py`
  - `DemoModelProvider` calls Google-hosted Gemma 4 through the Gemini OpenAI-compatible `/chat/completions` API when a private demo credential is present.
  - `OpenAICompatibleHttpModelProvider` routes Local and Custom profiles to any compatible endpoint.
- `services/local-api/app/providers/model_payloads.py`
  - Builds OpenAI-style multimodal chat messages with text plus `image_url` data URLs for screen and region analysis.
- `services/local-api/app/providers/demo_credentials.py`
  - Resolves Demo credentials from a bundled private demo file, optional remote single-file config, or offline fallback.
- `services/local-gemma-runner/app.py`
  - Experimental local Gemma 4 runner exposing `/v1/chat/completions`, `/ready`, `/warmup`, and diagnostics.
- `services/local-api/app/domain/answer_service.py`
  - Orchestrates retrieval, screen context, web search opt-in behavior, guidance intent, activity summaries, provider calls, citations, and traces.
- `services/local-api/app/domain/guidance_orchestrator.py`
  - Coordinates task planning, screen grounding, progress checks, and safe fallback behavior for Guided Task mode.

More detail: [docs/gemma-4-implementation.md](docs/gemma-4-implementation.md).

## Architecture

```text
apps/desktop
  Electron + React UI, launcher, chat panel, settings, overlays

services/local-api
  FastAPI local orchestration boundary used by the desktop app

services/demo-gateway
  Optional private-hosting scaffold for a server-side Gemma gateway

services/local-gemma-runner
  Experimental local Gemma 4 OpenAI-compatible runner

packages/contracts
  Shared TypeScript contracts and JSON schemas

config/profiles
  Public profile metadata for demo, local, and custom modes
```

The desktop UI talks only to `services/local-api`. Provider keys and endpoint routing are owned by the local API or private gateway paths, not by React components.

## Quick Start

Install dependencies:

```powershell
npm.cmd install
py -3.11 -m pip install -r services/local-api/requirements.txt
py -3.11 -m pip install -r services/demo-gateway/requirements.txt
```

Run desktop development mode:

```powershell
npm.cmd run dev:desktop
```

The Electron app starts the local API automatically in normal desktop flows. If PowerShell blocks `npm.ps1`, use `npm.cmd`.

## Demo Mode

Public source contains no real demo credential. Demo mode resolves in this order:

1. `resources/private/demo-provider.json` if present in a private local build.
2. Optional remote single-file config if configured.
3. Offline/mock fallback.

The public repository includes only:

- `resources/private/demo-provider.example.json`
- documentation for private demo builds
- audit scripts that fail public packages containing unsafe artifacts

For a competition recording, a private local `package:demo` build can include `resources/private/demo-provider.json`. Do not commit that file.

## Local Gemma 4

Local mode targets an OpenAI-compatible endpoint such as:

```text
http://127.0.0.1:8766/v1
```

Setup:

```powershell
npm.cmd run setup:local-gemma
npm.cmd run dev:local-gemma
```

Notes:

- `google/gemma-4-E4B-it` is the local quality target.
- 16 GB RAM laptops may need a smaller or quantized model.
- Hosted Demo mode is the recommended reliable judge path.

Details: [docs/local-gemma.md](docs/local-gemma.md).

## Validation Commands

```powershell
npm.cmd run test:backend
npm.cmd run test:desktop
npm.cmd run typecheck:desktop
npm.cmd run eval:guidance
npm.cmd run audit:package
```

Packaging:

```powershell
npm.cmd run package:public
npm.cmd run package:demo
```

Use `package:public` for public artifacts. Use `package:demo` only for private demo builds where a local ignored demo credential file is intentionally bundled.

## Public Repository Safety

This repo is prepared to be public:

- Real provider keys are not tracked.
- The previous local scratch Word document was removed from git history before publication.
- `resources/private/demo-provider.json` and `resources/private/demo-provider.json.txt` are ignored.
- Model weights, release artifacts, local databases, captures, reports, logs, caches, and private env files are ignored.
- Public builds must pass `npm.cmd run audit:package`.

See [docs/security.md](docs/security.md) and [docs/public-repository-checklist.md](docs/public-repository-checklist.md).

## Submission Resources

- [SUBMISSION.md](SUBMISSION.md)
- [docs/judge-quickstart.md](docs/judge-quickstart.md)
- [docs/demo-script.md](docs/demo-script.md)
- [docs/validation-report.md](docs/validation-report.md)
- [docs/gemma-4-implementation.md](docs/gemma-4-implementation.md)

## What Genie Does Not Do

- No autonomous clicking or typing.
- No form submission on behalf of the user.
- No shell/file/email mutation tools.
- No hidden passive monitoring.
- No committed provider credentials.

That boundary is intentional: Genie is a trustworthy companion that guides the user, not an unsafe remote-control agent.
