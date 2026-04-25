from __future__ import annotations

from typing import Any

import httpx

from app.models.contracts import EvidenceItem, GatewayChatRequest, GatewayChatResponse, ProviderConfig, RegionContext, ScreenContext
from app.providers.interfaces import ModelProvider
from app.providers.model_fallback import fallback_grounded_answer
from app.providers.model_payloads import build_openai_compatible_payload, encode_image_data_url
from app.providers.openai_compatible import OpenAICompatibleClient


class MockModelProvider(ModelProvider):
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
        return GatewayChatResponse(
            answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
            provider_used=f"{profile.id}:mock",
        )


class HttpModelProvider(ModelProvider):
    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}

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
        endpoint = profile.endpoint_override or profile.backend_base_url
        payload = GatewayChatRequest(
            prompt=prompt,
            profile_id=profile.id,
            evidence=evidence,
            screen_summary=screen_context.summary if screen_context else None,
            region_summary=region_context.summary if region_context else None,
            screen_image_data_url=encode_image_data_url(screen_context.capture.path) if screen_context else None,
            region_image_data_url=encode_image_data_url(region_context.capture.path) if region_context else None,
            audio_base64=audio_base64,
            audio_format=audio_format,
        )
        headers = {}
        token = self.credentials.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=profile.timeout_ms / 1000) as client:
                response = await client.post(endpoint.rstrip("/") + "/v1/chat", json=payload.model_dump(mode="json"), headers=headers)
                response.raise_for_status()
                data = response.json()
                return GatewayChatResponse(**data)
        except Exception:
            return GatewayChatResponse(
                answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                provider_used=f"{profile.id}:http-fallback",
            )


class GatewayModelProvider(HttpModelProvider):
    pass


class OpenAICompatibleHttpModelProvider(ModelProvider):
    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}

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
        base_url = (profile.endpoint_override or profile.backend_base_url or "").rstrip("/")
        token = (self.credentials.get("token") or "").strip()
        if not base_url:
            if profile.id == "demo":
                return GatewayChatResponse(
                    answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                    provider_used=f"{profile.id}:openai-fallback",
                )
            return GatewayChatResponse(
                answer=_provider_error_answer(
                    profile=profile,
                    base_url=base_url,
                    error="No endpoint is configured for this profile.",
                ),
                provider_used=f"{profile.id}:openai-config-error",
            )

        payload = build_openai_compatible_payload(
            model=profile.model_name,
            prompt=prompt,
            evidence=evidence,
            screen_context=screen_context,
            region_context=region_context,
            supports_images=profile.capabilities.supports_screen_input,
            supports_audio_input=bool(audio_base64 and audio_format),
            audio_base64=audio_base64,
            audio_format=audio_format,
            additional_image_paths=additional_image_paths,
        )

        client = OpenAICompatibleClient(base_url=base_url, bearer_token=token, timeout_s=max(5, profile.timeout_ms / 1000))
        try:
            answer = await client.chat_completions(payload)
            return GatewayChatResponse(answer=answer or "(empty response)", provider_used=f"{profile.id}:openai-compatible")
        except Exception as exc:
            if profile.id == "demo":
                return GatewayChatResponse(
                    answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                    provider_used=f"{profile.id}:openai-fallback",
                )
            return GatewayChatResponse(
                answer=_provider_error_answer(profile=profile, base_url=base_url, error=_describe_provider_error(exc)),
                provider_used=f"{profile.id}:openai-error",
            )


class DemoModelProvider(ModelProvider):
    def __init__(self, *, resolve_demo_config) -> None:
        self._resolve_demo_config = resolve_demo_config

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
        resolved = await self._resolve_demo_config(profile)
        status = resolved.status
        if not resolved.api_key:
            return GatewayChatResponse(
                answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                provider_used="demo:offline-mock",
            )

        payload = build_openai_compatible_payload(
            model=status.model,
            prompt=prompt,
            evidence=evidence,
            screen_context=screen_context,
            region_context=region_context,
            supports_images=status.supports_images,
            supports_audio_input=status.supports_audio_input,
            audio_base64=audio_base64,
            audio_format=audio_format,
            additional_image_paths=additional_image_paths,
        )

        client = OpenAICompatibleClient(
            base_url=status.base_url,
            bearer_token=resolved.api_key,
            timeout_s=max(5, status.timeout_ms / 1000),
        )
        try:
            answer = await client.chat_completions(payload)
        except Exception:
            return GatewayChatResponse(
                answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                provider_used="demo:offline-mock",
            )

        return GatewayChatResponse(answer=answer or "(empty response)", provider_used=f"demo:{status.source}:{status.model}")


def _describe_provider_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response_text = (exc.response.text or "").strip()
        if len(response_text) > 320:
            response_text = f"{response_text[:320]}..."
        suffix = f" Response: {response_text}" if response_text else ""
        return f"HTTP {exc.response.status_code} from model endpoint.{suffix}"
    return f"{exc.__class__.__name__}: {exc}"


def _provider_error_answer(*, profile: ProviderConfig, base_url: str, error: str) -> str:
    profile_name = profile.display_name or profile.id
    endpoint_label = base_url or "(not configured)"
    return (
        f"I could not reach the {profile_name} model endpoint, so I can't answer with the local model yet.\n\n"
        f"Endpoint: {endpoint_label}\n"
        f"Model: {profile.model_name or '(not configured)'}\n"
        f"Problem: {error}\n\n"
        "Please make sure the local model server is running, the endpoint points to its OpenAI-compatible base URL, "
        "and the selected model is loaded. I did not use the generic screen fallback for this response."
    )
