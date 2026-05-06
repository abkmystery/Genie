# Gemma 4 Implementation

This document maps the judged Gemma 4 behavior to concrete source files. It exists so reviewers can validate that Genie is not a generic chatbot wrapper.

## Provider Boundary

All model access goes through `ModelProvider` implementations. UI components do not call Gemma or arbitrary provider endpoints directly.

Key files:

- `services/local-api/app/providers/interfaces.py`
- `services/local-api/app/providers/model_provider.py`
- `services/local-api/app/providers/model_payloads.py`
- `services/local-api/app/domain/profile_service.py`

## Demo Gemma Path

Private demo build flow:

```text
Electron desktop
  -> services/local-api
  -> DemoModelProvider
  -> Gemini OpenAI-compatible /chat/completions
  -> Gemma 4 model
```

Important implementation details:

- `config/profiles/demo.json` is public metadata only.
- `resources/private/demo-provider.example.json` documents the private file shape.
- `resources/private/demo-provider.json` is ignored and must not be committed.
- `DemoCredentialResolver` can resolve a bundled private file, optional remote single-file config, or offline fallback.
- `DemoModelProvider` turns the resolved provider config into a Gemma 4 call without exposing raw keys in UI or logs.

## Local Gemma Path

Local flow:

```text
Electron desktop
  -> services/local-api
  -> OpenAICompatibleHttpModelProvider
  -> http://127.0.0.1:8766/v1/chat/completions
  -> services/local-gemma-runner
  -> Hugging Face Gemma 4 model
```

The local runner provides:

- `GET /health`
- `GET /ready`
- `POST /warmup`
- `GET /diagnostics`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /smoke`

The runner uses:

- `AutoProcessor`
- `AutoModelForMultimodalLM`
- `processor.apply_chat_template(...)`
- OpenAI-compatible message parts for text, images, and audio where the selected local model supports them

The runner includes a memory preflight so a 16 GB machine gets an actionable `local_not_ready` style error instead of an opaque generation failure.

## Multimodal Payloads

`services/local-api/app/providers/model_payloads.py` builds the Gemma request payload.

For screen and region understanding, Genie attaches base64 data URLs as OpenAI-style image parts:

```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/png;base64,..."
  }
}
```

The same payload includes grounded text context:

- screen summary
- region summary
- source evidence snippets
- user request

## RAG And Citations

Source ingestion and retrieval are local:

- `services/local-api/app/providers/source_parsers.py`
- `services/local-api/app/domain/source_ingestion_service.py`
- `services/local-api/app/domain/retrieval_service.py`
- `services/local-api/app/domain/citation_service.py`

Supported source types:

- `.txt`
- `.md`
- `.csv`
- `.xlsx`
- `.pdf`
- `.docx`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

Gemma receives only the relevant evidence snippets and screen/region context selected by the local API.

## Guided Task Mode

Guidance is implemented as a safe planning-and-grounding loop:

- `TaskPlanner` converts the user goal into steps.
- `TargetGrounder` finds visible screen targets.
- `StepProgressDetector` conservatively checks whether the current step appears complete.
- `GuidanceOrchestrator` coordinates planning, grounding, recovery, and trace events.
- `GuidanceOverlay` renders visible arrows/highlights without clicking.

Genie never invents a click location when confidence is too low. It asks the user to re-scan, mark done, select a region, or continue with text-only guidance.

## Activity Recording

Activity tracking is explicit session-based tracking:

- `ActivitySessionManager`
- `ScreenFrameSampler`
- `TimelineAssembler`
- `ActivitySummarizer`

Genie samples frames during a user-requested interval, assembles a timeline, and summarizes only visible action changes after the recording started. It does not claim past history unless a recording session actually ran.

## Verification

Use these commands:

```powershell
npm.cmd run test:backend
npm.cmd run test:desktop
npm.cmd run typecheck:desktop
npm.cmd run eval:guidance
npm.cmd run audit:package
```

The debug panel and Settings screen expose provider diagnostics so judges can tell whether the app is using live Gemma, local model mode, or fallback behavior.
