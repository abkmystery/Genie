from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.providers.interfaces import OCRProvider

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None


class OptionalTesseractOCRProvider(OCRProvider):
    def extract_text(self, image_path: Path) -> str:
        if pytesseract is None:
            return ""
        try:
            return pytesseract.image_to_string(Image.open(image_path)).strip()
        except Exception:
            return ""


class MetadataOCRProvider(OCRProvider):
    def extract_text(self, image_path: Path) -> str:
        try:
            with Image.open(image_path):
                return ""
        except Exception:
            return ""


class FallbackOCRProvider(OCRProvider):
    """Try a primary OCR engine first, then fall back to lightweight metadata OCR."""

    def __init__(self, primary: OCRProvider, fallback: OCRProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def extract_text(self, image_path: Path) -> str:
        return self.primary.extract_text(image_path) or self.fallback.extract_text(image_path)
