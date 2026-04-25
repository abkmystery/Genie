from __future__ import annotations

import asyncio

import httpx

from app.models.contracts import ProviderCapabilities, ProviderConfig
from app.providers.model_provider import OpenAICompatibleHttpModelProvider
from app.providers.openai_compatible import OpenAICompatibleClient


def test_openai_compatible_provider_surfaces_local_endpoint_failures(monkeypatch):
    async def _fail(_self, _payload):
        request = httpx.Request("POST", "http://127.0.0.1:8766/v1/chat/completions")
        response = httpx.Response(503, text="model is still loading", request=request)
        raise httpx.HTTPStatusError("Service unavailable", request=request, response=response)

    monkeypatch.setattr(OpenAICompatibleClient, "chat_completions", _fail)
    provider = OpenAICompatibleHttpModelProvider()
    profile = ProviderConfig(
        id="local",
        display_name="Local Gemma",
        description="Local model",
        transport="http",
        backend_base_url="http://127.0.0.1:8766/v1",
        model_name="gemma-4-e4b-it",
        capabilities=ProviderCapabilities(supports_screen_input=True),
    )

    result = asyncio.run(provider.answer("What is on my screen?", profile, evidence=[]))

    assert result.provider_used == "local:openai-error"
    assert "HTTP 503" in result.answer
    assert "local model server is running" in result.answer
    assert "Native screen capture" not in result.answer
