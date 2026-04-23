from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.models.contracts import (
    EvidenceItem,
    GroundingResult,
    GuidedTaskPlan,
    GuidedTaskStep,
    GuidedTaskSession,
    GuidedTaskStatus,
    StepProgressState,
)


@dataclass
class _ManagedGuidedTask:
    session: GuidedTaskSession
    plan: GuidedTaskPlan
    evidence: list[EvidenceItem] = field(default_factory=list)
    max_steps: int = 6
    latest_grounding: GroundingResult | None = None
    progress_state: StepProgressState | None = None
    recovery_options: list[str] = field(default_factory=list)
    previous_screen_text: str = ""
    previous_screen_signature: str = ""


class GuidedTaskSessionManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current: _ManagedGuidedTask | None = None
        self._last: _ManagedGuidedTask | None = None

    @staticmethod
    def _empty_status() -> GuidedTaskStatus:
        return GuidedTaskStatus(recovery_options=[])

    def start(
        self,
        *,
        plan: GuidedTaskPlan,
        conversation_id: str | None,
        trace_id: str,
        evidence: list[EvidenceItem],
        max_steps: int,
    ) -> GuidedTaskStatus:
        now = datetime.now(timezone.utc)
        managed = _ManagedGuidedTask(
            session=GuidedTaskSession(
                id=str(uuid4()),
                conversation_id=conversation_id,
                title=plan.title,
                goal=plan.goal,
                status="active",
                created_at=now,
                updated_at=now,
                current_step_index=0,
                trace_id=trace_id,
            ),
            plan=plan,
            evidence=list(evidence),
            max_steps=max_steps,
        )
        with self._lock:
            self._current = managed
        return self._status_from(managed)

    def current(self) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            return self._status_from(self._current)

    def last(self) -> GuidedTaskStatus:
        with self._lock:
            if self._last is None:
                return self._empty_status()
            return self._status_from(self._last)

    def update(
        self,
        *,
        grounding: GroundingResult | None = None,
        clear_grounding: bool = False,
        progress_state: StepProgressState | None = None,
        recovery_options: list[str] | None = None,
        previous_screen_text: str | None = None,
        previous_screen_signature: str | None = None,
        status: str | None = None,
        last_error: str | None = None,
    ) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            if clear_grounding:
                self._current.latest_grounding = None
            if grounding is not None:
                self._current.latest_grounding = grounding
            if progress_state is not None:
                self._current.progress_state = progress_state
            if recovery_options is not None:
                self._current.recovery_options = recovery_options
            if previous_screen_text is not None:
                self._current.previous_screen_text = previous_screen_text
            if previous_screen_signature is not None:
                self._current.previous_screen_signature = previous_screen_signature
            if status is not None:
                self._current.session.status = status
            if last_error is not None:
                self._current.session.last_error = last_error
            self._current.session.updated_at = datetime.now(timezone.utc)
            return self._status_from(self._current)

    def advance(self) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            next_index = self._current.session.current_step_index + 1
            self._current.session.current_step_index = next_index
            self._current.latest_grounding = None
            self._current.progress_state = None
            self._current.recovery_options = []
            self._current.previous_screen_text = ""
            if next_index >= len(self._current.plan.steps):
                self._current.session.status = "completed"
                self._last = self._current
                self._current = None
                return self._status_from(self._last)
            self._current.session.status = "active"
            self._current.session.updated_at = datetime.now(timezone.utc)
            return self._status_from(self._current)

    def jump_to(self, step_index: int) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            bounded_index = max(0, min(step_index, len(self._current.plan.steps) - 1))
            self._current.session.current_step_index = bounded_index
            self._current.session.status = "active"
            self._current.session.updated_at = datetime.now(timezone.utc)
            self._current.latest_grounding = None
            self._current.progress_state = None
            self._current.recovery_options = []
            self._current.previous_screen_text = ""
            return self._status_from(self._current)

    def replace_plan(self, plan: GuidedTaskPlan, *, step_index: int = 0) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            self._current.plan = plan
            self._current.session.title = plan.title
            self._current.session.goal = plan.goal
            self._current.session.current_step_index = max(0, min(step_index, len(plan.steps) - 1)) if plan.steps else 0
            self._current.session.status = "active" if plan.steps else "needs_attention"
            self._current.session.updated_at = datetime.now(timezone.utc)
            self._current.latest_grounding = None
            self._current.progress_state = None
            self._current.recovery_options = []
            self._current.previous_screen_text = ""
            return self._status_from(self._current)

    def pause(self, paused: bool) -> GuidedTaskStatus:
        return self.update(status="paused" if paused else "active")

    def stop(self) -> GuidedTaskStatus:
        with self._lock:
            if self._current is None:
                return self._empty_status()
            self._current.session.status = "stopped"
            self._current.session.updated_at = datetime.now(timezone.utc)
            self._current.latest_grounding = None
            self._current.progress_state = None
            self._current.recovery_options = []
            self._last = self._current
            self._current = None
            return self._status_from(self._last)

    def _status_from(self, managed: _ManagedGuidedTask) -> GuidedTaskStatus:
        current_step = None
        if managed.session.current_step_index < len(managed.plan.steps):
            current_step = managed.plan.steps[managed.session.current_step_index]
        overlay_target = managed.latest_grounding.bbox if managed.latest_grounding and managed.latest_grounding.success else None
        return GuidedTaskStatus(
            session=managed.session,
            plan=managed.plan,
            current_step=current_step,
            latest_grounding=managed.latest_grounding,
            overlay_target=overlay_target,
            progress_state=managed.progress_state,
            recovery_options=list(managed.recovery_options),
        )

    def current_step(self) -> GuidedTaskStep | None:
        with self._lock:
            if self._current is None:
                return None
            if self._current.session.current_step_index >= len(self._current.plan.steps):
                return None
            return self._current.plan.steps[self._current.session.current_step_index]

    def current_step_index(self) -> int | None:
        with self._lock:
            return self._current.session.current_step_index if self._current else None

    def steps(self) -> list[GuidedTaskStep]:
        with self._lock:
            if self._current is None:
                return []
            return list(self._current.plan.steps)

    def current_trace_id(self) -> str | None:
        with self._lock:
            return self._current.session.trace_id if self._current else None

    def previous_screen_text(self) -> str:
        with self._lock:
            return self._current.previous_screen_text if self._current else ""

    def previous_screen_signature(self) -> str:
        with self._lock:
            return self._current.previous_screen_signature if self._current else ""

    def evidence(self) -> list[EvidenceItem]:
        with self._lock:
            return list(self._current.evidence) if self._current else []

    def max_steps(self) -> int:
        with self._lock:
            return self._current.max_steps if self._current else 6
