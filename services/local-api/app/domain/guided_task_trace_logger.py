from __future__ import annotations

from app.domain.trace_service import TraceService


class GuidedTaskTraceLogger:
    def __init__(self, trace_service: TraceService) -> None:
        self.trace_service = trace_service

    def emit(self, trace_id: str, event_type: str, message: str, metadata: dict | None = None) -> None:
        self.trace_service.emit(trace_id, event_type, message, metadata or {})
