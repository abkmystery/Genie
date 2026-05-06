# Genie Submission Brief

Genie is a privacy-first digital access companion powered by Gemma 4. It helps users understand complex screens, use private documents as context, and move through digital workflows with visible guidance while keeping the user in control.

## Public Source Of Truth

Repository:

```text
https://github.com/abkmystery/Genie
```

The repository is intended to be public for judging. It contains the desktop app, local orchestration API, demo gateway scaffold, local Gemma runner, contracts, tests, validation scripts, and documentation. It does not contain real provider credentials or model weights.

## Gemma 4 Usage

Genie uses Gemma 4 through two explicit paths:

1. **Demo path**
   - Desktop app calls `services/local-api`.
   - `services/local-api` resolves Demo provider config.
   - In a private demo build, the local API calls Google-hosted Gemma 4 via the Gemini OpenAI-compatible `/chat/completions` API.
   - Public source includes only the example credential template and offline fallback.

2. **Local path**
   - Desktop app calls `services/local-api`.
   - Local profile points to an OpenAI-compatible endpoint such as `http://127.0.0.1:8766/v1`.
   - `services/local-gemma-runner` exposes an experimental Gemma 4 local endpoint using Hugging Face `AutoModelForMultimodalLM`.

Gemma 4 is used for:

- Current-screen understanding.
- Selected-region understanding.
- File-grounded answers with citations.
- Guided Task planning and target grounding.
- Activity recording summaries from sampled screen timelines.

## Judge-Visible Flows

1. Ask about the current screen and receive a concise Gemma-grounded answer.
2. Attach or ingest a local file and receive citations from private sources.
3. Ask `Guide me through...` and see on-screen guidance overlays.
4. Start `Track Screen`, perform actions, and receive an action-only step summary.
5. Open Settings or Debug and verify provider status such as `Live Gemma`, `Offline fallback`, or `Local model not ready`.

## Safety Boundary

Genie is human-in-the-loop guidance, not autonomous computer use. It does not click, type, submit forms, mutate files, run shell commands, send emails, or bypass user control.


