from __future__ import annotations

from typing import Any

import httpx
import re


class OpenAICompatibleClient:
    """
    Minimal OpenAI-compatible client for /chat/completions.
    Uses Authorization: Bearer <token>.
    """

    def __init__(self, *, base_url: str, bearer_token: str | None, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = (bearer_token or "").strip()
        self.timeout_s = timeout_s

    async def chat_completions(self, payload: dict[str, Any]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        return _sanitize_model_output(message.get("content") or "")


def _sanitize_model_output(value: str) -> str:
    text = value.strip()
    text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:thought|think)\b[^>]*>.*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = text.replace("</thought>", "").replace("</think>", "")
    text = re.sub(r"^\s*User question:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
