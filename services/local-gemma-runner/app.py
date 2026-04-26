from __future__ import annotations

import base64
import ctypes
import mimetypes
import os
import platform
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_IMPORT_ERROR: str | None = None
_TRANSFORMERS_VERSION: str | None = None

try:  # pragma: no cover - depends on the user's local ML environment
    import torch
    import transformers
    from transformers import AutoProcessor

    _TRANSFORMERS_VERSION = getattr(transformers, "__version__", "unknown")
    try:
        from transformers import AutoModelForMultimodalLM
    except Exception:
        AutoModelForMultimodalLM = None
except Exception as exc:  # pragma: no cover - optional experimental runner deps
    torch = None
    AutoProcessor = None
    AutoModelForMultimodalLM = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


DEFAULT_MODEL_ID = os.environ.get("GENIE_LOCAL_MODEL_ID", "google/gemma-4-E4B-it")
DEFAULT_MODEL_DIR = Path(
    os.environ.get(
        "GENIE_LOCAL_MODEL_DIR",
        Path(__file__).resolve().parents[2] / "models" / "gemma-4-E4B-it",
    )
)
GEMMA4_SETUP_HINT = (
    "Install a Transformers build with Gemma 4 multimodal support, then restart the runner. "
    "If you see a NumPy 'Inf' import error, run: py -3.11 -m pip install --upgrade --force-reinstall \"numpy>=1.26,<2\". "
    "Recommended: npm.cmd run setup:local-gemma. Manual fallback: "
    "py -3.11 -m pip install --upgrade --force-reinstall "
    "\"transformers @ git+https://github.com/huggingface/transformers.git\""
)


class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL_ID
    messages: list[dict[str, Any]]
    max_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = 0.2


app = FastAPI(title="Genie Local Gemma Runner", version="0.2.0")
_processor = None
_model = None
_load_lock = threading.Lock()
_generation_lock = threading.Lock()
_load_started_at: float | None = None
_load_finished_at: float | None = None
_last_error: str | None = None


class LocalModelNotReadyError(RuntimeError):
    pass


def _dependency_status() -> dict[str, Any]:
    has_required_model = AutoModelForMultimodalLM is not None
    return {
        "ok": bool(torch and AutoProcessor and has_required_model),
        "transformers_version": _TRANSFORMERS_VERSION,
        "torch_available": torch is not None,
        "auto_processor_available": AutoProcessor is not None,
        "auto_model_for_multimodal_lm_available": has_required_model,
        "import_error": _IMPORT_ERROR,
        "setup_hint": None if has_required_model else GEMMA4_SETUP_HINT,
    }


def _runtime_status() -> dict[str, Any]:
    return {
        "loaded": _processor is not None and _model is not None,
        "loading": _load_started_at is not None and _load_finished_at is None and _model is None,
        "load_started_at": _load_started_at,
        "load_finished_at": _load_finished_at,
        "last_error": _last_error,
        "device": str(getattr(_model, "device", "unloaded")) if _model is not None else "unloaded",
        "dtype": str(getattr(_model, "dtype", "unknown")) if _model is not None else "unknown",
    }


def _model_ref(model_name: str) -> str:
    return str(DEFAULT_MODEL_DIR if DEFAULT_MODEL_DIR.exists() else model_name)


def _available_memory_bytes() -> int | None:
    try:
        if platform.system().lower() == "windows":
            class _MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
    except Exception:
        return None
    return None


def _largest_safetensors_bytes(model_dir: Path) -> int:
    try:
        return max((path.stat().st_size for path in model_dir.glob("*.safetensors")), default=0)
    except Exception:
        return 0


def _preflight_model_files(model_ref: str) -> None:
    model_dir = Path(model_ref)
    if not model_dir.exists():
        return
    largest = _largest_safetensors_bytes(model_dir)
    available = _available_memory_bytes()
    if largest <= 0 or available is None or torch is None or torch.cuda.is_available():
        return
    # Single-shard 4B models can need substantially more than the raw file
    # size on CPU. Fail early with a useful message instead of an opaque 503.
    if largest > available * 0.75:
        raise LocalModelNotReadyError(
            "The configured local Gemma model is too large for the currently available RAM. "
            f"Largest safetensors shard: {largest / (1024 ** 3):.1f} GB; "
            f"available physical RAM: {available / (1024 ** 3):.1f} GB. "
            "Use hosted Demo mode for the competition path, switch Local to a smaller/quantized Gemma 4 model, "
            "or close apps/increase RAM/pagefile and restart the local runner."
        )


def _raise_unavailable() -> None:
    status = _dependency_status()
    if status["ok"]:
        return
    missing = [
        key
        for key in ("torch_available", "auto_processor_available", "auto_model_for_multimodal_lm_available")
        if not status.get(key)
    ]
    raise RuntimeError(
        "Local Gemma 4 runner is not ready. "
        f"Missing: {', '.join(missing) or 'unknown dependency'}. "
        f"Transformers: {status.get('transformers_version') or 'not importable'}. "
        f"{GEMMA4_SETUP_HINT}"
    )


def _load_model(model_name: str):
    global _processor, _model, _load_started_at, _load_finished_at, _last_error
    if _processor is not None and _model is not None:
        return _processor, _model

    with _load_lock:
        if _processor is not None and _model is not None:
            return _processor, _model
        _load_started_at = time.time()
        _load_finished_at = None
        _last_error = None
        try:
            _raise_unavailable()
            model_ref = _model_ref(model_name)
            _preflight_model_files(model_ref)
            _processor = AutoProcessor.from_pretrained(model_ref, padding_side="left", use_fast=True)
            load_kwargs: dict[str, Any] = {
                "dtype": torch.bfloat16 if torch.cuda.is_available() else "auto",
                "device_map": "auto",
                "low_cpu_mem_usage": True,
            }
            try:
                load_kwargs["attn_implementation"] = "sdpa"
                _model = AutoModelForMultimodalLM.from_pretrained(model_ref, **load_kwargs).eval()
            except TypeError:
                load_kwargs.pop("attn_implementation", None)
                _model = AutoModelForMultimodalLM.from_pretrained(model_ref, **load_kwargs).eval()
            _load_finished_at = time.time()
        except Exception as exc:
            _last_error = f"{type(exc).__name__}: {exc}"
            _load_finished_at = time.time()
            raise
    return _processor, _model


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    header, encoded = data_url.split(",", 1)
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
    return base64.b64decode(encoded), mime_type


def _write_temp_file(*, data: bytes, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with handle:
        handle.write(data)
    return Path(handle.name)


def _write_audio_part(part: dict[str, Any]) -> Path | None:
    audio = part.get("input_audio") or {}
    data = audio.get("data")
    if not data:
        return None
    audio_format = str(audio.get("format") or "wav").lower().lstrip(".")
    return _write_temp_file(data=base64.b64decode(data), suffix=f".{audio_format}")


def _write_image_part(part: dict[str, Any]) -> Path | None:
    image_url = (part.get("image_url") or {}).get("url")
    if not isinstance(image_url, str) or not image_url.startswith("data:"):
        return None
    image_bytes, mime_type = _decode_data_url(image_url)
    suffix = mimetypes.guess_extension(mime_type) or ".png"
    return _write_temp_file(data=image_bytes, suffix=suffix)


def _normalise_message_content(content: Any, temp_paths: list[Path]) -> list[dict[str, str]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []

    normalised: list[dict[str, str]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = str(part.get("text") or "").strip()
            if text:
                normalised.append({"type": "text", "text": text})
        elif part_type == "image_url":
            image_path = _write_image_part(part)
            if image_path:
                temp_paths.append(image_path)
                normalised.append({"type": "image", "url": image_path.as_uri()})
        elif part_type == "input_audio":
            audio_path = _write_audio_part(part)
            if audio_path:
                temp_paths.append(audio_path)
                normalised.append({"type": "audio", "url": audio_path.as_uri()})
    return normalised


def _build_gemma_messages(messages: list[dict[str, Any]], temp_paths: list[Path]) -> list[dict[str, Any]]:
    gemma_messages: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        if role not in {"system", "user", "assistant"}:
            role = "user"
        content = _normalise_message_content(message.get("content"), temp_paths)
        if content:
            gemma_messages.append({"role": role, "content": content})
    if not gemma_messages:
        gemma_messages.append({"role": "user", "content": [{"type": "text", "text": "Respond briefly."}]})
    return gemma_messages


def _move_inputs_to_device(inputs: Any, model: Any):
    target = getattr(model, "device", None)
    if hasattr(inputs, "to") and target is not None:
        try:
            return inputs.to(target)
        except TypeError:
            return inputs.to(device=target)
    if isinstance(inputs, dict):
        return {key: value.to(target) if target is not None and hasattr(value, "to") else value for key, value in inputs.items()}
    return inputs


def _generate(model: Any, inputs: Any, *, max_new_tokens: int, temperature: float):
    generation_kwargs = {
        **inputs,
        "max_new_tokens": max_new_tokens,
        "do_sample": temperature > 0,
        "temperature": max(temperature, 0.01),
    }
    try:
        return model.generate(**generation_kwargs, cache_implementation="static")
    except Exception as first_error:
        # Some CPU/offloaded Gemma 4 setups do not support static cache. Retry
        # once with the safest generation path before surfacing a 503.
        try:
            return model.generate(**generation_kwargs)
        except Exception as second_error:
            raise RuntimeError(
                f"Generation failed. static-cache error: {type(first_error).__name__}: {first_error}; "
                f"fallback error: {type(second_error).__name__}: {second_error}"
            ) from second_error


@app.get("/health")
def health():
    status = _dependency_status()
    return {
        "ok": status["ok"],
        "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
        "model_dir": str(DEFAULT_MODEL_DIR),
        "model_id": DEFAULT_MODEL_ID,
        "dependencies": status,
        "runtime": _runtime_status(),
    }


@app.get("/ready")
def ready():
    status = _dependency_status()
    runtime = _runtime_status()
    return {
        "ok": bool(status["ok"] and runtime["loaded"]),
        "dependencies": status,
        "runtime": runtime,
        "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
        "model_id": DEFAULT_MODEL_ID,
    }


@app.get("/diagnostics")
def diagnostics():
    return {
        "ok": True,
        "model_id": DEFAULT_MODEL_ID,
        "model_dir": str(DEFAULT_MODEL_DIR),
        "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
        "dependencies": _dependency_status(),
        "runtime": _runtime_status(),
        "cuda_available": bool(torch and torch.cuda.is_available()) if torch else False,
    }


@app.post("/warmup")
def warmup():
    try:
        started = time.perf_counter()
        _load_model(DEFAULT_MODEL_ID)
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "runtime": _runtime_status()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error": f"{type(exc).__name__}: {exc}", "runtime": _runtime_status(), "dependencies": _dependency_status()}) from exc


@app.get("/v1/models")
def list_models():
    status = _dependency_status()
    return {
        "object": "list",
        "ready": status["ok"],
        "data": [
            {
                "id": DEFAULT_MODEL_ID,
                "object": "model",
                "owned_by": "local",
                "model_dir": str(DEFAULT_MODEL_DIR),
                "model_dir_exists": DEFAULT_MODEL_DIR.exists(),
                "supports_audio_input": status["ok"],
                "supports_image_input": status["ok"],
            }
        ],
        "diagnostics": status,
    }


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    temp_paths: list[Path] = []
    try:
        with _generation_lock:
            processor, model = _load_model(request.model)
            gemma_messages = _build_gemma_messages(request.messages, temp_paths)
            inputs = processor.apply_chat_template(
                gemma_messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            inputs = _move_inputs_to_device(inputs, model)
            input_len = inputs["input_ids"].shape[-1]
            output = _generate(
                model,
                inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            decoded = processor.decode(output[0][input_len:], skip_special_tokens=True).strip()
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": decoded},
                    "finish_reason": "stop",
                }
            ]
        }
    except Exception as exc:
        detail = {
            "error": f"{type(exc).__name__}: {exc}",
            "model": request.model,
            "model_dir": str(DEFAULT_MODEL_DIR),
            "dependencies": _dependency_status(),
            "runtime": _runtime_status(),
        }
        raise HTTPException(status_code=503, detail=detail) from exc
    finally:
        for path in temp_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


@app.post("/smoke")
def smoke():
    request = ChatCompletionRequest(
        model=DEFAULT_MODEL_ID,
        messages=[{"role": "user", "content": "Reply with exactly: GENIE_OK"}],
        max_tokens=24,
        temperature=0,
    )
    return chat_completions(request)
