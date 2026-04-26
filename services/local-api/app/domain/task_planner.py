from __future__ import annotations

import json
import re
from uuid import uuid4

from app.models.contracts import EvidenceItem, GuidedTaskPlan, GuidedTaskStep, ProviderConfig, RegionContext, ScreenContext
from app.providers.interfaces import ModelProvider


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


class TaskPlanner:
    async def plan(
        self,
        *,
        goal: str,
        screen_context: ScreenContext | None,
        region_context: RegionContext | None,
        evidence: list[EvidenceItem],
        profile: ProviderConfig,
        provider: ModelProvider,
        max_steps: int,
    ) -> GuidedTaskPlan:
        prompt = self._build_prompt(goal=goal, screen_context=screen_context, region_context=region_context, evidence=evidence, max_steps=max_steps)
        response = await provider.answer(
            prompt=prompt,
            profile=profile,
            evidence=evidence[:6],
            screen_context=screen_context,
            region_context=region_context,
        )
        parsed = self._parse_plan(response.answer, goal=goal, max_steps=max_steps)
        if parsed is not None:
            return parsed
        return self._fallback_plan(goal=goal, screen_context=screen_context, max_steps=max_steps)

    def _build_prompt(
        self,
        *,
        goal: str,
        screen_context: ScreenContext | None,
        region_context: RegionContext | None,
        evidence: list[EvidenceItem],
        max_steps: int,
    ) -> str:
        parts = [
            "Create a short guided desktop task plan for Genie.",
            "Return JSON only.",
            'Schema: {"title":"...","steps":[{"instruction_text":"...","target_description":"...","completion_hint":"...","grounding_required":true}]}',
            f"Use at most {max_steps} steps.",
            "Each step must describe one visible user action and the target to ground on screen.",
            "If the task needs confirmation, include a clear completion_hint.",
            "Plan from the user's current visible screen state, not from an idealized starting point.",
            "If the user is in the wrong browser, tab, app, or page, begin by guiding them back to the correct place.",
            "Prefer short navigation steps that can be grounded on the current screen before deeper task steps.",
            "Ignore the Genie companion panel, launcher, and overlay UI. Focus on the underlying app or website the user is working in.",
            f"Goal: {goal}",
        ]
        if screen_context:
            parts.append(f"Screen summary: {screen_context.summary}")
            if screen_context.text:
                parts.append(f"Screen text: {screen_context.text[:1200]}")
        if region_context:
            parts.append(f"Region summary: {region_context.summary}")
        if evidence:
            parts.append("Relevant source evidence:")
            for item in evidence[:4]:
                quote = (item.quote or "").strip()
                parts.append(f"- {item.label}: {quote}" if quote else f"- {item.label}")
        return "\n".join(parts)

    def _parse_plan(self, raw: str, *, goal: str, max_steps: int) -> GuidedTaskPlan | None:
        match = _JSON_BLOCK_RE.search(raw)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:
            return None
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            return None

        normalized_steps: list[GuidedTaskStep] = []
        for index, step in enumerate(steps[:max_steps]):
            if not isinstance(step, dict):
                continue
            instruction = str(step.get("instruction_text") or "").strip()
            target = str(step.get("target_description") or "").strip()
            hint = str(step.get("completion_hint") or "").strip()
            if not instruction or not target:
                continue
            if self._is_vague_step(instruction=instruction, target=target):
                continue
            normalized_steps.append(
                GuidedTaskStep(
                    step_id=str(uuid4()),
                    order_index=index,
                    instruction_text=instruction,
                    target_description=target,
                    completion_hint=hint or f"Confirm that step {index + 1} is finished.",
                    grounding_required=bool(step.get("grounding_required", True)),
                )
            )
        if not normalized_steps:
            return None
        return GuidedTaskPlan(
            title=str(data.get("title") or self._derive_title(goal)),
            goal=goal,
            estimated_steps=len(normalized_steps),
            steps=normalized_steps,
        )

    def _fallback_plan(self, *, goal: str, screen_context: ScreenContext | None, max_steps: int) -> GuidedTaskPlan:
        lowered = goal.lower()
        screen_text = f"{screen_context.summary if screen_context else ''} {screen_context.text if screen_context else ''}".lower()
        fallback_steps: list[tuple[str, str, str]] = []
        if self._looks_like_kaggle_competition_goal(lowered):
            fallback_steps = self._kaggle_competition_steps(screen_text)
        elif "form" in lowered or "submit" in lowered:
            fallback_steps = [
                ("Review the current form and locate the first required input.", "the first required field or input label", "The required field is filled in or no longer highlighted."),
                ("Move to the next visible action that continues the form.", "the Continue, Next, or Submit control", "The form advances or a confirmation message appears."),
                ("Confirm that the submission or next page is visible.", "the success message, confirmation banner, or next page heading", "A success or confirmation state is shown."),
            ]
        else:
            fallback_steps = [
                ("Click the most specific visible button, link, tab, or input named in your request.", "the visible label that directly matches the requested action", "The page changes or the requested control opens."),
                ("Use the next visible control that continues the task.", "the visible Next, Continue, Apply, Search, Save, or Submit control", "The interface advances to the next state."),
                ("Check the new page or confirmation area to verify progress.", "the new page heading or confirmation message", "The expected result is visible."),
            ]
        normalized_steps = [
            GuidedTaskStep(
                step_id=str(uuid4()),
                order_index=index,
                instruction_text=instruction,
                target_description=target,
                completion_hint=hint,
                grounding_required=True,
            )
            for index, (instruction, target, hint) in enumerate(fallback_steps[:max_steps])
        ]
        return GuidedTaskPlan(
            title=self._derive_title(goal),
            goal=goal,
            estimated_steps=len(normalized_steps),
            steps=normalized_steps,
        )

    def _derive_title(self, goal: str) -> str:
        compact = goal.strip().rstrip(".")
        if len(compact) <= 72:
            return compact[:1].upper() + compact[1:]
        return f"Guided task: {compact[:68].rstrip()}..."

    def _is_vague_step(self, *, instruction: str, target: str) -> bool:
        text = f"{instruction} {target}".lower()
        vague_markers = (
            "visible area",
            "focus there",
            "matches your goal",
            "related to the task",
            "current focus",
            "control, section, or button",
            "main visible action",
            "whatever",
            "anything relevant",
        )
        return any(marker in text for marker in vague_markers)

    def _looks_like_kaggle_competition_goal(self, lowered_goal: str) -> bool:
        return "kaggle" in lowered_goal and any(term in lowered_goal for term in ("competition", "competitions", "hackathon", "prize", "prized"))

    def _kaggle_competition_steps(self, screen_text: str) -> list[tuple[str, str, str]]:
        on_competitions_page = "competitions and hackathons" in screen_text or "search competitions" in screen_text
        on_kaggle = "kaggle" in screen_text
        if on_competitions_page:
            return [
                ("Click Filters on the right side of the competition search bar.", "Filters", "The filters panel or filter options are visible."),
                ("Choose prize or reward filters if they are available.", "Prize or reward filter", "Prize or reward options are selected or visible."),
                ("Apply the filters or sort competitions by prize if a sort control is visible.", "Apply, Sort, or prize control", "The competition list refreshes with prize-focused results."),
            ]
        if on_kaggle:
            return [
                ("Click Competitions in Kaggle's left navigation.", "Competitions", "The Competitions and Hackathons page is visible."),
                ("Click Filters on the competition search bar.", "Filters", "The filters panel or filter options are visible."),
                ("Choose prize or reward filters if they are available.", "Prize or reward filter", "Prize or reward options are selected or visible."),
            ]
        return [
            ("Click the browser address bar.", "address bar", "The address bar is focused."),
            ("Type kaggle.com and press Enter.", "address bar", "Kaggle is open in the browser."),
            ("Click Competitions in Kaggle's left navigation.", "Competitions", "The Competitions and Hackathons page is visible."),
            ("Click Filters on the competition search bar.", "Filters", "The filters panel or filter options are visible."),
        ]
