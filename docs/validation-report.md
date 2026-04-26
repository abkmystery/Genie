# Validation Report

This document tracks the competition reliability gates for Genie. Keep it updated before creating a submission build.

## Automated Gates

- Backend tests: `npm.cmd run test:backend`
- Desktop tests: `npm.cmd run test:desktop`
- Desktop typecheck: `npm.cmd run typecheck:desktop`
- Guidance eval: `npm.cmd run eval:guidance`
- Package audit: `npm.cmd run audit:package`

## Provider Status Gates

- Demo profile must show `Live Gemma` for the final recording.
- If Demo shows `Offline fallback`, the demo gateway is not using a live key or endpoint.
- Local profile must show ready diagnostics before it is used in a judged flow.

## Guidance Eval

`npm.cmd run eval:guidance` writes:

- `reports/guidance-eval.json`
- `reports/guidance-eval.md`

The eval is intentionally synthetic and fast. It checks target ranking and center-distance for common UI targets such as browser address bars, Kaggle filters, Excel chart controls, forms, settings, and generic buttons.

## Package Safety

Public packages must not include:

- real `demo-provider.json`
- `.env` files
- local SQLite databases
- screen captures
- model weights
- Python caches

Demo packages may include `resources/private/demo-provider.json` only when intentionally building a private demo artifact.
