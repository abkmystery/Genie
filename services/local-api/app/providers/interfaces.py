from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.models.contracts import (
    EvidenceItem,
    GatewayChatRequest,
    GatewayChatResponse,
    ProviderConfig,
    RegionContext,
    RegionSelection,
    ScreenCaptureRef,
    ScreenContext,
    SourceChunk,
    SourceRecord,
    TraceEvent,
)


class ModelProvider(ABC):
    @abstractmethod
    async def answer(
        self,
        prompt: str,
        profile: ProviderConfig,
        evidence: list[EvidenceItem],
        screen_context: ScreenContext | None = None,
        region_context: RegionContext | None = None,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        additional_image_paths: list[str] | None = None,
    ) -> GatewayChatResponse:
        raise NotImplementedError


class ScreenCaptureProvider(ABC):
    @abstractmethod
    def capture_current_screen(self) -> ScreenCaptureRef:
        raise NotImplementedError

    @abstractmethod
    def crop_region(self, capture: ScreenCaptureRef, selection: RegionSelection) -> ScreenCaptureRef:
        raise NotImplementedError


class RegionSelectionProvider(ABC):
    @abstractmethod
    def normalize(self, selection: RegionSelection, max_width: int, max_height: int) -> RegionSelection:
        raise NotImplementedError


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def diagnostics(self) -> dict[str, Any]:
        raise NotImplementedError


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def speak(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def diagnostics(self) -> dict[str, Any]:
        raise NotImplementedError


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_path: Path) -> str:
        raise NotImplementedError


class SourceParser(ABC):
    @abstractmethod
    def supports(self, path: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse(self, path: Path) -> list[SourceChunk]:
        raise NotImplementedError


class SourceRepository(ABC):
    @abstractmethod
    def save_source(self, source: SourceRecord, chunks: list[SourceChunk]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_sources(self) -> list[SourceRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_source(self, source_id: str) -> SourceRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_chunks(self, source_ids: list[str] | None = None) -> list[SourceChunk]:
        raise NotImplementedError

    @abstractmethod
    def delete_source(self, source_id: str) -> None:
        raise NotImplementedError


class RetrievalEngine(ABC):
    @abstractmethod
    def retrieve(self, prompt: str, source_ids: list[str] | None = None, limit: int = 6) -> list[tuple[SourceChunk, float]]:
        raise NotImplementedError


class TraceLogger(ABC):
    @abstractmethod
    def emit(self, event: TraceEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, trace_id: str) -> list[TraceEvent]:
        raise NotImplementedError


class ProfileConfigLoader(ABC):
    @abstractmethod
    def list_profiles(self) -> list[ProviderConfig]:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, profile_id: str) -> ProviderConfig:
        raise NotImplementedError


class SecureCredentialStore(ABC):
    @abstractmethod
    def save(self, provider_id: str, secret_payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, provider_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, provider_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def has(self, provider_id: str) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def mode(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def warning(self) -> str | None:
        raise NotImplementedError


class WakeWordProvider(ABC):
    @abstractmethod
    def is_enabled(self) -> bool:
        raise NotImplementedError
