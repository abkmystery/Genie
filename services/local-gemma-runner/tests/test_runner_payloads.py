from __future__ import annotations

import base64
import sys
from pathlib import Path


RUNNER_DIR = Path(__file__).resolve().parents[1]
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from app import _build_gemma_messages, _dependency_status  # noqa: E402


def test_dependency_status_exposes_actionable_fields():
    status = _dependency_status()

    assert "auto_model_for_multimodal_lm_available" in status
    assert "setup_hint" in status


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
