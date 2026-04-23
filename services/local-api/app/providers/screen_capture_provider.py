from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageGrab

from app.models.contracts import RegionSelection, ScreenCaptureRef
from app.providers.interfaces import ScreenCaptureProvider


class PillowScreenCaptureProvider(ScreenCaptureProvider):
    def __init__(self, data_dir: Path) -> None:
        self.capture_dir = data_dir / "captures"
        self.capture_dir.mkdir(parents=True, exist_ok=True)

    def capture_current_screen(self) -> ScreenCaptureRef:
        capture_id = str(uuid4())
        capture_path = self.capture_dir / f"{capture_id}.png"
        mode = "native"
        try:
            # Capture the primary screen by default so it matches the region-overlay UX.
            image = ImageGrab.grab()
        except Exception:
            image = self._build_simulated_capture()
            mode = "simulated"
        image.save(capture_path)
        return ScreenCaptureRef(
            id=capture_id,
            path=str(capture_path),
            width=image.width,
            height=image.height,
            mode=mode,
            captured_at=datetime.now(timezone.utc),
        )

    def crop_region(self, capture: ScreenCaptureRef, selection: RegionSelection) -> ScreenCaptureRef:
        source_path = Path(capture.path)
        with Image.open(source_path) as image:
            x2 = min(selection.x + selection.width, image.width)
            y2 = min(selection.y + selection.height, image.height)
            cropped = image.crop((selection.x, selection.y, x2, y2))
            capture_id = str(uuid4())
            capture_path = self.capture_dir / f"{capture_id}.png"
            cropped.save(capture_path)
        return ScreenCaptureRef(
            id=capture_id,
            path=str(capture_path),
            width=max(1, x2 - selection.x),
            height=max(1, y2 - selection.y),
            mode=capture.mode,
            captured_at=datetime.now(timezone.utc),
        )

    def _build_simulated_capture(self) -> Image.Image:
        image = Image.new("RGB", (1280, 720), color=(245, 246, 250))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((80, 60, 1200, 660), radius=24, outline=(90, 105, 125), width=3)
        draw.rectangle((120, 110, 760, 150), fill=(232, 237, 244))
        draw.rectangle((120, 190, 1120, 240), fill=(223, 234, 250))
        draw.rectangle((120, 270, 1120, 320), fill=(235, 241, 248))
        draw.rectangle((120, 350, 980, 540), fill=(255, 255, 255), outline=(180, 190, 200))
        draw.text((130, 80), "Genie simulated screen capture", fill=(30, 40, 55))
        draw.text((130, 205), "This environment could not capture the native desktop.", fill=(40, 50, 70))
        draw.text((130, 230), "Use this simulated capture to test screen and region flows.", fill=(40, 50, 70))
        return image


class MockRegionSelectionProvider:
    def normalize(self, selection: RegionSelection, max_width: int, max_height: int) -> RegionSelection:
        x = max(0, min(selection.x, max_width - 1))
        y = max(0, min(selection.y, max_height - 1))
        width = max(1, min(selection.width, max_width - x))
        height = max(1, min(selection.height, max_height - y))
        return RegionSelection(x=x, y=y, width=width, height=height)
