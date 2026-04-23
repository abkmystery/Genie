from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.activity_timeline import ActivitySummarizer, TimelineAssembler
from app.domain.trace_service import TraceService
from app.models.contracts import (
    ActivityEvent,
    ActivitySessionRecord,
    ActivityStatusResponse,
    ActivitySummary,
    StartActivityRecordingResponse,
    StopActivityRecordingResponse,
)
from app.providers.activity_capture import ScreenFrameSampler, SessionArtifactStore


_DURATION_RE = re.compile(r"(?P<count>\d+)\s*(?P<unit>second|seconds|sec|secs|minute|minutes|min|mins)")


@dataclass
class _ManagedSession:
    record: ActivitySessionRecord
    trace_id: str
    stop_event: threading.Event = field(default_factory=threading.Event)
    frames: list = field(default_factory=list)
    events: list[ActivityEvent] = field(default_factory=list)
    summary: ActivitySummary | None = None
    thread: threading.Thread | None = None
    surfaced: bool = False


def parse_activity_prompt(prompt: str) -> dict[str, object] | None:
    lowered = prompt.lower().strip()
    if any(token in lowered for token in ("stop tracking", "stop recording", "stop watching")):
        return {"intent": "stop"}
    if any(token in lowered for token in ("current recording", "recording status", "are you tracking", "what are you tracking")):
        return {"intent": "status"}
    if any(token in lowered for token in ("last recording", "last tracked", "summarize last recording", "last minute")):
        return {"intent": "last"}
    if any(token in lowered for token in ("track my actions", "watch what i do", "record steps", "track what i do", "record my actions")):
        seconds = 60
        match = _DURATION_RE.search(lowered)
        if match:
            count = int(match.group("count"))
            unit = match.group("unit")
            seconds = count * 60 if unit.startswith("min") else count
        return {"intent": "start", "duration_seconds": seconds}
    return None


class ActivitySessionManager:
    def __init__(
        self,
        sampler: ScreenFrameSampler,
        artifact_store: SessionArtifactStore,
        timeline_assembler: TimelineAssembler,
        summarizer: ActivitySummarizer,
        trace_service: TraceService,
    ) -> None:
        self.sampler = sampler
        self.artifact_store = artifact_store
        self.timeline_assembler = timeline_assembler
        self.summarizer = summarizer
        self.trace_service = trace_service
        self._lock = threading.Lock()
        self._current: _ManagedSession | None = None
        self._last: _ManagedSession | None = None

    def start(self, *, duration_seconds: int, sampling_hz: float) -> StartActivityRecordingResponse:
        with self._lock:
            if self._current and self._current.record.status == "active":
                return StartActivityRecordingResponse(ok=False, session=self._current.record, message="A recording session is already active.")

            now = datetime.now(timezone.utc)
            session = _ManagedSession(
                record=ActivitySessionRecord(
                    id=str(uuid4()),
                    status="active",
                    started_at=now,
                    requested_duration_seconds=duration_seconds,
                    sampling_hz=sampling_hz,
                    ends_at=now + timedelta(seconds=duration_seconds),
                ),
                trace_id=self.trace_service.new_trace_id(),
            )
            session.thread = threading.Thread(target=self._run_session, args=(session,), daemon=True, name=f"activity-{session.record.id}")
            self._current = session
            session.thread.start()
            return StartActivityRecordingResponse(ok=True, session=session.record, message="Activity recording started.")

    def stop(self, session_id: str | None = None) -> StopActivityRecordingResponse:
        with self._lock:
            session = self._current
        if session is None or session.record.status != "active":
            return StopActivityRecordingResponse(ok=False, session=None, summary=self._last.summary if self._last else None, message="No active recording session is running.")
        if session_id and session.record.id != session_id:
            return StopActivityRecordingResponse(ok=False, session=session.record, summary=None, message="The requested recording session is not the active session.")

        session.stop_event.set()
        if session.thread:
            session.thread.join(timeout=max(3, session.record.requested_duration_seconds + 5))
        return StopActivityRecordingResponse(
            ok=session.summary is not None,
            session=session.record,
            summary=session.summary,
            message="Activity recording stopped and summarized." if session.summary else "Activity recording stopped.",
        )

    def current_status(self) -> ActivityStatusResponse:
        with self._lock:
            current = self._current.record if self._current else None
            last = self._last.record if self._last else None
            summary = self._last.summary if self._last else None
        return ActivityStatusResponse(current=current, last=last, summary=summary)

    def last_status(self) -> ActivityStatusResponse:
        with self._lock:
            last = self._last.record if self._last else None
            summary = self._last.summary if self._last else None
        return ActivityStatusResponse(current=None, last=last, summary=summary)

    def summarize(self, session_id: str | None = None) -> ActivitySummary | None:
        with self._lock:
            if session_id and self._last and self._last.record.id == session_id:
                return self._last.summary
            if not session_id and self._last:
                return self._last.summary
            return None

    def consume_unsurfaced_summary(self) -> ActivitySummary | None:
        with self._lock:
            if not self._last or self._last.surfaced or self._last.summary is None:
                return None
            self._last.surfaced = True
            return self._last.summary

    def _run_session(self, session: _ManagedSession) -> None:
        self.trace_service.emit(session.trace_id, "RECORDING_STARTED", "Activity recording started", {"session_id": session.record.id})
        session.events.append(
            ActivityEvent(
                id=str(uuid4()),
                timestamp=session.record.started_at,
                type="recording_started",
                description="Recording started.",
            )
        )
        interval = max(0.25, 1 / max(0.1, session.record.sampling_hz))
        previous_window: str | None = None

        try:
            while not session.stop_event.is_set():
                now = datetime.now(timezone.utc)
                if session.record.ends_at and now >= session.record.ends_at:
                    break

                frame, frame_events = self.sampler.sample()
                session.frames.append(frame)
                session.events.extend(frame_events)
                session.record.frames_captured = len(session.frames)
                session.record.last_window_title = frame.window_title
                if frame.window_title and frame.window_title != previous_window:
                    previous_window = frame.window_title
                    session.events.append(
                        ActivityEvent(
                            id=str(uuid4()),
                            timestamp=frame.timestamp,
                            type="window_changed",
                            description=f"Focused on \"{frame.window_title}\".",
                            window_title=frame.window_title,
                        )
                    )
                self.trace_service.emit(
                    session.trace_id,
                    "RECORDING_FRAME_CAPTURED",
                    "Activity recording captured a frame",
                    {"session_id": session.record.id, "frames_captured": session.record.frames_captured, "window_title": frame.window_title},
                )
                time.sleep(interval)

            session.record.ended_at = datetime.now(timezone.utc)
            session.record.status = "stopped" if session.stop_event.is_set() else "completed"
            session.events.append(
                ActivityEvent(
                    id=str(uuid4()),
                    timestamp=session.record.ended_at,
                    type="recording_stopped",
                    description="Recording stopped.",
                    window_title=session.record.last_window_title,
                )
            )
            timeline = self.timeline_assembler.build(session.record, frames=session.frames, events=session.events)
            self.artifact_store.save_timeline(session.record.id, timeline)
            session.summary = asyncio.run(self.summarizer.summarize(timeline))
            session.record.summary_available = session.summary is not None
            if session.summary:
                self.artifact_store.save_summary(session.record.id, session.summary)
                self.trace_service.emit(
                    session.trace_id,
                    "SUMMARY_GENERATED",
                    "Activity recording summary generated",
                    {"session_id": session.record.id, "steps": len(session.summary.steps)},
                )
            self.trace_service.emit(
                session.trace_id,
                "RECORDING_STOPPED",
                "Activity recording stopped",
                {"session_id": session.record.id, "status": session.record.status},
            )
        except Exception as exc:
            session.record.status = "failed"
            session.record.ended_at = datetime.now(timezone.utc)
            session.record.last_error = str(exc)
            session.events.append(
                ActivityEvent(
                    id=str(uuid4()),
                    timestamp=session.record.ended_at,
                    type="error",
                    description=f"Recording failed: {exc}",
                )
            )
            self.trace_service.emit(
                session.trace_id,
                "ERROR_RAISED",
                "Activity recording failed",
                {"session_id": session.record.id, "error": str(exc)},
            )
        finally:
            with self._lock:
                self._last = session
                self._current = None


class ActivityRecordingService:
    def __init__(self, session_manager: ActivitySessionManager) -> None:
        self.session_manager = session_manager

    def start(self, *, duration_seconds: int, sampling_hz: float) -> StartActivityRecordingResponse:
        return self.session_manager.start(duration_seconds=duration_seconds, sampling_hz=sampling_hz)

    def stop(self, session_id: str | None = None) -> StopActivityRecordingResponse:
        return self.session_manager.stop(session_id=session_id)

    def current(self) -> ActivityStatusResponse:
        return self.session_manager.current_status()

    def last(self) -> ActivityStatusResponse:
        return self.session_manager.last_status()

    def summarize(self, session_id: str | None = None) -> ActivitySummary | None:
        return self.session_manager.summarize(session_id=session_id)

    def consume_unsurfaced_summary(self) -> ActivitySummary | None:
        return self.session_manager.consume_unsurfaced_summary()
