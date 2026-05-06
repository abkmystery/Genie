# Kaggle Writeup

## Title

Genie: A Privacy-First Digital Access Companion Powered by Gemma 4

## Subtitle

A desktop AI companion that sees the current screen, grounds answers in private files, and guides users through complex digital workflows without taking control.

## Selected Track

Impact Track - Digital Equity

## Writeup

Many people do not fail at digital tasks because they lack intelligence. They fail because modern websites, portals, forms, dashboards, school systems, healthcare pages, job applications, and government services assume too much context. A user may not know what a page is asking, which field matters, whether a document contains the needed answer, or where to click next. Genie was built for that gap: a privacy-first desktop companion that helps users understand and complete digital workflows safely.

Genie is not another chatbot in a window. It is an always-available screen companion. The user can ask about what is currently visible, attach private files, select a region of the screen, record a short activity session, or ask Genie to guide them step by step. Genie answers with citations and debug traces, and in Guided Task mode it points with an on-screen arrow while leaving every click and decision to the user.

### Why This Fits Digital Equity

Digital access is no longer only about having an internet connection. It is about being able to navigate systems that are dense, high-stakes, and often unforgiving. Genie is designed for students filling out education portals, job seekers reading application forms, caregivers navigating benefits pages, and anyone who needs plain-language help on the screen in front of them.

The safety boundary is intentional: Genie guides, but it does not click, type, submit forms, run shell commands, send emails, mutate files, or bypass user control. This keeps the product useful for real workflows while avoiding the trust and reliability risks of autonomous desktop control.

### Architecture

The architecture is split into clear, replaceable layers:

- `apps/desktop`: Electron + React desktop app, launcher, chat panel, settings, source manager, debug panel, region selector, and guidance overlay.
- `services/local-api`: FastAPI orchestration layer. The desktop app talks only to this local service.
- `services/demo-gateway`: optional deployable gateway scaffold for server-side provider hosting.
- `services/local-gemma-runner`: experimental local OpenAI-compatible Gemma 4 runner.
- `packages/contracts`: shared schemas and TypeScript types.
- `config/profiles`: public profile metadata for Demo, Local, and Custom modes.

This separation matters. React components do not call arbitrary model endpoints. The local API owns profile resolution, source ingestion, retrieval, screen context, activity recording, guided task orchestration, provider routing, citations, and traces. That makes the system inspectable and safer to evolve.

### How Genie Uses Gemma 4

Genie uses Gemma 4 through provider abstractions rather than hardcoding a single model path.

The primary demo path is:

`Electron desktop -> local-api -> DemoModelProvider -> Gemini OpenAI-compatible /chat/completions -> Gemma 4`

For the recorded demo, Demo mode uses Google-hosted Gemma 4 through the Gemini OpenAI-compatible interface. The private demo credential is intentionally excluded from the public repository and resolved only from a local ignored demo config file for private demo builds. Public source contains only an example template and fallback behavior.

The local experimentation path is:

`Electron desktop -> local-api -> OpenAI-compatible local profile -> local-gemma-runner -> Hugging Face Gemma 4`

The local runner exposes `/ready`, `/warmup`, `/diagnostics`, `/v1/models`, `/v1/chat/completions`, and `/smoke`. It uses `AutoProcessor`, `AutoModelForMultimodalLM`, and `processor.apply_chat_template(...)` for Gemma 4 text, image, and audio-capable local model messages where supported. We also added memory preflight checks because E4B-class local models can exceed practical RAM limits on 16 GB laptops.

Gemma 4 is used for screen understanding, selected-region understanding, file-grounded answers, guided task planning, target grounding, and activity summaries from sampled screen timelines. The local API builds OpenAI-style multimodal payloads with text plus base64 `image_url` data URLs for screenshots and selected regions.

### Grounded Answers and Private Files

Genie supports local ingestion for `.txt`, `.md`, `.csv`, `.xlsx`, `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, and `.webp`. Files are parsed locally, chunked, indexed, and retrieved as evidence. Answers include structured citations such as a source file, page, sheet, row range, screen, or selected region.

This design is deliberately not "upload everything and hope." The local API first narrows context through retrieval and screen/region services, then sends relevant evidence and images to the active provider. The user can also inspect debug traces showing provider status, source hits, timing, and errors.

### Guided Task Mode

The most important interaction is Guided Task mode. A user can type something like "Guide me through checking high prize competitions on Kaggle." Genie creates a short plan, analyzes the current screen, grounds the next visible target, and renders an overlay arrow or highlight. It then waits for confirmation or conservative progress detection before moving forward.

This was harder than it sounds. Screens change, browser zoom changes, windows move, and a model can easily point to the wrong thing. We built guidance as a conservative loop with `TaskPlanner`, `TargetGrounder`, `StepProgressDetector`, `RecoveryPolicy`, and `GuidanceOrchestrator`. If confidence is low, Genie does not hallucinate a click location. It offers re-scan, region selection, "I can't find it," or text-only recovery.

### Activity Recording

Genie also supports explicit short screen tracking. When the user starts Track Screen, Genie samples frames and events during that window only. At the end, it produces an ordered action summary: for example, went to a site, focused a page, clicked a visible area, or reached a filter section. It does not narrate everything on screen, and it does not pretend to remember past activity unless a recording session actually ran.

### Challenges and Technical Choices

The biggest challenge was balancing capability with trust. Adding desktop automation with tools like PyAutoGUI would have been flashy, but unsafe. The current product is more honest: it provides screen-aware guidance and leaves control with the user.

A second challenge was provider reliability. Hosted Gemma 4 is the reliable judge path, while local Gemma 4 is an optional proof of edge readiness. This is why the UI exposes provider status such as Live Gemma, Offline fallback, Local model not ready, and Endpoint error. Silent fallback would make the demo look smoother, but it would be less truthful.

A third challenge was making model output humane. Genie sanitizes chain-of-thought tags, avoids raw prompt leakage, and converts math-style formatting into plain language for display and speech. For example, a trigonometry formula is explained as "tangent alpha equals sine alpha divided by cosine alpha" instead of reading dollar signs, slashes, and LaTeX.

### Validation

The public repository is the source of truth: `https://github.com/abkmystery/Genie`.

Before submission we ran:

- 53 local-api tests, 2 demo-gateway tests, and 8 local-gemma-runner tests.
- 5 desktop Vitest tests.
- TypeScript desktop typecheck.
- Guidance eval with 20/20 target cases passing.
- Package audit for unsafe artifacts.

The public repository contains no real provider keys, no model weights, no local databases, no screen captures, and no release bundles. The private demo build can include a local ignored demo credential file, but that file is not committed.

### Conclusion

Genie demonstrates a practical Gemma 4 application for digital equity: a companion that sees the screen, understands private context, explains in plain language, and guides the next step without taking control. The result is not just a chatbot. It is a safer interaction pattern for AI on the desktop: grounded, inspectable, human-in-the-loop, and useful for the real digital tasks people struggle with every day.

## Assets 

- Public video: https://youtu.be/WFLS7RgKG1A
- Public code repository: `https://github.com/abkmystery/Genie`
- Live demo/prototype: Download attached installer, give it a minute to get setup and then run in demo mode.
- Media gallery: Relevant Images and Video are attached
