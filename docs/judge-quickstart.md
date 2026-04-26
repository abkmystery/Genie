# Judge Quickstart

## Recommended Demo Path

1. Install and launch the packaged Genie app.
2. Keep profile set to Demo.
3. Confirm Settings shows `Live Gemma`.
4. Open a website or form and ask: `What am I looking at?`
5. Attach a file in chat or add one under Sources, then ask a question that requires the file.
6. Ask: `Guide me through checking high prize competitions on Kaggle`.
7. Use the visible overlay and task card. Genie will guide only; it will not click for you.

## Local Gemma Path

1. Start a local OpenAI-compatible Gemma runner on `http://127.0.0.1:8766/v1`.
2. Open Settings -> Local.
3. Set endpoint to `http://127.0.0.1:8766/v1`.
4. Set model to your local Gemma model name.
5. Run diagnostics and confirm the local endpoint is ready.

## Expected Status Labels

- `Live Gemma`: real Gemma model path is active.
- `Offline fallback`: no live provider is configured or reachable.
- `Local model not ready`: the local runner needs warmup or failed to load.
- `Endpoint error`: configured endpoint returned an error.
