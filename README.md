# Genie

Genie is a privacy-first desktop AI companion built to feel genuinely useful in the real world, not just impressive in a demo. It stays available as an on-screen companion, understands what the user is looking at, grounds answers in local files and live screen context, and can guide a user step by step with on-screen overlays.

This repository is being shaped as a strong submission for the Kaggle Gemma 4 Good Hackathon. The product direction intentionally matches the themes highlighted by Google and Kaggle around local-first AI, multimodal utility, privacy, trust, and meaningful real-world impact. Official context:

- [Gemma 4: Byte for byte, the most capable open models](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- [The Gemma 4 Good Hackathon on Kaggle](https://www.kaggle.com/competitions/gemma-4-good-hackathon/overview)

This repo is intentionally split into a few replaceable parts:

- `apps/desktop`: Electron + React desktop shell and overlay UI.
- `services/local-api`: FastAPI orchestration layer that owns profiles, ingestion, retrieval, chat, screen context, and trace generation.
- `services/demo-gateway`: deployable demo-mode gateway scaffold with no embedded secrets.
- `packages/contracts`: shared TypeScript contracts and JSON schemas used by the desktop app and docs.
- `config/profiles`: public profile definitions for `demo`, `local`, and `custom`.

## Why Genie Is Competitive

Genie is designed to score well on the things that usually separate winning hackathon submissions from generic assistants:

- Real utility: it helps a user understand the screen they are already on, not a disconnected toy workflow.
- Strong Gemma 4 fit: demo mode uses hosted Gemma 4, and local mode supports edge-friendly Gemma 4 E4B/E2B through an OpenAI-compatible runner.
- Privacy-first UX: local API boundary, local file grounding, and local model support reduce unnecessary data exposure.
- Multimodal grounding: answers and guidance use screenshots, selected regions, OCR, attachments, and structured evidence.
- Polished user experience: launcher, drawer UI, citations, debug panel, settings, activity tracking, and guided overlays.
- Honest behavior: Genie does not pretend it tracked history or found a target when the evidence is weak.

## Core Features

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

## Gemma 4 Alignment

Genie is intentionally aligned with the strengths Google called out for Gemma 4:

- Multimodal reasoning over screen images and documents.
- Native edge-model audio support for E2B/E4B in Local mode.
- Local-first deployment paths for privacy-sensitive or low-connectivity environments.
- Agentic-style step guidance without unsafe autonomous control.

Current recommended profiles:

- `demo`: hosted Gemma 4 for the smoothest public demo path
- `local`: Gemma 4 E4B through the local runner path for edge-style local testing, with E2B as the lower-memory fallback
- `custom`: any compatible endpoint for experimentation or later production routing

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

## What Makes Genie Useful

Genie is not just “chat with screenshots.” It combines several things users actually need in one companion:

- Ask what a page means or what action is being requested.
- Attach private files and get grounded answers with citations.
- Select a region to focus the model on exactly the right area.
- Track a short window of activity and summarize the steps.
- Ask Genie to guide the next click with an on-screen arrow instead of only returning text.

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
- Local Gemma 4 setup: `npm.cmd run setup:local-gemma`
- Local Gemma 4 runner: `npm.cmd run dev:local-gemma`
- Guidance eval: `npm.cmd run eval:guidance`
- Package audit: `npm.cmd run audit:package`
- Public package: `npm.cmd run package:public`
- Private demo package: `npm.cmd run package:demo`
- Root build: `npm.cmd run build`

## Profiles

- `demo`: uses bundled/remote demo credential file when available, otherwise offline fallback.
- `local`: user enters endpoint + optional token + model in the setup wizard or Settings. The recommended endpoint is `http://127.0.0.1:8766/v1`; the recommended local model is `google/gemma-4-E4B-it`.
- `custom`: user enters endpoint + optional token + model in the setup wizard or Settings; nothing requires a source edit.

For local Gemma 4, see [docs/local-gemma.md](docs/local-gemma.md). The runner verifies `AutoModelForMultimodalLM` before startup because older Transformers installs can expose `/v1/models` but still fail on audio/image chat requests.

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

## Submission Positioning

If you are packaging Genie as a Gemma 4 Good submission, the strongest story is:

- Genie helps people complete real digital tasks with less confusion and less risk.
- It works in privacy-sensitive settings because the desktop app talks to a local orchestration layer and can run with local models.
- It uses Gemma 4 where Gemma is strongest: multimodal reasoning, grounded help, local/edge deployment options, and practical human-in-the-loop guidance.
- It focuses on trust and usability instead of pretending to be fully autonomous.
