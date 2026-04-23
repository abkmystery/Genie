from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

try:  # Optional: allows local dev via services/demo-gateway/.env (never commit real secrets)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass


class EvidenceItem(BaseModel):
    id: str
    label: str
    kind: str
    quote: str | None = None
    locator: str | None = None
    score: float | None = None


class GatewayChatRequest(BaseModel):
    prompt: str
    profile_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    screen_summary: str | None = None
    region_summary: str | None = None
    screen_image_data_url: str | None = None
    region_image_data_url: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None


class GatewayChatResponse(BaseModel):
    answer: str
    provider_used: str


app = FastAPI(title="Genie Demo Gateway", version="0.1.0")

DEMO_GATEWAY_PROVIDER = os.getenv("DEMO_GATEWAY_PROVIDER", "gemini_openai").lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_OPENAI_BASE_URL = os.getenv(
    "GEMINI_OPENAI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
).rstrip("/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it")

DEMO_PROVIDER_URL = os.getenv("DEMO_PROVIDER_URL", "").rstrip("/")
DEMO_PROVIDER_TOKEN = os.getenv("DEMO_PROVIDER_TOKEN", "")


@app.get("/health")
def health():
    return {
        "ok": True,
        "mode": "scaffold",
        "provider": DEMO_GATEWAY_PROVIDER,
        "model": GEMINI_MODEL if DEMO_GATEWAY_PROVIDER == "gemini_openai" else None,
        "base_url": GEMINI_OPENAI_BASE_URL if DEMO_GATEWAY_PROVIDER == "gemini_openai" else None,
        "has_gemini_api_key": bool(GEMINI_API_KEY) if DEMO_GATEWAY_PROVIDER == "gemini_openai" else None,
        "message": "Demo gateway is running. Configure real upstream secrets only in private server environments.",
    }


def _render_grounding_context(request: GatewayChatRequest) -> str:
    lines: list[str] = []
    if request.screen_summary:
        lines.append(f"Screen summary: {request.screen_summary}")
    if request.region_summary:
        lines.append(f"Region summary: {request.region_summary}")
    if request.evidence:
        lines.append("Evidence:")
        for item in request.evidence[:8]:
            quote = (item.quote or "").strip()
            if quote:
                lines.append(f"- {item.label}: {quote}")
            else:
                lines.append(f"- {item.label}")
    return "\n".join(lines)


async def _chat_via_ollama(request: GatewayChatRequest) -> GatewayChatResponse:
    system = (
        "You are Genie, a desktop assistant. Answer from the provided evidence first. "
        "If you lack evidence, say you are unsure. Keep answers concise."
    )
    user = "\n\n".join(part for part in [_render_grounding_context(request), f"User question: {request.prompt}"] if part)
    payload: dict[str, Any] = {
        "model": DEMO_OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{DEMO_OLLAMA_HOST}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
    return GatewayChatResponse(answer=content or "(empty response)", provider_used=f"ollama:{DEMO_OLLAMA_MODEL}")


async def _chat_via_http_provider(request: GatewayChatRequest) -> GatewayChatResponse:
    if not DEMO_PROVIDER_URL:
        raise RuntimeError("DEMO_PROVIDER_URL is not set")
    headers = {}
    if DEMO_PROVIDER_TOKEN:
        headers["Authorization"] = f"Bearer {DEMO_PROVIDER_TOKEN}"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{DEMO_PROVIDER_URL}/v1/chat", json=request.model_dump(), headers=headers)
        response.raise_for_status()
        return GatewayChatResponse(**response.json())

async def _chat_via_gemini_openai(request: GatewayChatRequest) -> GatewayChatResponse:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    # OpenAI-compatible Gemini interface supports multimodal parts:
    # - {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}
    # - {"type":"input_audio","input_audio":{"data":"...","format":"wav"}}
    system = (
        "You are Genie, a desktop assistant. Answer from the provided evidence first. "
        "If you lack evidence, say you are unsure. Keep answers concise."
    )
    user_text = "\n\n".join(
        part for part in [_render_grounding_context(request), f"User question: {request.prompt}"] if part
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]

    if request.screen_image_data_url:
        content.append({"type": "image_url", "image_url": {"url": request.screen_image_data_url}})
    if request.region_image_data_url:
        content.append({"type": "image_url", "image_url": {"url": request.region_image_data_url}})

    if request.audio_base64 and request.audio_format:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": request.audio_base64,
                    "format": request.audio_format,
                },
            }
        )

    payload: dict[str, Any] = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GEMINI_API_KEY}"}
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{GEMINI_OPENAI_BASE_URL}/chat/completions", json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Surface response body to make debugging model/endpoint issues easy.
            body = (exc.response.text or "").strip()
            snippet = body[:1200] + ("..." if len(body) > 1200 else "")
            raise RuntimeError(f"Gemini OpenAI error {exc.response.status_code}: {snippet}") from exc
        data = response.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        answer = message.get("content") or ""
    return GatewayChatResponse(answer=answer or "(empty response)", provider_used=f"gemini:{GEMINI_MODEL}")


@app.post("/v1/chat", response_model=GatewayChatResponse)
async def chat(request: GatewayChatRequest) -> GatewayChatResponse:
    try:
        if DEMO_GATEWAY_PROVIDER == "gemini_openai":
            return await _chat_via_gemini_openai(request)
        if DEMO_GATEWAY_PROVIDER == "http":
            return await _chat_via_http_provider(request)
        raise RuntimeError("mock provider requested")
    except Exception as exc:
        context = _render_grounding_context(request)
        answer = "\n".join(
            [
                "Genie demo gateway fell back to a grounded mock response.",
                f"Reason: {type(exc).__name__}: {exc}",
                context,
                f"Prompt: {request.prompt}",
                "Answer: Configure GEMINI_API_KEY (server-side) for real model responses in demo mode.",
            ]
        ).strip()
        return GatewayChatResponse(answer=answer, provider_used="demo-gateway:mock-fallback")


@app.get("/diagnostics/models")
async def list_models(limit: int = 50):
    """
    Lists models visible to the configured GEMINI_API_KEY using the OpenAI-compatible /models endpoint.
    Useful for debugging 404s that are actually 'model not found' errors.
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY is not set"}
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{GEMINI_OPENAI_BASE_URL}/models", headers=headers)
        response.raise_for_status()
        data = response.json()
    models = data.get("data") or []
    ids = [model.get("id") for model in models if isinstance(model, dict)]
    return {
        "ok": True,
        "count": len(ids),
        "limit": limit,
        "configured_model": GEMINI_MODEL,
        "configured_model_visible": GEMINI_MODEL in ids,
        "models": ids[: max(1, min(limit, 200))],
    }
