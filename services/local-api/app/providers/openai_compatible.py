from __future__ import annotations

from typing import Any

import httpx
import re

_LATEX_WORDS = {
    "sin": "sine",
    "cos": "cosine",
    "tan": "tangent",
    "cot": "cotangent",
    "sec": "secant",
    "csc": "cosecant",
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "theta": "theta",
    "pi": "pi",
}


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
    text = _replace_latex_math(text)
    text = _strip_markdown_noise(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _replace_latex_math(value: str) -> str:
    text = value
    text = re.sub(r"\$\$(.*?)\$\$", lambda match: _plain_math(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"\\\[(.*?)\\\]", lambda match: _plain_math(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"\\\((.*?)\\\)", lambda match: _plain_math(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"\$(.*?)\$", lambda match: _plain_math(match.group(1)), text, flags=re.DOTALL)
    return text


def _plain_math(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\\text\{([^{}]+)\}", r"\1", text)
    for _ in range(4):
        next_text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1 divided by \2", text)
        if next_text == text:
            break
        text = next_text
    for command, word in _LATEX_WORDS.items():
        text = re.sub(rf"\\{command}\b", word, text)
    text = text.replace("\\cdot", " times ")
    text = text.replace("\\times", " times ")
    text = text.replace("\\over", " divided by ")
    text = text.replace("\\", "")
    text = text.replace("^", " to the power of ")
    text = text.replace("_", " ")
    text = text.replace("=", " equals ")
    text = text.replace("/", " divided by ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_markdown_noise(value: str) -> str:
    text = value
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)
    text = re.sub(r"^\s*[*-]\s+", "", text, flags=re.MULTILINE)
    return text
