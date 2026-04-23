from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    try:
        from transformers import AutoModelForMultimodalLM
    except Exception:  # pragma: no cover - depends on installed transformers version
        AutoModelForMultimodalLM = None
except Exception:  # pragma: no cover - optional experimental runner deps
    torch = None
    AutoProcessor = None
    AutoModelForCausalLM = None
    AutoModelForMultimodalLM = None


DEFAULT_MODEL_ID = os.environ.get("GENIE_LOCAL_MODEL_ID", "google/gemma-4-E4B-it")
DEFAULT_MODEL_DIR = Path(os.environ.get("GENIE_LOCAL_MODEL_DIR", Path(__file__).resolve().parents[2] / "models" / "gemma-4-E4B-it"))


class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL_ID
    messages: list[dict[str, Any]]
    max_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = 0.2


app = FastAPI(title="Genie Local Gemma Runner", version="0.1.0")
_processor = None
_model = None


def _load_model(model_name: str):
    global _processor, _model
    if _processor is not None and _model is not None:
        return _processor, _model
    if AutoProcessor is None or torch is None or (AutoModelForMultimodalLM is None and AutoModelForCausalLM is None):
        raise RuntimeError("Transformers Gemma 4 dependencies are not installed.")

    model_ref = str(DEFAULT_MODEL_DIR if DEFAULT_MODEL_DIR.exists() else model_name)
    _processor = AutoProcessor.from_pretrained(model_ref)
    model_class = AutoModelForMultimodalLM or AutoModelForCausalLM
    _model = model_class.from_pretrained(
        model_ref,
        dtype="auto",
        low_cpu_mem_usage=True,
        device_map="auto",
    ).eval()
    return _processor, _model


def _extract_prompt_and_media(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    texts: list[str] = []
    media: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(str(part.get("text") or ""))
            elif part.get("type") in {"image_url", "input_audio"}:
                media.append(part)
    return "\n".join(text for text in texts if text.strip()).strip(), media


def _write_audio_part(part: dict[str, Any]) -> Path | None:
    audio = part.get("input_audio") or {}
    data = audio.get("data")
    fmt = audio.get("format") or "wav"
    if not data:
        return None
    suffix = f".{fmt}"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with handle:
        handle.write(base64.b64decode(data))
    return Path(handle.name)


@app.get("/health")
def health():
    return {
        "ok": True,
        "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
        "model_dir": str(DEFAULT_MODEL_DIR),
        "model_id": DEFAULT_MODEL_ID,
        "dependencies_available": bool(AutoProcessor and torch and (AutoModelForMultimodalLM or AutoModelForCausalLM)),
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": DEFAULT_MODEL_ID,
                "object": "model",
                "owned_by": "local",
                "model_dir": str(DEFAULT_MODEL_DIR),
                "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    try:
        processor, model = _load_model(request.model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    prompt, media_parts = _extract_prompt_and_media(request.messages)
    audio_paths: list[Path] = []
    try:
        conversation: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        for part in media_parts:
            if part.get("type") == "input_audio":
                audio_path = _write_audio_part(part)
                if audio_path:
                    audio_paths.append(audio_path)
                    conversation[0]["content"].append({"type": "audio", "audio": str(audio_path)})

        inputs = processor.apply_chat_template(
            conversation,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = {key: value.to(model.device) for key, value in inputs.items()}
        output = model.generate(**inputs, max_new_tokens=request.max_tokens, do_sample=request.temperature > 0, temperature=max(request.temperature, 0.01))
        decoded = processor.batch_decode(output[:, inputs["input_ids"].shape[-1] :], skip_special_tokens=True)[0].strip()
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": decoded},
                    "finish_reason": "stop",
                }
            ]
        }
    finally:
        for path in audio_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
