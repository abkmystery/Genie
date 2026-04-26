# Troubleshooting

## `npm` is blocked in PowerShell

Use `npm.cmd` instead of `npm`.

## Screen capture is simulated

If native capture is unavailable, Genie generates a labeled mock screen image and continues the flow. The debug panel will show the provider that handled capture.

## Secure storage warning

If Genie cannot use OS-backed secure storage, it falls back to a development-only local file store. This is expected in some environments and is intentionally surfaced in Settings.

## OCR returns limited text

OCR is optional in Phase 1. When no OCR engine is installed, Genie uses metadata-only image context rather than failing the request.

## Mic button fails

Genie now prefers browser-native speech recognition in the desktop shell. If that is unavailable, it falls back to the backend `/audio/transcribe` provider chain.

- Ensure Electron is allowed to access the microphone.
- Check Settings diagnostics to see whether an offline STT package was detected.
- Demo and non-audio models use the packaged offline STT helper, then send transcript text to Gemma.
- Local/Custom endpoints using audio-native models such as Gemma 4 E2B/E4B are tried first, then Genie falls back to offline STT if the endpoint rejects audio.
- If no local STT package is installed, browser speech recognition may still work in the desktop shell.

## Activity recording does not start

- Check that `Enable explicit activity recording sessions` is enabled in Settings.
- Verify the local backend is healthy and that `Run Diagnostics` shows `activity_capture.enabled = true`.
- Genie will only claim recording is active after `/activity/start` succeeds.

## Genie says it has no history

That is expected unless an explicit activity recording session was started earlier. Genie does not maintain magical passive memory of the last minute of desktop activity.

## Guided Task mode cannot find the next click target

- Use `Re-scan` to capture the current page state again.
- Use `I can't find it` and then circle the relevant area so Genie can re-ground inside that region.
- Make sure the relevant button, field, or label is actually visible on the current screen.
- Genie merges OCR words into line/phrase candidates for better target boxes, but if OCR is weak or the control is icon-only, it may fall back to text-only instructions instead of guessing.

## Settings shows Offline fallback or Endpoint error

- `Offline fallback` means Genie is intentionally using the bundled mock path because no live Gemma provider was reachable.
- `Endpoint error` means the selected HTTP provider responded with an error; open Debug to see the sanitized error.
- `Local model not ready` means the local runner is not warmed up or failed to load the model. Start `npm.cmd run dev:local-gemma`, call `/warmup`, then re-run diagnostics.
- Final competition recordings should show `Live Gemma` unless you are explicitly demonstrating offline fallback.

## Package audit fails

Run `npm.cmd run package:public` for public sharing. It quarantines `resources/private` during packaging and then runs the audit. If `npm.cmd run audit:package` fails on an old `win-unpacked` folder, rebuild the public package so stale private resources are removed.
