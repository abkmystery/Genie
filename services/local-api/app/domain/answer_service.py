from __future__ import annotations

from datetime import datetime, timezone

from app.core.text_matching import terms
from app.domain.activity_recording_service import ActivityRecordingService, parse_activity_prompt
from app.domain.citation_service import CitationService
from app.domain.guided_task_intent import parse_guided_task_prompt
from app.domain.guidance_orchestrator import GuidanceOrchestrator
from app.domain.profile_service import ProfileManager, ProviderRegistry
from app.domain.retrieval_service import RetrievalService
from app.domain.session_service import SessionService
from app.domain.trace_service import TraceService
from app.domain.web_search_service import WebSearchService, should_search_web
from app.models.contracts import AttachmentRecord, ChatRequest, ChatResponse, EvidenceItem, SourceChunk


def _retrieve_attachment_evidence(
    prompt: str,
    *,
    attachment_records: list[AttachmentRecord],
    attachment_chunks: list[SourceChunk],
    limit: int = 4,
) -> list[EvidenceItem]:
    prompt_terms = terms(prompt)
    if not prompt_terms:
        return []

    record_by_id = {record.id: record for record in attachment_records}
    scored: list[tuple[SourceChunk, float]] = []
    for chunk in attachment_chunks:
        overlap = len(prompt_terms & terms(chunk.text))
        if overlap:
            scored.append((chunk, overlap / max(1, len(prompt_terms))))
    scored.sort(key=lambda item: item[1], reverse=True)

    evidence: list[EvidenceItem] = []
    for chunk, score in scored[:limit]:
        record = record_by_id.get(chunk.source_id)
        filename = record.filename if record else chunk.source_id
        label = f"[Attachment: {filename}"
        if chunk.locator:
            label += f" {chunk.locator}"
        label += "]"
        evidence.append(
            EvidenceItem(
                id=chunk.id,
                label=label,
                kind="source",
                quote=chunk.text[:220],
                locator=chunk.locator,
                score=score,
            )
        )
    return evidence


class AnswerService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        profile_manager: ProfileManager,
        provider_registry: ProviderRegistry,
        trace_service: TraceService,
        session_service: SessionService,
        citation_service: CitationService,
        web_search_service: WebSearchService,
        activity_recording_service: ActivityRecordingService,
        guidance_orchestrator: GuidanceOrchestrator,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.profile_manager = profile_manager
        self.provider_registry = provider_registry
        self.trace_service = trace_service
        self.session_service = session_service
        self.citation_service = citation_service
        self.web_search_service = web_search_service
        self.activity_recording_service = activity_recording_service
        self.guidance_orchestrator = guidance_orchestrator

    async def answer(self, request: ChatRequest, *, screen_context=None, region_context=None) -> ChatResponse:
        trace_id = self.trace_service.new_trace_id()
        self.trace_service.emit(trace_id, "REQUEST_RECEIVED", "Chat request received", {"prompt": request.prompt})

        profile = self.profile_manager.load_active_profile()
        self.trace_service.emit(trace_id, "PROFILE_RESOLVED", "Active profile resolved", {"profile_id": profile.id})

        conversation_id = self.session_service.ensure_conversation(request.conversation_id)
        activity_intent = parse_activity_prompt(request.prompt)
        if activity_intent:
            response = self._handle_activity_prompt(
                intent=activity_intent,
                request=request,
                conversation_id=conversation_id,
                trace_id=trace_id,
            )
            self.session_service.add_turn(conversation_id, "user", request.prompt)
            self.session_service.add_turn(conversation_id, "assistant", response.answer)
            self.trace_service.emit(trace_id, "RESPONSE_RENDERED", "Activity response assembled", {"conversation_id": conversation_id})
            return response
        guided_intent = parse_guided_task_prompt(request.prompt)

        if screen_context:
            self.trace_service.emit(
                trace_id,
                "SCREEN_CAPTURED",
                "Screen context attached to the request",
                {"capture_id": screen_context.capture.id, "mode": screen_context.capture.mode},
            )
        if region_context:
            self.trace_service.emit(
                trace_id,
                "REGION_CAPTURED",
                "Region context attached to the request",
                {"capture_id": region_context.capture.id},
            )
        if screen_context or region_context:
            self.trace_service.emit(trace_id, "CONTEXT_BUILT", "Context bundle prepared for grounded answering")

        source_evidence = self.retrieval_service.retrieve_evidence(request.prompt, request.source_ids or None)
        attachment_records = self.session_service.list_attachments(conversation_id)
        attachment_chunks = self.session_service.list_attachment_chunks(conversation_id)
        attachment_evidence = _retrieve_attachment_evidence(
            request.prompt,
            attachment_records=attachment_records,
            attachment_chunks=attachment_chunks,
        )
        merged_local_evidence = [*source_evidence, *attachment_evidence]
        if guided_intent:
            if screen_context is None:
                answer = "I can guide you step by step, but I need the current screen first. Turn screen sharing on or re-scan the page and ask again."
                return ChatResponse(
                    answer=answer,
                    provider_used="guided:missing-screen",
                    trace_id=trace_id,
                    evidence=merged_local_evidence,
                    debug_steps=self.trace_service.list_events(trace_id),
                    conversation_id=conversation_id,
                    warnings=[],
                )
            settings = self.profile_manager.get_settings()
            if not settings.guided_task_enabled:
                answer = "Guided Task mode is disabled in Settings right now, so I did not start guidance."
                return ChatResponse(
                    answer=answer,
                    provider_used="guided:disabled",
                    trace_id=trace_id,
                    evidence=merged_local_evidence,
                    debug_steps=self.trace_service.list_events(trace_id),
                    conversation_id=conversation_id,
                    warnings=[],
                )
            provider = self.provider_registry.create_model_client(profile)
            started = await self.guidance_orchestrator.start(
                goal=str(guided_intent.get("goal") or request.prompt),
                conversation_id=conversation_id,
                screen_context=screen_context,
                region_context=region_context,
                evidence=merged_local_evidence,
                profile=profile,
                provider=provider,
                max_steps=settings.guided_max_planning_steps or 6,
                overlay_style=settings.guided_overlay_style or "arrow_pulse",
            )
            guided_status = started.status
            answer = self._format_guided_task_started(guided_status)
            self.session_service.add_turn(conversation_id, "user", request.prompt)
            self.session_service.add_turn(conversation_id, "assistant", answer)
            self.trace_service.emit(trace_id, "RESPONSE_RENDERED", "Guided task response assembled", {"conversation_id": conversation_id})
            return ChatResponse(
                answer=answer,
                provider_used="guided:started",
                trace_id=trace_id,
                evidence=merged_local_evidence,
                debug_steps=self.trace_service.list_events(trace_id),
                conversation_id=conversation_id,
                warnings=[],
                guided_task_status=guided_status,
            )
        web_evidence: list[EvidenceItem] = []
        if should_search_web(request.prompt):
            try:
                web_evidence = await self.web_search_service.search(request.prompt)
            except Exception as exc:
                self.trace_service.emit(
                    trace_id,
                    "ERROR_RAISED",
                    "Web search enrichment failed",
                    {"error": str(exc)},
                )
        self.trace_service.emit(
            trace_id,
            "RETRIEVAL_COMPLETED",
            "Evidence retrieval completed",
            {"source_hits": len(source_evidence), "attachment_hits": len(attachment_evidence), "web_hits": len(web_evidence)},
        )

        evidence = self.citation_service.merge(
            [*source_evidence, *attachment_evidence, *web_evidence],
            screen_context=screen_context,
            region_context=region_context,
        )
        provider = self.provider_registry.create_model_client(profile)
        response = await provider.answer(
            request.prompt,
            profile,
            evidence,
            screen_context=screen_context,
            region_context=region_context,
            audio_base64=None,
            audio_format=None,
        )
        self.trace_service.emit(trace_id, "MODEL_CALLED", "Model provider returned a response", {"provider": response.provider_used})

        self.session_service.add_turn(conversation_id, "user", request.prompt)
        self.session_service.add_turn(conversation_id, "assistant", response.answer)
        self.trace_service.emit(trace_id, "RESPONSE_RENDERED", "Chat response assembled", {"conversation_id": conversation_id})

        return ChatResponse(
            answer=response.answer,
            provider_used=response.provider_used,
            trace_id=trace_id,
            evidence=evidence,
            debug_steps=self.trace_service.list_events(trace_id),
            conversation_id=conversation_id,
            warnings=(["Web search used only your typed question. Local files, attachments, and screen captures were kept local."] if web_evidence else []),
        )

    def _handle_activity_prompt(self, *, intent: dict[str, object], request: ChatRequest, conversation_id: str, trace_id: str) -> ChatResponse:
        action = str(intent.get("intent") or "")
        warnings: list[str] = []
        evidence: list[EvidenceItem] = []

        if action == "start":
            settings = self.profile_manager.get_settings()
            if not settings.activity_recording_enabled:
                answer = "Activity recording is disabled in Settings right now, so I did not start tracking. Turn it on first and ask again."
                return ChatResponse(answer=answer, provider_used="activity:disabled", trace_id=trace_id, evidence=[], debug_steps=self.trace_service.list_events(trace_id), conversation_id=conversation_id, warnings=[])

            duration_seconds = int(intent.get("duration_seconds") or settings.activity_max_duration_seconds or 60)
            sampling_hz = float(settings.activity_sampling_hz or 1.0)
            started = self.activity_recording_service.start(duration_seconds=min(duration_seconds, settings.activity_max_duration_seconds or duration_seconds), sampling_hz=sampling_hz)
            if not started.ok or started.session is None:
                self.trace_service.emit(trace_id, "ERROR_RAISED", "Activity recording could not start", {"message": started.message})
                return ChatResponse(
                    answer=f"I couldn’t start activity tracking: {started.message}",
                    provider_used="activity:start-failed",
                    trace_id=trace_id,
                    evidence=[],
                    debug_steps=self.trace_service.list_events(trace_id),
                    conversation_id=conversation_id,
                    warnings=[],
                )
            self.trace_service.emit(trace_id, "RECORDING_STARTED", "Activity recording started from chat", {"session_id": started.session.id})
            answer = (
                f"I started tracking your desktop activity for {started.session.requested_duration_seconds} seconds. "
                "Keep working normally and I’ll provide a step-by-step summary when the session finishes."
            )
            return ChatResponse(
                answer=answer,
                provider_used="activity:started",
                trace_id=trace_id,
                evidence=[],
                debug_steps=self.trace_service.list_events(trace_id),
                conversation_id=conversation_id,
                warnings=[],
            )

        if action == "stop":
            stopped = self.activity_recording_service.stop()
            if not stopped.ok or stopped.summary is None:
                return ChatResponse(
                    answer="There isn’t an active recording to stop right now.",
                    provider_used="activity:no-active-session",
                    trace_id=trace_id,
                    evidence=[],
                    debug_steps=self.trace_service.list_events(trace_id),
                    conversation_id=conversation_id,
                    warnings=[],
                )
            evidence = [
                EvidenceItem(id=stopped.summary.session_id, label="[Activity Recording]", kind="source", quote=stopped.summary.summary_text[:220], locator=stopped.summary.session_id, score=1.0)
            ]
            return ChatResponse(
                answer=self._format_activity_summary(stopped.summary),
                provider_used=stopped.summary.provider_used,
                trace_id=trace_id,
                evidence=evidence,
                debug_steps=self.trace_service.list_events(trace_id),
                conversation_id=conversation_id,
                warnings=stopped.summary.warnings,
            )

        if action == "status":
            status = self.activity_recording_service.current()
            if status.current and status.current.status == "active":
                remaining = 0
                if status.current.ends_at:
                    remaining = max(0, int((status.current.ends_at - status.current.started_at).total_seconds()) - int((datetime.now(timezone.utc) - status.current.started_at).total_seconds()))
                answer = (
                    f"Recording is active. {status.current.frames_captured} frames captured so far, "
                    f"{remaining} seconds remaining, and the last visible window was {status.current.last_window_title or 'unknown'}."
                )
                return ChatResponse(answer=answer, provider_used="activity:status", trace_id=trace_id, evidence=[], debug_steps=self.trace_service.list_events(trace_id), conversation_id=conversation_id, warnings=[])
            return ChatResponse(
                answer="I’m not currently tracking your activity. I only keep temporal history when you explicitly start a recording session.",
                provider_used="activity:status-idle",
                trace_id=trace_id,
                evidence=[],
                debug_steps=self.trace_service.list_events(trace_id),
                conversation_id=conversation_id,
                warnings=[],
            )

        if action == "last":
            summary = self.activity_recording_service.summarize()
            if summary is None:
                return ChatResponse(
                    answer="I don’t have a previous recording session to summarize. Right now I only know the current screen unless you start tracking first.",
                    provider_used="activity:no-history",
                    trace_id=trace_id,
                    evidence=[],
                    debug_steps=self.trace_service.list_events(trace_id),
                    conversation_id=conversation_id,
                    warnings=[],
                )
            evidence = [EvidenceItem(id=summary.session_id, label="[Activity Recording]", kind="source", quote=summary.summary_text[:220], locator=summary.session_id, score=1.0)]
            return ChatResponse(
                answer=self._format_activity_summary(summary),
                provider_used=summary.provider_used,
                trace_id=trace_id,
                evidence=evidence,
                debug_steps=self.trace_service.list_events(trace_id),
                conversation_id=conversation_id,
                warnings=summary.warnings,
            )

        return ChatResponse(
            answer="I’m not currently tracking your activity.",
            provider_used="activity:noop",
            trace_id=trace_id,
            evidence=[],
            debug_steps=self.trace_service.list_events(trace_id),
            conversation_id=conversation_id,
            warnings=warnings,
        )

    def _format_activity_summary(self, summary) -> str:
        body = [summary.summary_text.strip()]
        if summary.steps:
            body.append("")
            body.extend(summary.steps)
        return "\n".join(line for line in body if line is not None).strip()

    def _format_guided_task_started(self, status) -> str:
        if not status or not status.session or not status.plan or not status.current_step:
            return "I started Guided Task mode, but I could not build the first step clearly enough yet. Try Re-scan or switch to the correct page."
        lines = [
            f"Guided Task: {status.plan.title}",
            f"Step {status.current_step.order_index + 1} of {status.plan.estimated_steps}: {status.current_step.instruction_text}",
        ]
        if status.latest_grounding and status.latest_grounding.success and status.latest_grounding.target_label:
            lines.append(f"I am pointing at: {status.latest_grounding.target_label}.")
        elif status.latest_grounding and not status.latest_grounding.success:
            lines.append(status.latest_grounding.reason)
        if status.recovery_options:
            lines.append("If needed, use Re-scan, Mark done, or I can't find it.")
        return "\n".join(lines)
