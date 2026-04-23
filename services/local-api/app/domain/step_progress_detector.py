from __future__ import annotations

from app.core.text_matching import terms
from app.models.contracts import GroundingResult, GuidedTaskStep, StepProgressState


class StepProgressDetector:
    def detect(
        self,
        *,
        step: GuidedTaskStep,
        grounding: GroundingResult | None,
        previous_screen_text: str,
        current_screen_text: str,
        mode: str = "conservative",
        screen_changed: bool = False,
    ) -> StepProgressState:
        current_terms = terms(current_screen_text)
        previous_terms = terms(previous_screen_text)
        hint_terms = terms(step.completion_hint)
        label_terms = terms((grounding.target_label or "") if grounding else "")
        target_terms = terms(step.target_description)
        instruction_terms = terms(step.instruction_text)

        if hint_terms and hint_terms & current_terms:
            return StepProgressState(state="completed", confidence=0.95, reason="Completion hint text is visible.", auto_advanced=True)

        if label_terms and label_terms <= previous_terms and not (label_terms & current_terms):
            confidence = 0.9 if mode == "balanced" else 0.84
            state = "completed"
            return StepProgressState(
                state=state,
                confidence=confidence,
                reason="The previously grounded target is no longer visible on screen.",
                auto_advanced=state == "completed",
            )

        if target_terms and target_terms & current_terms:
            return StepProgressState(
                state="waiting",
                confidence=0.25,
                reason="The target still appears to be visible, so I am waiting for confirmation.",
                auto_advanced=False,
            )

        if screen_changed or current_screen_text.strip() != previous_screen_text.strip():
            if self._looks_like_navigation_step(step, instruction_terms | target_terms):
                return StepProgressState(
                    state="completed",
                    confidence=0.86 if mode == "balanced" else 0.82,
                    reason="The screen changed after a navigation or address-bar step.",
                    auto_advanced=True,
                )
            return StepProgressState(
                state="uncertain",
                confidence=0.52 if mode == "balanced" else 0.4,
                reason="The visible screen changed, so I am re-checking the next step from the current screen.",
                auto_advanced=False,
            )

        return StepProgressState(
            state="needs_confirmation",
            confidence=0.2,
            reason="I cannot confirm that this step is complete yet.",
            auto_advanced=False,
        )

    def _looks_like_navigation_step(self, step: GuidedTaskStep, step_terms: set[str]) -> bool:
        text = f"{step.instruction_text} {step.target_description} {step.completion_hint}".lower()
        navigation_words = {"address", "url", "browser", "tab", "navigate", "open", "search", "type", "enter", "go"}
        if navigation_words & step_terms:
            return True
        return any(marker in text for marker in ("http://", "https://", ".com", ".org", ".net", "address bar", "search bar"))
