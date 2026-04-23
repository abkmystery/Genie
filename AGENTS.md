# AGENTS.md

This file is for future Codex or human contributors working in the Genie repo. Phase 1 is intentionally small, typed, and modular. Preserve those boundaries when extending the product.

## Repo Layout

- `apps/desktop`
  - Electron shell, renderer UI, preload bridge, bottom-right launcher behavior, region-selection window hooks, and local API client.
- `services/local-api`
  - FastAPI orchestration service for profiles, settings, ingestion, retrieval, screen/region context, chat, traces, and health.
- `services/demo-gateway`
  - Optional deployable demo-mode proxy/gateway scaffold. No real provider credentials belong here in git.
- `packages/contracts`
  - Shared TypeScript contracts and JSON schemas. Treat these as the public interface between UI and services.
- `config/profiles`
  - Public non-secret profile config files. Safe to ship.
- `docs`
  - Product spec, architecture, security, runbook, troubleshooting, roadmap, and release notes.

## Install / Run / Test

- Node install: `npm.cmd install`
- Python install: `py -3.11 -m pip install -r services/local-api/requirements.txt`
- Demo gateway install: `py -3.11 -m pip install -r services/demo-gateway/requirements.txt`
- Local API dev: `py -3.11 -m uvicorn app.main:app --app-dir services/local-api --reload --port 8765`
- Demo gateway dev: `py -3.11 -m uvicorn app.main:app --app-dir services/demo-gateway --reload --port 8788`
- Desktop dev: `npm.cmd run dev --workspace @genie/desktop -- --profile=demo`
- Desktop tests: `npm.cmd run test --workspace @genie/desktop`
- Backend tests: `py -3.11 -m pytest services/local-api/tests && py -3.11 -m pytest services/demo-gateway/tests`
- Build desktop: `npm.cmd run build --workspace @genie/desktop`

If PowerShell blocks `npm.ps1`, use `npm.cmd`.

## Coding Conventions

- Prefer boring architecture over cleverness.
- Keep modules small; extract helpers before a file becomes a giant.
- Business logic belongs in service/domain modules, not React components.
- Use typed DTOs for all API boundaries.
- Comments should explain intent where logic is non-obvious, not narrate the obvious.
- New Phase 1 behavior should flow through interfaces before touching providers directly.

## Architectural Boundaries

- The desktop app talks only to `services/local-api`.
- The local API owns profile resolution, secure credential usage, source ingestion, retrieval, and provider routing.
- Demo-mode calls go through `services/demo-gateway`.
- UI components never call arbitrary provider endpoints directly.
- Contracts in `packages/contracts` are the compatibility layer. Backward-compatible changes only unless you also update all consumers and docs together.

## Profiles

Phase 1 ships with three standard profiles:

- `demo`
- `local`
- `custom`

Startup resolution order:

1. Desktop CLI flag `--profile=...`
2. Persisted setting in local API storage
3. Fallback `demo`

Public profile files may include metadata, capabilities, URLs, model names, and timeout settings. They must never contain real secrets.

## Provider Wiring

Mandatory provider interfaces in Phase 1:

- `ModelProvider`
- `ScreenCaptureProvider`
- `RegionSelectionProvider`
- `SpeechToTextProvider`
- `TextToSpeechProvider`
- `OCRProvider`
- `SourceParser`
- `SourceRepository`
- `RetrievalEngine`
- `TraceLogger`
- `ProfileConfigLoader`
- `SecureCredentialStore`
- `WakeWordProvider`

When adding a provider:

1. Add or extend the interface in the provider layer.
2. Keep domain services unaware of vendor-specific details.
3. Register the implementation in the service wiring module.
4. Add tests for both the happy path and graceful fallback.

## Secure Credential Storage

- Prefer OS-backed secure storage when available.
- The Python local API attempts `keyring` first.
- If secure storage is unavailable, Genie uses a development-only local file store under the data directory and surfaces a warning in Settings and docs.
- Never add real API keys to:
  - source files
  - `.env.example`
  - `config/profiles/*.json`
  - desktop bundle assets
  - test fixtures

## Phase 1 Includes

- Launcher, panel, text chat, source ingestion, screen/region context, citations, traces, profile settings, mock audio flows, demo gateway scaffold, and release path docs.

## Phase 1 Excludes

- Autonomous computer control.
- Browser automation.
- Email/shell/file mutation tools.
- Database connectors.
- URL crawling.
- Wake word activation beyond a stub interface.
- Policy/approval workflows.

## Done Means

Phase 1 is done when:

- The desktop app runs locally with documented commands.
- Sources can be ingested and cited.
- Screen and region context can be attached and answered against.
- Profile switching works without code edits.
- No real secrets are present client-side.
- Tests cover the core services and main smoke flows.
- The release path is documented without leaking secrets.

## Future Phase Guidance

- Add new capabilities behind small interfaces and new service modules.
- Do not overload Phase 1 contracts with action-tool semantics; introduce separate contracts for approvals/tools later.
- Preserve `local-api` as the orchestration boundary even when adding URL/database/action features.
- Prefer additive contract evolution and feature flags over breaking rewrites.
