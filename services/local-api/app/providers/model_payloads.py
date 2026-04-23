from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.models.contracts import EvidenceItem, RegionContext, ScreenContext

GENIE_SYSTEM_PROMPT = (
    "You are Genie, a warm desktop companion. Answer naturally and helpfully using the provided evidence first. "
    "Do not reveal chain-of-thought, hidden reasoning, scratch notes, XML tags, or labels like <thought> or <think>. "
    "Do not mention raw prompt assembly such as 'question', 'evidence above', or internal context labels. "
    "When screen context is relevant, answer like a person helping another person. If evidence is weak, say so briefly."
)


def encode_image_data_url(path: str) -> str | None:
    try:
        file_path = Path(path)
        mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
        encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    except Exception:
        return None


def build_grounded_user_text(
    *,
    prompt: str,
    evidence: list[EvidenceItem],
    screen_context: ScreenContext | None,
    region_context: RegionContext | None,
) -> str:
    grounding: list[str] = []
    if screen_context:
        grounding.append(f"Screen summary: {screen_context.summary}")
    if region_context:
        grounding.append(f"Region summary: {region_context.summary}")
    if evidence:
        grounding.append("Relevant context:")
        for item in evidence[:8]:
            quote = (item.quote or "").strip()
            grounding.append(f"- {item.label}: {quote}" if quote else f"- {item.label}")
    return "\n\n".join([*grounding, f"Request: {prompt}"]).strip()


def build_openai_compatible_payload(
    *,
    model: str,
    prompt: str,
    evidence: list[EvidenceItem],
    screen_context: ScreenContext | None,
    region_context: RegionContext | None,
    supports_images: bool,
    supports_audio_input: bool,
    audio_base64: str | None = None,
    audio_format: str | None = None,
    additional_image_paths: list[str] | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": build_grounded_user_text(
                prompt=prompt,
                evidence=evidence,
                screen_context=screen_context,
                region_context=region_context,
            ),
        }
    ]

    if supports_images:
        for image_path in _candidate_image_paths(screen_context, region_context, additional_image_paths):
            url = encode_image_data_url(image_path)
            if url:
                content.append({"type": "image_url", "image_url": {"url": url}})

    if supports_audio_input and audio_base64 and audio_format:
        content.append({"type": "input_audio", "input_audio": {"data": audio_base64, "format": audio_format}})

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": GENIE_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
    }


def _candidate_image_paths(
    screen_context: ScreenContext | None,
    region_context: RegionContext | None,
    additional_image_paths: list[str] | None,
) -> list[str]:
    paths: list[str] = []
    if screen_context:
        paths.append(screen_context.capture.path)
    if region_context:
        paths.append(region_context.capture.path)
    paths.extend(additional_image_paths or [])
    return paths
