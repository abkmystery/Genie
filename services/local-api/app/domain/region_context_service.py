from __future__ import annotations

from pathlib import Path

from app.models.contracts import RegionContext, RegionSelection
from app.providers.interfaces import OCRProvider, RegionSelectionProvider, ScreenCaptureProvider


class RegionContextService:
    def __init__(
        self,
        capture_provider: ScreenCaptureProvider,
        selection_provider: RegionSelectionProvider,
        ocr_provider: OCRProvider,
    ) -> None:
        self.capture_provider = capture_provider
        self.selection_provider = selection_provider
        self.ocr_provider = ocr_provider

    def capture_region(self, base_capture, selection: RegionSelection) -> RegionContext:
        normalized = self.selection_provider.normalize(selection, base_capture.width, base_capture.height)
        capture = self.capture_provider.crop_region(base_capture, normalized)
        ocr_text = self.ocr_provider.extract_text(Path(capture.path))
        capture.ocr_text = ocr_text or None
        capture.summary = f"Region capture {capture.width}x{capture.height} from selection ({normalized.x},{normalized.y})."
        return RegionContext(capture=capture, selection=normalized, text=ocr_text or capture.summary, summary=capture.summary)

