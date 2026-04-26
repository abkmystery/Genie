# Genie Submission Brief

Genie is a privacy-first digital access companion for people who need help understanding complex websites, forms, portals, and workflows. It uses Gemma 4 for screen reasoning, private-file grounding, and human-in-the-loop guidance without taking autonomous control of the computer.

## Competition Story

- Category fit: Digital Equity, Future of Education, Safety and Trust.
- Core promise: Genie helps users complete digital tasks safely and independently by seeing the screen, explaining what matters, citing private files, and pointing to the next step.
- Safety boundary: Genie guides with overlays and instructions only. It does not click, type, submit forms, run shell commands, send emails, mutate files, or bypass user control.

## Judge-Visible Flows

1. Ask about the current screen and receive a concise Gemma-grounded answer.
2. Attach or ingest a private file and receive citations from local sources.
3. Ask "Guide me through..." and see on-screen arrows with conservative step advancement.
4. Switch between Demo hosted Gemma and Local Gemma endpoint modes from Settings.

## Gemma 4 Usage

- Demo path: desktop -> local-api -> demo-gateway -> Google Gemini OpenAI-compatible Gemma 4 endpoint.
- Local path: desktop -> local-api -> local OpenAI-compatible Gemma runner.
- Gemma handles text + image reasoning for screen understanding, region understanding, guidance grounding, and activity summaries.
- Audio remains explicit: browser/local STT transcribes speech first unless a selected local endpoint truly supports audio-native messages.

## Reliability Gates

- `npm.cmd run test:backend`
- `npm.cmd run test:desktop`
- `npm.cmd run typecheck:desktop`
- `npm.cmd run eval:guidance`
- `npm.cmd run audit:package`

Final demo recordings should show "Live Gemma" in Settings or Debug. Fallback/mock responses are acceptable only when intentionally demonstrating offline resilience.
