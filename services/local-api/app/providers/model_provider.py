from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from app.models.contracts import EvidenceItem, GatewayChatRequest, GatewayChatResponse, ProviderConfig, ProviderDiagnostics, RegionContext, ScreenContext
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
            provider_diagnostics=ProviderDiagnostics(
                provider_status="fallback_mock",
                provider_source="mock",
                live_model_name=profile.model_name,
                fallback_reason="Mock provider selected.",
            ),
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
            started = perf_counter()
            async with httpx.AsyncClient(timeout=profile.timeout_ms / 1000) as client:
                response = await client.post(endpoint.rstrip("/") + "/v1/chat", json=payload.model_dump(mode="json"), headers=headers)
                response.raise_for_status()
                data = response.json()
                parsed = GatewayChatResponse(**data)
                if parsed.provider_diagnostics is None:
                    parsed.provider_diagnostics = ProviderDiagnostics(
                        provider_status="live_gemma" if "gemma" in parsed.provider_used.lower() else "unknown",
                        provider_source=endpoint,
                        live_model_name=profile.model_name,
                        latency_ms=round((perf_counter() - started) * 1000, 2),
                    )
                return parsed
        except Exception as exc:
            return GatewayChatResponse(
                answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                provider_used=f"{profile.id}:http-fallback",
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="fallback_mock",
                    provider_source=endpoint,
                    live_model_name=profile.model_name,
                    fallback_reason=_describe_provider_error(exc),
                    last_model_error=_describe_provider_error(exc),
                ),
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
                    provider_diagnostics=ProviderDiagnostics(
                        provider_status="fallback_mock",
                        live_model_name=profile.model_name,
                        fallback_reason="Demo endpoint missing.",
                    ),
                )
            return GatewayChatResponse(
                answer=_provider_error_answer(
                    profile=profile,
                    base_url=base_url,
                    error="No endpoint is configured for this profile.",
                ),
                provider_used=f"{profile.id}:openai-config-error",
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="endpoint_error",
                    provider_source=base_url,
                    live_model_name=profile.model_name,
                    last_model_error="No endpoint is configured for this profile.",
                ),
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
            started = perf_counter()
            answer = await client.chat_completions(payload)
            return GatewayChatResponse(
                answer=answer or "(empty response)",
                provider_used=f"{profile.id}:openai-compatible",
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="live_gemma" if "gemma" in profile.model_name.lower() else "unknown",
                    provider_source=base_url,
                    live_model_name=profile.model_name,
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                ),
            )
        except Exception as exc:
            if profile.id == "demo":
                return GatewayChatResponse(
                    answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                    provider_used=f"{profile.id}:openai-fallback",
                    provider_diagnostics=ProviderDiagnostics(
                        provider_status="fallback_mock",
                        provider_source=base_url,
                        live_model_name=profile.model_name,
                        fallback_reason=_describe_provider_error(exc),
                        last_model_error=_describe_provider_error(exc),
                    ),
                )
            return GatewayChatResponse(
                answer=_provider_error_answer(profile=profile, base_url=base_url, error=_describe_provider_error(exc)),
                provider_used=f"{profile.id}:openai-error",
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="local_not_ready" if profile.id == "local" else "endpoint_error",
                    provider_source=base_url,
                    live_model_name=profile.model_name,
                    last_model_error=_describe_provider_error(exc),
                ),
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
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="fallback_mock",
                    provider_source=status.source,
                    live_model_name=status.model,
                    fallback_reason="No demo provider credential was detected.",
                ),
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
            started = perf_counter()
            answer = await client.chat_completions(payload)
        except Exception:
            return GatewayChatResponse(
                answer=fallback_grounded_answer(prompt, evidence, screen_context, region_context),
                provider_used="demo:offline-mock",
                provider_diagnostics=ProviderDiagnostics(
                    provider_status="fallback_mock",
                    provider_source=status.source,
                    live_model_name=status.model,
                    fallback_reason="Demo model call failed.",
                ),
            )

        return GatewayChatResponse(
            answer=answer or "(empty response)",
            provider_used=f"demo:{status.source}:{status.model}",
            provider_diagnostics=ProviderDiagnostics(
                provider_status="live_gemma" if "gemma" in status.model.lower() else "unknown",
                provider_source=status.source,
                live_model_name=status.model,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            ),
        )


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
