from __future__ import annotations

import ctypes
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from app.models.contracts import ActivityEvent, ActivityFrameRef, ActivitySummary, ActivityTimeline
from app.providers.interfaces import OCRProvider, ScreenCaptureProvider


def sanitize_visible_text(text: str | None) -> str:
    cleaned = " ".join((text or "").split())
    lowered = cleaned.lower()
    redaction_terms = ("password", "api key", "token", "secret", "bearer")
    if any(term in lowered for term in redaction_terms):
        return "[redacted-sensitive-text]"
    return cleaned[:240]


class DesktopEventCollector:
    def get_active_window_title(self) -> str | None:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            return title or None
        except Exception:
            return None


class ScreenFrameSampler:
    def __init__(self, capture_provider: ScreenCaptureProvider, ocr_provider: OCRProvider, event_collector: DesktopEventCollector) -> None:
        self.capture_provider = capture_provider
        self.ocr_provider = ocr_provider
        self.event_collector = event_collector

    def sample(self) -> tuple[ActivityFrameRef, list[ActivityEvent]]:
        capture = self.capture_provider.capture_current_screen()
        image_path = Path(capture.path)
        ocr_text = sanitize_visible_text(self.ocr_provider.extract_text(image_path))
        window_title = sanitize_visible_text(self.event_collector.get_active_window_title())
        dedupe_key = self._dedupe_key(image_path, window_title)
        frame = ActivityFrameRef(
            id=str(uuid4()),
            capture=capture,
            timestamp=capture.captured_at,
            summary=window_title or ocr_text or "Screen sampled",
            ocr_text=ocr_text or None,
            window_title=window_title or None,
            dedupe_key=dedupe_key,
        )
        events = [
            ActivityEvent(
                id=str(uuid4()),
                timestamp=capture.captured_at,
                type="frame_sampled",
                description="Captured a sampled desktop frame.",
                window_title=window_title or None,
                metadata={"capture_id": capture.id, "mode": capture.mode},
            )
        ]
        return frame, events

    def _dedupe_key(self, image_path: Path, window_title: str | None) -> str:
        try:
            with Image.open(image_path) as image:
                image.thumbnail((64, 64))
                digest = hashlib.md5(image.tobytes(), usedforsecurity=False).hexdigest()
        except Exception:
            digest = image_path.name
        return f"{window_title or 'windowless'}:{digest}"


class SessionArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "activity"
        self.root.mkdir(parents=True, exist_ok=True)

    def create_session_dir(self, session_id: str) -> Path:
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_timeline(self, session_id: str, timeline: ActivityTimeline) -> None:
        session_dir = self.create_session_dir(session_id)
        (session_dir / "timeline.json").write_text(timeline.model_dump_json(indent=2), encoding="utf-8")

    def save_summary(self, session_id: str, summary: ActivitySummary) -> None:
        session_dir = self.create_session_dir(session_id)
        (session_dir / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    def load_summary(self, session_id: str) -> ActivitySummary | None:
        path = self.root / session_id / "summary.json"
        if not path.exists():
            return None
        return ActivitySummary(**json.loads(path.read_text(encoding="utf-8")))

    def load_timeline(self, session_id: str) -> ActivityTimeline | None:
        path = self.root / session_id / "timeline.json"
        if not path.exists():
            return None
        return ActivityTimeline(**json.loads(path.read_text(encoding="utf-8")))
