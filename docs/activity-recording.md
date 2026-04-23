# Activity Recording

Genie activity recording is explicit session-based tracking. It is not passive memory and it is not always-on surveillance.

## How it works

1. The user explicitly starts a recording session.
2. Genie shows a visible recording indicator in the chat panel.
3. The local API samples desktop frames over time.
4. Genie collects lightweight desktop context such as the active window title when available.
5. Genie assembles a bounded timeline from sampled frames and events.
6. Gemma 4 26B summarizes the recorded session into an ordered step-by-step result.

## Frame Sampling

- Recording uses sampled frames instead of raw continuous video streaming.
- The default sampling rate is 1 frame per second.
- Representative frames are deduplicated before summarization so the model sees a compact timeline rather than every raw frame.

## Privacy

- Recording only starts after an explicit user request.
- A visible recording state is shown while the session is active.
- Artifacts are stored locally in the local API data directory.
- Genie avoids logging obvious sensitive text markers such as `password`, `token`, `secret`, and `api key` when building timeline summaries.
- Raw credentials from Settings are never surfaced in diagnostics.

## Known Limitations

- Window/app metadata depends on what the local operating system can expose safely.
- OCR and desktop event fidelity may be limited in restricted environments.
- Genie cannot summarize activity that was never recorded.
- Local offline STT package support is provider-based and may require installing a supported package in a given environment.
