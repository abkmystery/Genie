from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

from app.domain.profile_service import ProfileManager, ProviderRegistry
from app.models.contracts import ActivityEvent, ActivityFrameRef, ActivitySessionRecord, ActivitySummary, ActivityTimeline, EvidenceItem


class TimelineAssembler:
    def build(
        self,
        session: ActivitySessionRecord,
        *,
        frames: list[ActivityFrameRef],
        events: list[ActivityEvent],
    ) -> ActivityTimeline:
        representative: list[ActivityFrameRef] = []
        seen_keys: set[str] = set()
        for frame in frames:
            key = frame.dedupe_key or frame.id
            if key in seen_keys:
                continue
            seen_keys.add(key)
            representative.append(frame)
            if len(representative) >= 8:
                break

        ordered_titles = OrderedDict()
        for frame in frames:
            if frame.window_title:
                ordered_titles[frame.window_title] = True
        return ActivityTimeline(
            session_id=session.id,
            started_at=session.started_at,
            ended_at=session.ended_at,
            representative_frames=representative,
            events=events,
            total_frames=len(frames),
            window_titles=list(ordered_titles.keys()),
        )


class ActivitySummarizer:
    def __init__(self, profile_manager: ProfileManager, provider_registry: ProviderRegistry) -> None:
        self.profile_manager = profile_manager
        self.provider_registry = provider_registry

    async def summarize(self, timeline: ActivityTimeline) -> ActivitySummary:
        started_at = timeline.started_at
        ended_at = timeline.ended_at or datetime.now(timezone.utc)
        heuristic_steps = self._heuristic_steps(timeline)
        uncertain = not heuristic_steps or timeline.total_frames == 0

        if uncertain:
            return ActivitySummary(
                session_id=timeline.session_id,
                started_at=started_at,
                ended_at=ended_at,
                summary_text="I recorded the requested session, but I did not capture enough distinct activity to confidently describe step-by-step actions.",
                steps=["Recording ran, but the captured timeline did not contain enough distinct changes to infer reliable steps."],
                uncertain=True,
                provider_used="activity:heuristic",
                warnings=["Summary confidence is low because the timeline had limited visible changes."],
            )

        prompt = (
            "Summarize this recorded desktop activity into a short paragraph and preserve the factual order of actions. "
            "Do not invent missing steps. If something is uncertain, say so briefly."
        )
        evidence = [
            EvidenceItem(
                id=f"activity-step-{index + 1}",
                label=f"[Activity Step {index + 1}]",
                kind="source",
                quote=step,
                locator=str(index + 1),
                score=1.0 - (index * 0.05),
            )
            for index, step in enumerate(heuristic_steps[:10])
        ]
        for index, frame in enumerate(timeline.representative_frames[:4], start=1):
            evidence.append(
                EvidenceItem(
                    id=frame.id,
                    label=f"[Activity Frame {index}]",
                    kind="screen",
                    quote=frame.ocr_text or frame.summary,
                    locator=frame.capture.path,
                    score=0.5,
                )
            )

        profile = self.profile_manager.load_active_profile()
        provider = self.provider_registry.create_model_client(profile)
        response = await provider.answer(
            prompt,
            profile,
            evidence,
            additional_image_paths=[frame.capture.path for frame in timeline.representative_frames[:4]],
        )
        return ActivitySummary(
            session_id=timeline.session_id,
            started_at=started_at,
            ended_at=ended_at,
            summary_text=response.answer,
            steps=heuristic_steps,
            uncertain=False,
            provider_used=response.provider_used,
            warnings=[],
        )

    def _heuristic_steps(self, timeline: ActivityTimeline) -> list[str]:
        steps: list[str] = []
        seen_titles: set[str] = set()
        for title in timeline.window_titles:
            if title and title not in seen_titles:
                seen_titles.add(title)
                steps.append(f"Focused on \"{title}\".")

        if not steps:
            for frame in timeline.representative_frames:
                detail = frame.ocr_text or frame.summary or "Viewed the desktop."
                if detail:
                    steps.append(f"Viewed: {detail}")
                if len(steps) >= 5:
                    break

        normalized: list[str] = []
        for index, step in enumerate(steps[:8], start=1):
            normalized.append(f"Step {index}: {step}")
        return normalized
