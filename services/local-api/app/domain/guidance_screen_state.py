from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from PIL import Image

from app.core.text_matching import terms
from app.models.contracts import GroundingResult, GuidedTaskStep, ScreenContext, StepProgressState


class GuidanceScreenStateAnalyzer:
    """Small policy object for deciding when a live screen invalidates guidance state."""

    def screen_signature(self, screen_context: ScreenContext) -> str:
        """Return a stable-enough signature for detecting visible screen changes.

        OCR can be empty on many machines, so guidance cannot rely only on text.
        A small average-hash catches app/page changes while ignoring tiny timestamp
        and cursor differences better than raw capture ids would.
        """

        try:
            with Image.open(Path(screen_context.capture.path)) as image:
                # A small quantized thumbnail is more sensitive than a classic
                # average hash, but still stable enough to ignore tiny cursor or
                # video-frame changes.
                grayscale = image.convert("L").resize((32, 18))
                quantized = bytes(min(15, max(0, pixel // 16)) for pixel in grayscale.getdata())
                return f"vhash:{quantized.hex()}"
        except Exception:
            text = f"{screen_context.summary}\n{screen_context.text}".strip()
            if text:
                return f"text:{hashlib.sha1(text.encode('utf-8')).hexdigest()}"
            return f"capture:{screen_context.capture.id}"

    def has_screen_changed(self, previous_signature: str, current_signature: str) -> bool:
        if not previous_signature or not current_signature:
            return False
        if previous_signature.startswith("vhash:") and current_signature.startswith("vhash:"):
            try:
                previous = bytes.fromhex(previous_signature.split(":", 1)[1])
                current = bytes.fromhex(current_signature.split(":", 1)[1])
            except ValueError:
                return previous_signature != current_signature
            if len(previous) != len(current):
                return True
            diffs = [abs(left - right) for left, right in zip(previous, current)]
            changed_pixels = sum(1 for value in diffs if value >= 3)
            mean_delta = sum(diffs) / max(1, len(diffs))
            return changed_pixels > 48 or mean_delta > 0.9
        return previous_signature != current_signature

    def candidate_step_indexes(
        self,
        *,
        screen_context: ScreenContext,
        current_step_index: int,
        steps: Sequence[GuidedTaskStep],
    ) -> list[int]:
        if not steps:
            return []
        if len(steps) == 1:
            return [0]

        screen_terms = terms(f"{screen_context.summary} {screen_context.text}")
        scored = [
            (self._step_relevance_score(step=step, screen_terms=screen_terms, current_step_index=current_step_index), index)
            for index, step in enumerate(steps)
        ]
        scored.sort(key=lambda item: (-item[0], abs(item[1] - current_step_index), item[1]))
        return [index for _, index in scored]

    def should_refresh_grounding(
        self,
        *,
        progress: StepProgressState,
        current_step: GuidedTaskStep,
        grounding: GroundingResult | None,
        previous_screen_text: str,
        current_screen_text: str,
        screen_changed: bool = False,
    ) -> bool:
        if progress.state == "completed":
            return False
        if screen_changed:
            return True
        if not current_screen_text.strip() or current_screen_text.strip() == previous_screen_text.strip():
            return False
        if grounding is None or not grounding.success:
            return True
        if progress.state == "uncertain":
            return True

        current_terms = terms(current_screen_text)
        target_terms = terms(current_step.target_description)
        label_terms = terms(grounding.target_label or "")
        return bool((target_terms and not (target_terms & current_terms)) or (label_terms and not (label_terms & current_terms)))

    def _step_relevance_score(self, *, step: GuidedTaskStep, screen_terms: set[str], current_step_index: int) -> float:
        step_terms = terms(f"{step.target_description} {step.instruction_text} {step.completion_hint}")
        overlap = len(step_terms & screen_terms)
        position_bias = max(0.0, 1.0 - (abs(step.order_index - current_step_index) * 0.18))
        current_bias = 0.35 if step.order_index == current_step_index else 0.0
        return overlap + position_bias + current_bias
