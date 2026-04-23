from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import logging
from pydantic import BaseModel, Field


class DemoProviderFile(BaseModel):
    provider_type: Literal["google_gemini_openai_compatible"] = "google_gemini_openai_compatible"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    api_key: str | None = None
    api_key_b64: str | None = None
    model: str = "gemma-4-26b-a4b-it"
    timeout_ms: int = 60000
    supports_images: bool = True
    supports_audio_input: bool = False
    notes: str | None = None


class DemoResolvedConfig(BaseModel):
    source: Literal["bundled_file", "remote_file", "offline_mock"]
    provider_type: str
    base_url: str
    model: str
    timeout_ms: int
    supports_images: bool
    supports_audio_input: bool
    api_key_present: bool = Field(default=False, description="True if an API key was resolved (never expose the key).")


@dataclass(frozen=True)
class DemoResolverResult:
    status: DemoResolvedConfig
    api_key: str | None


def _decode_api_key(payload: DemoProviderFile) -> str | None:
    if payload.api_key_b64:
        try:
            return base64.b64decode(payload.api_key_b64.encode("utf-8")).decode("utf-8").strip() or None
        except Exception:
            return None
    if payload.api_key and payload.api_key.startswith("b64:"):
        try:
            raw = payload.api_key.removeprefix("b64:")
            return base64.b64decode(raw.encode("utf-8")).decode("utf-8").strip() or None
        except Exception:
            return None
    return payload.api_key.strip() if payload.api_key else None


def _load_demo_file(path: Path) -> tuple[DemoProviderFile | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return None, None
    try:
        data = json.loads(text)
        return DemoProviderFile(**data), None
    except Exception:
        # Plain text fallback: treat as API key only.
        payload = DemoProviderFile(api_key=text)
        return payload, None


class DemoCredentialResolver:
    """
    Resolves demo provider config using:
    1) bundled local file
    2) optional remote single-file URL
    3) offline/mock fallback
    """

    def __init__(self, *, resources_dir: Path, bundled_relative_path: str = "private/demo-provider.json") -> None:
        self.resources_dir = resources_dir
        self.bundled_relative_path = bundled_relative_path
        self._cached_remote: DemoResolverResult | None = None
        self._log = logging.getLogger("genie.demo_resolver")

    def bundled_path(self) -> Path:
        return self.resources_dir / self.bundled_relative_path

    async def resolve(
        self,
        *,
        demo_source_order: list[str] | None,
        remote_demo_file_url: str | None,
        remote_demo_file_format: str | None,
        default_base_url: str,
        default_model: str,
        default_timeout_ms: int,
    ) -> DemoResolverResult:
        source_order = demo_source_order or ["bundled_file", "remote_file", "offline_mock"]
        remote_url = (remote_demo_file_url or "").strip()
        remote_format = (remote_demo_file_format or "json").strip().lower()

        for source in source_order:
            if source == "bundled_file":
                path = self.bundled_path()
                if path.exists():
                    payload, _error = _load_demo_file(path)
                    if payload:
                        api_key = _decode_api_key(payload)
                        self._log.info(
                            "demo provider resolved via bundled file (present=%s, supports_images=%s)",
                            bool(api_key),
                            payload.supports_images,
                        )
                        return DemoResolverResult(
                            status=DemoResolvedConfig(
                                source="bundled_file",
                                provider_type=payload.provider_type,
                                base_url=(payload.base_url or default_base_url).rstrip("/") + "/",
                                model=payload.model or default_model,
                                timeout_ms=payload.timeout_ms or default_timeout_ms,
                                supports_images=payload.supports_images,
                                supports_audio_input=payload.supports_audio_input,
                                api_key_present=bool(api_key),
                            ),
                            api_key=api_key,
                        )

            if source == "remote_file":
                if not remote_url:
                    continue
                if self._cached_remote is not None:
                    self._log.info("demo provider resolved via cached remote file")
                    return self._cached_remote
                fetched = await self._fetch_remote(
                    remote_url,
                    remote_format=remote_format,
                    default_base_url=default_base_url,
                    default_model=default_model,
                    default_timeout_ms=default_timeout_ms,
                )
                if fetched is not None:
                    self._cached_remote = fetched
                    self._log.info(
                        "demo provider resolved via remote file (present=%s, supports_images=%s)",
                        fetched.status.api_key_present,
                        fetched.status.supports_images,
                    )
                    return fetched

            if source == "offline_mock":
                self._log.info("demo provider using offline mock fallback")
                return DemoResolverResult(
                    status=DemoResolvedConfig(
                        source="offline_mock",
                        provider_type="offline_mock",
                        base_url=default_base_url.rstrip("/") + "/",
                        model=default_model,
                        timeout_ms=default_timeout_ms,
                        supports_images=True,
                        supports_audio_input=False,
                        api_key_present=False,
                    ),
                    api_key=None,
                )

        # Guaranteed fallback.
        self._log.info("demo provider using offline mock fallback (no sources succeeded)")
        return DemoResolverResult(
            status=DemoResolvedConfig(
                source="offline_mock",
                provider_type="offline_mock",
                base_url=default_base_url.rstrip("/") + "/",
                model=default_model,
                timeout_ms=default_timeout_ms,
                supports_images=True,
                supports_audio_input=False,
                api_key_present=False,
            ),
            api_key=None,
        )

    async def _fetch_remote(
        self,
        url: str,
        *,
        remote_format: str,
        default_base_url: str,
        default_model: str,
        default_timeout_ms: int,
    ) -> DemoResolverResult | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                body = (resp.text or "").strip()
        except Exception:
            return None

        try:
            if remote_format == "text":
                payload = DemoProviderFile(api_key=body)
            else:
                payload = DemoProviderFile(**json.loads(body))
        except Exception:
            return None

        api_key = _decode_api_key(payload)
        return DemoResolverResult(
            status=DemoResolvedConfig(
                source="remote_file",
                provider_type=payload.provider_type,
                base_url=(payload.base_url or default_base_url).rstrip("/") + "/",
                model=payload.model or default_model,
                timeout_ms=payload.timeout_ms or default_timeout_ms,
                supports_images=payload.supports_images,
                supports_audio_input=payload.supports_audio_input,
                api_key_present=bool(api_key),
            ),
            api_key=api_key,
        )
