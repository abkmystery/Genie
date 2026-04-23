# Phase 1.5 Spec

This repo now includes the original grounded desktop assistant MVP plus additive work for explicit activity recording, local speech provider diagnostics, and Guided Task mode with on-screen arrow guidance.

## In Scope

- Always-available launcher and chat panel.
- Text input, mic button, TTS toggle.
- Current-screen and region-selection analysis.
- Explicit activity recording sessions with sampled frames and end-of-session summaries.
- Guided Task sessions with task planning, target grounding, overlay rendering, recovery controls, and conservative step advancement.
- Local source ingestion for supported files.
- Grounded answers with evidence and trace data.
- Demo/local/custom profile system.
- Local API orchestration boundary.
- Demo gateway scaffold.

## Out of Scope

- Autonomous actions.
- URL/database connectors.
- Wake word behavior beyond interface stubs.
- Background proactive behavior.
- Real provider secrets in the client.
- Passive historical memory without an explicit recording session.
- Autonomous clicking, typing, or computer control.

## Acceptance Notes

- All answer payloads include evidence and trace metadata.
- Activity tracking only occurs after a successful explicit start request.
- Guided Task mode must not invent a click location when grounding fails.
- Guided Task mode must not claim a step is complete unless the user confirms it or conservative completion detection is confident enough.
- Genie must not claim temporal history unless a real activity session was recorded.
- Profile switching must not require code edits.
- Demo mode must be usable with public config only.
