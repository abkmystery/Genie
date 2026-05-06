# Judge Quickstart

This page gives reviewers a short path to validate Genie from source.

## Source Repository

```text
https://github.com/abkmystery/Genie
```

The public repository contains source, tests, docs, and example configs only. Real demo credentials, model weights, packaged binaries, local databases, screen captures, and logs are intentionally excluded.

## Recommended Demo Path

1. Install and launch the packaged Genie app from the submitted video/demo artifact.
2. Keep profile set to `Demo`.
3. Open Settings or Debug and confirm provider status shows live Gemma behavior for the recording path.
4. Open a website or form and ask: `What am I looking at?`
5. Attach or ingest a small file, then ask a question that requires that file.
6. Ask: `Guide me through checking high prize competitions on Kaggle`.
7. Follow the visible overlay. Genie guides only; it does not click for the user.
8. Start `Track Screen`, perform a few actions, stop recording, and verify the summary lists only actions after tracking started.

## Local Source Validation

Install dependencies:

```powershell
npm.cmd install
py -3.11 -m pip install -r services/local-api/requirements.txt
py -3.11 -m pip install -r services/demo-gateway/requirements.txt
```

Run checks:

```powershell
npm.cmd run test:backend
npm.cmd run test:desktop
npm.cmd run typecheck:desktop
npm.cmd run eval:guidance
npm.cmd run audit:package
```

## Local Gemma Path

1. Start a local OpenAI-compatible Gemma runner:

```powershell
npm.cmd run setup:local-gemma
npm.cmd run dev:local-gemma
```

2. Open Genie Settings.
3. Select `Local Model`.
4. Set endpoint to `http://127.0.0.1:8766/v1`.
5. Set model to your local Gemma 4 model name.
6. Run diagnostics.

Note: local E4B can be memory-heavy on 16 GB laptops. Hosted Demo mode is the recommended reliable judge path.

## Expected Status Labels

- `Live Gemma`: real Gemma model path is active.
- `Offline fallback`: no live provider is configured or reachable.
- `Local model not ready`: the local runner needs warmup or failed to load.
- `Endpoint error`: the configured endpoint returned an error.
