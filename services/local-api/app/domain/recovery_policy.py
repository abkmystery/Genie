from __future__ import annotations

from app.models.contracts import GuidedTaskStep


class RecoveryPolicy:
    def grounding_failure_options(self, step: GuidedTaskStep) -> list[str]:
        return [
            f"Re-scan the current screen and look again for {step.target_description}.",
            "Use Draw Region to circle the area you want me to focus on, then re-scan.",
            "Switch to the page or section that contains the control and ask me to continue.",
            "Follow the text-only instruction for now if the target is not visibly labeled.",
        ]

    def completion_uncertain_options(self) -> list[str]:
        return [
            "Mark done when you finish the step.",
            "Use Re-scan after the page changes.",
            "Pause guidance if you need to navigate manually for a moment.",
        ]
