from __future__ import annotations

from pathlib import Path

from app.models.contracts import ScreenContext
from app.providers.interfaces import OCRProvider, ScreenCaptureProvider


class ScreenContextService:
    def __init__(self, capture_provider: ScreenCaptureProvider, ocr_provider: OCRProvider) -> None:
        self.capture_provider = capture_provider
        self.ocr_provider = ocr_provider
        self._last_capture = None

    def capture(self) -> ScreenContext:
        capture = self.capture_provider.capture_current_screen()
        ocr_text = self.ocr_provider.extract_text(Path(capture.path))
        capture.ocr_text = ocr_text or None
        capture.summary = f"{capture.mode.capitalize()} screen capture {capture.width}x{capture.height}."
        self._last_capture = capture
        return ScreenContext(capture=capture, text=ocr_text or capture.summary, summary=capture.summary)

    def get_last_capture(self):
        return self._last_capture

