from __future__ import annotations

from app.domain.guidance_screen_state import GuidanceScreenStateAnalyzer
from app.domain.guided_task_session_manager import GuidedTaskSessionManager
from app.domain.guided_task_trace_logger import GuidedTaskTraceLogger
from app.domain.recovery_policy import RecoveryPolicy
from app.domain.step_progress_detector import StepProgressDetector
from app.domain.task_planner import TaskPlanner
from app.domain.target_grounder import TargetGrounder
from app.models.contracts import (
    EvidenceItem,
    GroundingResult,
    GuidedTaskStatus,
    ProviderConfig,
    RegionContext,
    ScreenContext,
    StartGuidedTaskResponse,
    StopGuidedTaskResponse,
)
from app.providers.interfaces import ModelProvider


class GuidanceOrchestrator:
    def __init__(
        self,
        *,
        session_manager: GuidedTaskSessionManager,
        planner: TaskPlanner,
        grounder: TargetGrounder,
        progress_detector: StepProgressDetector,
        recovery_policy: RecoveryPolicy,
        trace_logger: GuidedTaskTraceLogger,
        screen_state_analyzer: GuidanceScreenStateAnalyzer | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.planner = planner
        self.grounder = grounder
        self.progress_detector = progress_detector
        self.recovery_policy = recovery_policy
        self.trace_logger = trace_logger
        self.screen_state_analyzer = screen_state_analyzer or GuidanceScreenStateAnalyzer()

    async def start(
        self,
        *,
        goal: str,
        conversation_id: str | None,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        evidence: list[EvidenceItem],
        profile: ProviderConfig,
        provider: ModelProvider,
        max_steps: int,
        overlay_style: str,
    ) -> StartGuidedTaskResponse:
        plan = await self.planner.plan(
            goal=goal,
            screen_context=screen_context,
            region_context=region_context,
            evidence=evidence,
            profile=profile,
            provider=provider,
            max_steps=max_steps,
        )
        trace_id = self.trace_logger.trace_service.new_trace_id()
        self.trace_logger.emit(trace_id, "GUIDED_TASK_STARTED", "Guided task session started", {"goal": goal})
        self.trace_logger.emit(trace_id, "TASK_PLAN_CREATED", "Guided task plan created", {"steps": len(plan.steps), "title": plan.title})
        status = self.session_manager.start(
            plan=plan,
            conversation_id=conversation_id,
            trace_id=trace_id,
            evidence=evidence,
            max_steps=max_steps,
        )
        status = await self._ground_current_step(
            screen_context=screen_context,
            region_context=region_context,
            overlay_style=overlay_style,
            profile=profile,
            provider=provider,
        )
        return StartGuidedTaskResponse(ok=True, status=status, message="Guided task started.")

    def current(self) -> GuidedTaskStatus:
        return self.session_manager.current()

    def stop(self) -> StopGuidedTaskResponse:
        status = self.session_manager.stop()
        if status.session:
            self.trace_logger.emit(status.session.trace_id, "GUIDED_TASK_STOPPED", "Guided task stopped", {"session_id": status.session.id})
        return StopGuidedTaskResponse(ok=bool(status.session), status=status, message="Guided task stopped." if status.session else "No active guided task.")

    def pause(self, paused: bool) -> GuidedTaskStatus:
        status = self.session_manager.pause(paused)
        if status.session:
            self.trace_logger.emit(status.session.trace_id, "OVERLAY_RENDERED", "Guided task pause state updated", {"paused": paused})
        return status

    async def confirm_step(
        self,
        *,
        overlay_style: str,
        screen_context: ScreenContext,
        profile: ProviderConfig,
        provider: ModelProvider,
        region_context: RegionContext | None = None,
    ) -> GuidedTaskStatus:
        trace_id = self.session_manager.current_trace_id()
        if trace_id:
            self.trace_logger.emit(trace_id, "STEP_CONFIRMED_BY_USER", "User confirmed the current step", {})
        status = self.session_manager.advance()
        if status.session and status.session.status == "completed":
            if trace_id:
                self.trace_logger.emit(trace_id, "GUIDED_TASK_STOPPED", "Guided task completed", {"session_id": status.session.id})
            return status
        return await self._ground_current_step(
            screen_context=screen_context,
            region_context=region_context,
            overlay_style=overlay_style,
            profile=profile,
            provider=provider,
        )

    async def rescan(
        self,
        *,
        overlay_style: str,
        screen_context: ScreenContext,
        profile: ProviderConfig,
        provider: ModelProvider,
        region_context: RegionContext | None = None,
    ) -> GuidedTaskStatus:
        return await self._ground_current_step(
            screen_context=screen_context,
            region_context=region_context,
            overlay_style=overlay_style,
            profile=profile,
            provider=provider,
        )

    def cant_find_it(self) -> GuidedTaskStatus:
        step = self.session_manager.current_step()
        status = self.session_manager.update(
            status="needs_attention",
            recovery_options=self.recovery_policy.grounding_failure_options(step) if step else self.recovery_policy.completion_uncertain_options(),
        )
        if status.session:
            self.trace_logger.emit(status.session.trace_id, "STEP_GROUNDING_FAILED", "User could not find the grounded target", {})
        return status

    async def observe(
        self,
        *,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        profile: ProviderConfig,
        provider: ModelProvider,
        completion_mode: str,
        auto_advance_sensitivity: float,
        overlay_style: str,
    ) -> GuidedTaskStatus:
        status = self.session_manager.current()
        if not status.session or status.current_step is None:
            return status
        if status.session.status == "needs_attention":
            return await self._ground_current_step(
                screen_context=screen_context,
                region_context=region_context,
                overlay_style=overlay_style,
                profile=profile,
                provider=provider,
            )
        if status.session.status != "active":
            return status

        previous_screen_text = self.session_manager.previous_screen_text()
        previous_screen_signature = self.session_manager.previous_screen_signature()
        current_screen_signature = self.screen_state_analyzer.screen_signature(screen_context)
        screen_changed = self.screen_state_analyzer.has_screen_changed(previous_screen_signature, current_screen_signature)
        progress = self.progress_detector.detect(
            step=status.current_step,
            grounding=status.latest_grounding,
            previous_screen_text=previous_screen_text,
            current_screen_text=screen_context.text,
            mode=completion_mode,
            screen_changed=screen_changed,
        )
        # When the visible page/app changes, clear and re-evaluate the overlay instead of
        # letting a stale arrow point at the wrong window until the next user action.
        should_refresh = self.screen_state_analyzer.should_refresh_grounding(
            progress=progress,
            current_step=status.current_step,
            grounding=status.latest_grounding,
            previous_screen_text=previous_screen_text,
            current_screen_text=screen_context.text,
            screen_changed=screen_changed,
        )
        updated = self.session_manager.update(
            progress_state=progress,
            previous_screen_text=screen_context.text,
            previous_screen_signature=current_screen_signature,
            clear_grounding=should_refresh,
            status="needs_attention" if should_refresh else None,
        )
        if updated.session:
            self.trace_logger.emit(
                updated.session.trace_id,
                "STEP_COMPLETION_DETECTED",
                "Guided task progress evaluated",
                {"state": progress.state, "confidence": progress.confidence},
            )
        if should_refresh:
            return await self._ground_current_step(
                screen_context=screen_context,
                region_context=region_context,
                overlay_style=overlay_style,
                profile=profile,
                provider=provider,
                force_replan=self.screen_state_analyzer.should_force_replan(
                    screen_context=screen_context,
                    current_step_index=status.session.current_step_index,
                    steps=status.plan.steps if status.plan else [],
                ),
            )
        if progress.state == "completed" and progress.confidence >= auto_advance_sensitivity:
            return await self.confirm_step(
                overlay_style=overlay_style,
                screen_context=screen_context,
                region_context=region_context,
                profile=profile,
                provider=provider,
            )
        return updated

    async def _ground_current_step(
        self,
        *,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        overlay_style: str,
        profile: ProviderConfig,
        provider: ModelProvider,
        allow_replan: bool = True,
        force_replan: bool = False,
    ) -> GuidedTaskStatus:
        status = self.session_manager.current()
        if not status.session or status.current_step is None or status.plan is None:
            return status

        # A manual re-scan means "trust the current screen over the old plan".
        # Re-plan first so generic stale steps like "click the address bar" do not
        # keep grounding successfully after the user switches apps or pages.
        if force_replan:
            await self._replan_for_current_screen(
                screen_context=screen_context,
                region_context=region_context,
                profile=profile,
                provider=provider,
            )
            status = self.session_manager.current()
            if not status.session or status.current_step is None or status.plan is None:
                return status
        current_step_index = status.session.current_step_index

        candidate_indexes = self.screen_state_analyzer.candidate_step_indexes(
            screen_context=screen_context,
            current_step_index=current_step_index,
            steps=status.plan.steps,
        )

        grounded_step = status.current_step
        grounding: GroundingResult | None = None
        for step_index in candidate_indexes:
            step = status.plan.steps[step_index]
            attempt = await self.grounder.ground(
                step=step,
                screen_context=screen_context,
                profile=profile,
                region_context=region_context,
                overlay_style=overlay_style,
            )
            if not attempt.success:
                if grounding is None or attempt.confidence > grounding.confidence:
                    grounding = attempt
                continue

            grounding = attempt
            if step_index != current_step_index:
                self.session_manager.jump_to(step_index)
                grounded_step = step
                self.trace_logger.emit(
                    status.session.trace_id,
                    "STEP_ADVANCED",
                    "Guided task re-anchored to a step that matches the current screen",
                    {
                        "from_step_index": current_step_index,
                        "to_step_index": step_index,
                        "step_id": step.step_id,
                    },
                )
            break

        if (grounding is None or not grounding.success) and allow_replan:
            replanned = await self._replan_for_current_screen(
                screen_context=screen_context,
                region_context=region_context,
                profile=profile,
                provider=provider,
            )
            if replanned:
                return await self._ground_current_step(
                    screen_context=screen_context,
                    region_context=region_context,
                    overlay_style=overlay_style,
                    profile=profile,
                    provider=provider,
                    allow_replan=False,
                )

        if grounding is None:
            grounding = self._default_grounding_failure(status.current_step)

        recovery_options = [] if grounding.success else self.recovery_policy.grounding_failure_options(grounded_step)
        updated = self.session_manager.update(
            grounding=grounding,
            recovery_options=recovery_options,
            status="active" if grounding.success else "needs_attention",
            previous_screen_text=screen_context.text,
            previous_screen_signature=self.screen_state_analyzer.screen_signature(screen_context),
        )
        if grounding.success:
            self.trace_logger.emit(
                status.session.trace_id,
                "STEP_GROUNDED",
                "Guided task step grounded on screen",
                {
                    "step_id": grounded_step.step_id,
                    "label": grounding.target_label,
                    "confidence": grounding.confidence,
                },
            )
            if grounding.bbox:
                self.trace_logger.emit(
                    status.session.trace_id,
                    "OVERLAY_RENDERED",
                    "Guidance overlay rendered",
                    {"target_label": grounding.bbox.target_label, "style": grounding.bbox.render_style},
                )
        else:
            self.trace_logger.emit(
                status.session.trace_id,
                "STEP_GROUNDING_FAILED",
                "Guided task grounding failed",
                {"step_id": grounded_step.step_id, "reason": grounding.reason},
            )
        return updated

    async def _replan_for_current_screen(
        self,
        *,
        screen_context: ScreenContext,
        region_context: RegionContext | None,
        profile: ProviderConfig,
        provider: ModelProvider,
    ) -> bool:
        status = self.session_manager.current()
        if not status.session:
            return False
        try:
            plan = await self.planner.plan(
                goal=status.session.goal,
                screen_context=screen_context,
                region_context=region_context,
                evidence=self.session_manager.evidence(),
                profile=profile,
                provider=provider,
                max_steps=self.session_manager.max_steps(),
            )
        except Exception as exc:
            self.trace_logger.emit(
                status.session.trace_id,
                "GUIDED_TASK_ERROR",
                "Guided task replanning failed",
                {"error": str(exc)},
            )
            return False

        if not plan.steps:
            return False

        self.session_manager.replace_plan(plan, step_index=0)
        self.trace_logger.emit(
            status.session.trace_id,
            "TASK_PLAN_CREATED",
            "Guided task plan refreshed from the current screen",
            {"steps": len(plan.steps), "title": plan.title, "mode": "replan"},
        )
        return True

    def _default_grounding_failure(self, step) -> GroundingResult:
        return GroundingResult(
            success=False,
            confidence=0.0,
            bbox=None,
            target_label=None,
            reason=f"I could not confidently locate {step.target_description} on the current screen.",
            fallback_suggestion="Try Re-scan, switch back to the relevant page, or use Draw Region around the area you want help with.",
        )
