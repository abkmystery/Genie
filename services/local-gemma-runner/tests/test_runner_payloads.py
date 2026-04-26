from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path


RUNNER_DIR = Path(__file__).resolve().parents[1]
APP_PATH = RUNNER_DIR / "app.py"

spec = importlib.util.spec_from_file_location("genie_local_gemma_runner_app", APP_PATH)
assert spec is not None and spec.loader is not None
runner_app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner_app
spec.loader.exec_module(runner_app)

_build_gemma_messages = runner_app._build_gemma_messages
_dependency_status = runner_app._dependency_status
_generate = runner_app._generate
_move_inputs_to_device = runner_app._move_inputs_to_device
app = runner_app.app


def test_dependency_status_exposes_actionable_fields():
    status = _dependency_status()

    assert "auto_model_for_multimodal_lm_available" in status
    assert "setup_hint" in status


def test_ready_endpoint_reports_runtime_state():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    payload = client.get("/ready").json()

    assert "ok" in payload
    assert "runtime" in payload
    assert "dependencies" in payload


def test_warmup_endpoint_uses_loader(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(runner_app, "_load_model", lambda _model_id: ("processor", "model"))
    client = TestClient(app)
    payload = client.post("/warmup").json()

    assert payload["ok"] is True
    assert "latency_ms" in payload


def test_openai_audio_payload_is_converted_to_gemma_audio_part():
    temp_paths: list[Path] = []

    messages = _build_gemma_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribe this."},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64.b64encode(b"fake-wav").decode("ascii"),
                            "format": "wav",
                        },
                    },
                ],
            }
        ],
        temp_paths,
    )

    try:
        assert messages[0]["content"][0] == {"type": "text", "text": "Transcribe this."}
        assert messages[0]["content"][1]["type"] == "audio"
        assert messages[0]["content"][1]["url"].startswith("file:///")
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


def test_openai_image_data_url_is_converted_to_gemma_image_part():
    temp_paths: list[Path] = []
    image_url = "data:image/png;base64," + base64.b64encode(b"fake-png").decode("ascii")

    messages = _build_gemma_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "What is visible?"},
                ],
            }
        ],
        temp_paths,
    )

    try:
        assert messages[0]["content"][0]["type"] == "image"
        assert messages[0]["content"][0]["url"].startswith("file:///")
        assert messages[0]["content"][1] == {"type": "text", "text": "What is visible?"}
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


def test_move_inputs_to_device_does_not_force_model_dtype_on_token_ids():
    class _Inputs:
        def __init__(self):
            self.calls = []

        def to(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return self

    class _Model:
        device = "cpu"
        dtype = "bfloat16"

    inputs = _Inputs()
    assert _move_inputs_to_device(inputs, _Model()) is inputs
    assert inputs.calls == [(("cpu",), {})]


def test_generate_retries_without_static_cache():
    class _Model:
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            if "cache_implementation" in kwargs:
                raise RuntimeError("static cache unsupported")
            return ["ok"]

    model = _Model()
    output = _generate(model, {"input_ids": "ids"}, max_new_tokens=8, temperature=0)

    assert output == ["ok"]
    assert "cache_implementation" in model.calls[0]
    assert "cache_implementation" not in model.calls[1]
