# Validation Report

This document tracks the reliability and repository-safety gates for Genie.

## Automated Gates

Run before creating a submission build or making the repository public:

```powershell
npm.cmd run test:backend
npm.cmd run test:desktop
npm.cmd run typecheck:desktop
npm.cmd run eval:guidance
npm.cmd run audit:package
```

Latest local verification on May 5, 2026:

- `npm.cmd run test:backend` passed: 53 local-api tests, 2 demo-gateway tests, 8 local-gemma-runner tests.
- `npm.cmd run test:desktop` passed: 5 Vitest tests.
- `npm.cmd run typecheck:desktop` passed.
- `npm.cmd run eval:guidance` passed: 20/20 guidance eval targets.

## Current Coverage Areas

- Backend orchestration and smoke tests.
- Source parsers for text, markdown, PDF, DOCX, CSV, XLSX, and images.
- Demo credential resolver behavior.
- OpenAI-compatible provider payload/output handling.
- Speech provider fallback behavior.
- Guided task planning, grounding, progress, and failure modes.
- Local Gemma runner payload conversion and memory preflight.
- Desktop launcher and overlay smoke tests.

## Guidance Eval

`npm.cmd run eval:guidance` writes:

- `reports/guidance-eval.json`
- `reports/guidance-eval.md`

The eval is intentionally synthetic and fast. It checks target ranking and center-distance for common UI targets such as browser address bars, Kaggle filters, Excel chart controls, forms, settings, and generic buttons.

## Provider Status Gates

- Demo profile should show live Gemma behavior in the final recording.
- If Demo shows `Offline fallback`, the private demo credential or hosted endpoint is not available.
- Local profile must show ready diagnostics before being used in a judged flow.
- Custom profile should show endpoint errors honestly instead of silently pretending to be live.

## Public Repository Safety

Before publication:

- The old local scratch Word document was removed from git history.
- History checks for any real provider-key fragment should return no commits.
- `resources/private/demo-provider.json` is ignored and not tracked.
- Public source contains no model weights, release artifacts, local databases, captures, logs, or real env files.

## Package Safety

Public packages must not include:

- real `demo-provider.json`
- `.env` files
- local SQLite databases
- screen captures
- model weights
- Python caches

Private demo packages may include `resources/private/demo-provider.json` only when intentionally building a local demo artifact. That artifact is not the public source repository.
