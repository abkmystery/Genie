from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import re

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

        deterministic_summary = self._summary_from_steps(heuristic_steps)
        prompt = (
            "You are summarizing an explicit desktop activity recording. "
            "Use only actions that happened after the recording started. "
            "Do not narrate static page contents, OCR dumps, pixels, or everything visible on screen. "
            "Return only a concise ordered action recap: went to this site/page, clicked or focused this visible control, selected this option, switched to this app. "
            "If the timeline only shows a window/page change and no click evidence, say 'Focused' or 'Viewed', not 'clicked'. "
            "Do not invent actions."
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
        diagnostics = response.provider_diagnostics
        if diagnostics and diagnostics.provider_status != "live_gemma":
            return ActivitySummary(
                session_id=timeline.session_id,
                started_at=started_at,
                ended_at=ended_at,
                summary_text=deterministic_summary,
                steps=heuristic_steps,
                uncertain=False,
                provider_used="activity:heuristic",
                warnings=[diagnostics.last_model_error or diagnostics.fallback_reason or "Model summarizer was unavailable; used local timeline actions."],
            )
        return ActivitySummary(
            session_id=timeline.session_id,
            started_at=started_at,
            ended_at=ended_at,
            summary_text=self._clean_model_summary(response.answer) or deterministic_summary,
            steps=heuristic_steps,
            uncertain=False,
            provider_used=response.provider_used,
            warnings=[],
        )

    def _heuristic_steps(self, timeline: ActivityTimeline) -> list[str]:
        steps: list[str] = []
        last_title: str | None = None
        last_page_hint: str | None = None

        for frame in timeline.representative_frames:
            title = self._clean_window_title(frame.window_title)
            if title and title != last_title:
                steps.append(self._format_timed_step(timeline.started_at, frame.timestamp, f"Focused on {title}."))
                last_title = title

            page_hint = self._extract_page_action_hint(frame.ocr_text or frame.summary)
            if page_hint and page_hint != last_page_hint:
                steps.append(self._format_timed_step(timeline.started_at, frame.timestamp, page_hint))
                last_page_hint = page_hint

        if not steps:
            for event in timeline.events:
                if event.type not in {"window_changed", "recording_started", "recording_stopped"}:
                    continue
                if event.type == "window_changed" and event.window_title:
                    title = self._clean_window_title(event.window_title)
                    if title and title != last_title:
                        steps.append(self._format_timed_step(timeline.started_at, event.timestamp, f"Focused on {title}."))
                        last_title = title
                if len(steps) >= 8:
                    break

        if not steps:
            steps.append("Recorded the screen, but no clear user-visible action change was detected.")

        normalized: list[str] = []
        for index, step in enumerate(steps[:8], start=1):
            normalized.append(f"Step {index}: {step}")
        return normalized

    def _format_timed_step(self, started_at: datetime, timestamp: datetime, text: str) -> str:
        elapsed = max(0, round((timestamp - started_at).total_seconds()))
        return f"+{elapsed}s - {text}"

    def _clean_window_title(self, title: str | None) -> str | None:
        cleaned = " ".join((title or "").split())
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if lowered in {"genie", "ai companion"}:
            return None
        cleaned = re.sub(r"\s+[-|]\s+(google chrome|microsoft edge|mozilla firefox|brave|opera)$", "", cleaned, flags=re.I)
        return cleaned[:120]

    def _extract_page_action_hint(self, text: str | None) -> str | None:
        cleaned = " ".join((text or "").split())
        if not cleaned or cleaned == "[redacted-sensitive-text]":
            return None
        lowered = cleaned.lower()
        if "filters" in lowered and ("competitions" in lowered or "search competitions" in lowered):
            return "Reached the competitions filter/search area."
        if "kaggle" in lowered and "competitions" in lowered:
            return "Viewed the Kaggle competitions page."
        if "new tab" in lowered or "search or type a url" in lowered:
            return "Opened or focused a browser tab/address bar."
        if "excel" in lowered or "workbook" in lowered:
            return "Focused an Excel workbook."
        return None

    def _summary_from_steps(self, steps: list[str]) -> str:
        return "Recorded actions after tracking started. The ordered steps below show only visible action changes, not a full narration of the screen."

    def _clean_model_summary(self, value: str) -> str:
        cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", value or "", flags=re.I).strip()
        cleaned = re.sub(r"\b(Image file|Native screen capture|pixels?|OCR dump)\b.*", "", cleaned, flags=re.I).strip()
        return cleaned[:800]
