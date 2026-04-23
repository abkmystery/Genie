# Experimental Local Gemma 4

Genie keeps the current Demo, Local, and Custom provider system intact. This optional path adds a local Gemma 4 runner you can switch to from Settings if it works well on your machine.

## Why Gemma 4 E4B

The practical local starting point for a 16 GB RAM laptop, when you want native audio plus better local quality than E2B, is:

```text
google/gemma-4-E4B-it
```

If your machine struggles, fall back to `google/gemma-4-E2B-it`. The hosted `gemma-4-26b-a4b-it` demo path remains the reliable fallback.

## Setup

Run this once:

```powershell
npm.cmd run setup:local-gemma
```

This downloads `google/gemma-4-E4B-it` into:

```text
models/gemma-4-E4B-it
```

If Hugging Face asks for access, sign in with:

```powershell
py -3.11 -m huggingface_hub.commands.huggingface_cli login
```

Then run the local runner:

```powershell
npm.cmd run dev:local-gemma
```

For E4B or a custom folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-local-gemma.ps1 -ModelId google/gemma-4-E4B-it -ModelDir "C:\path\to\your\gemma-4-E4B-it"
```

## Use In Genie

1. Open Genie.
2. Go to Settings.
3. Select `Local Model`.
4. Set Local endpoint to:

```text
http://127.0.0.1:8766/v1
```

5. Set Local model to:

```text
google/gemma-4-E4B-it
```

6. Set Local model folder to the same folder passed to `-ModelDir`.
7. Save Local Credential. Token can stay blank.
8. Run Diagnostics.

## Notes

- This is experimental and not bundled into the default packaged app.
- If it is slow or fails, switch Settings back to Demo.
- Local mode now uses the Gemma 4 edge model itself for speech transcription through the local OpenAI-compatible runner.
- The public packaged desktop build no longer needs bundled Whisper just to support Local mode audio.
