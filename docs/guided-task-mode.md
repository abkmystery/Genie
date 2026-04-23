# Guided Task Mode

Guided Task Mode lets Genie guide the user step by step on the live screen without taking control of the computer.

## What It Does

- Turns a request like "Guide me through this" into a short step plan.
- Grounds the current step against the current screen.
- Shows a visible arrow or highlight overlay when grounding succeeds.
- Waits for either:
  - explicit user confirmation, or
  - a conservative completion signal from the latest screen re-scan.

## What It Does Not Do

- It does not click, type, submit, or automate actions.
- It does not invent target locations when grounding fails.
- It does not pretend a step is complete unless the user confirms it or the completion detector crosses the configured threshold.

## Overlay Grounding

- Genie reuses the current screen capture and OCR pipeline.
- `TargetGrounder` looks for visible text that matches the current step target.
- If a match is found, Genie renders an overlay arrow or highlight around the best bounding box.
- If no reliable match is found, Genie falls back to recovery suggestions instead of hallucinating.

## Manual Fallback Controls

During a guided session the user can:

- `Mark Done`
- `Next Step`
- `Re-scan`
- `I can't find it`
- `Pause`
- `Stop Guidance`

`I can't find it` is designed to work with the region-draw flow so the user can circle the relevant area and let Genie re-ground inside that part of the screen.

## Limitations

- Text grounding is strongest when the target control has visible OCR-friendly text.
- Icon-only controls are harder to locate reliably without stronger UI understanding.
- On screens where OCR is unavailable or very weak, Genie may fall back to text-only guidance or ask for confirmation.

## Why Genie May Ask for Confirmation

Guided Task Mode is intentionally conservative. If Genie is not confident that the target moved or the next state appeared, it keeps the user in control and asks for confirmation instead of advancing incorrectly.
