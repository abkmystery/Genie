# Architecture

Genie is a desktop-first, local-orchestration architecture built to keep the UI simple, keep secrets out of the client, and leave room for later phases.

## Topology

1. `apps/desktop` renders the launcher, panel, source manager, settings, and debug views.
2. `services/local-api` is the only backend the desktop app talks to.
3. `services/local-api` resolves the active profile and then routes model/STT/TTS work to:
   - the demo gateway,
   - a local model endpoint,
   - or a custom endpoint.
4. `services/demo-gateway` is an optional hosted service used only for demo mode.

## Domain Boundaries

- `ProfileManager`: profile resolution, active-profile persistence, config lookup, and credentials lookup.
- `SourceIngestionService`: validates source types, parses content, chunks it, and stores metadata.
- `RetrievalService`: keyword-first retrieval for Phase 1 with structured evidence.
- `ScreenContextService`: captures the current screen and optionally derives OCR/summary context.
- `RegionContextService`: crops a region from the latest screen capture and derives context.
- `ActivityRecordingService`: owns explicit time-bounded activity recording sessions and the stop/start API surface.
- `ActivitySessionManager`: manages the active recording thread, session state, and last completed result.
- `TimelineAssembler`: condenses sampled frames and desktop events into a bounded timeline.
- `ActivitySummarizer`: uses Gemma 4 26B plus timeline artifacts to produce the final step-by-step recording summary.
- `GuidedTaskSessionManager`: holds the active guided-task session, step state, and overlay-ready status.
- `TaskPlanner`: turns a user goal plus current screen context into a compact plan.
- `TargetGrounder`: finds the best visible on-screen target candidate and returns a bounded overlay target.
- `StepProgressDetector`: evaluates whether the current step is complete and defaults to conservative confirmation behavior.
- `GuidanceOrchestrator`: coordinates planning, grounding, re-scan, recovery, and step advancement.
- `AnswerService`: builds grounded prompts, routes to a `ModelProvider`, formats evidence, and records traces.
- `TraceService`: emits per-request events and summaries shown in the debug panel.

## Storage

- SQLite stores settings, source metadata, chunks, and trace summaries.
- Session chat memory is process-local and reset when the local API restarts.
- Activity session artifacts are stored locally under the local API data directory.
- Credentials live behind `SecureCredentialStore`.

## Desktop Overlay Model

- The Electron window starts in a compact bottom-right launcher size.
- Opening Genie expands the same floating window into a chat drawer/panel.
- Region selection uses an overlay-style selection experience backed by a captured screen image and a typed region contract.
- Guided Task mode uses a second transparent Electron overlay window that is click-through and only renders arrows, highlights, and step labels.

## Graceful Degradation

- Screen capture falls back to a generated simulated image if native capture is unavailable.
- OCR falls back to metadata-only extraction if OCR tooling is unavailable.
- STT uses a local provider chain with browser/UI fallback when no offline Python package is installed.
- TTS uses a local provider chain that prefers `pyttsx3` and falls back to Windows `System.Speech` when available.
- Secure storage falls back to a clearly labeled dev-only local file store if OS keyring support is missing.
