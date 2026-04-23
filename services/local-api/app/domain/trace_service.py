from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.contracts import TraceEvent
from app.providers.interfaces import TraceLogger


class TraceService:
    def __init__(self, logger: TraceLogger) -> None:
        self.logger = logger

    def new_trace_id(self) -> str:
        return str(uuid4())

    def emit(self, trace_id: str, event_type: str, message: str, metadata: dict | None = None, duration_ms: float | None = None) -> None:
        event = TraceEvent(
            id=str(uuid4()),
            trace_id=trace_id,
            type=event_type,
            message=message,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
        self.logger.emit(event)

    def list_events(self, trace_id: str) -> list[TraceEvent]:
        return self.logger.list_events(trace_id)

