from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.providers.demo_credentials import DemoCredentialResolver


@pytest.mark.anyio
async def test_demo_resolver_prefers_bundled_file(tmp_path: Path):
    resources = tmp_path / "resources"
    private = resources / "private"
    private.mkdir(parents=True, exist_ok=True)

    key = "demo-key-123"
    (private / "demo-provider.json").write_text(
        """{
  "provider_type":"google_gemini_openai_compatible",
  "base_url":"https://generativelanguage.googleapis.com/v1beta/openai/",
  "api_key":"demo-key-123",
  "model":"gemma-4-26b-a4b-it",
  "timeout_ms":60000,
  "supports_images":true,
  "supports_audio_input":false
}""",
        encoding="utf-8",
    )

    resolver = DemoCredentialResolver(resources_dir=resources)
    resolved = await resolver.resolve(
        demo_source_order=["bundled_file", "offline_mock"],
        remote_demo_file_url=None,
        remote_demo_file_format=None,
        default_base_url="https://example.invalid/",
        default_model="fallback-model",
        default_timeout_ms=1,
    )

    assert resolved.status.source == "bundled_file"
    assert resolved.api_key == key
    assert resolved.status.api_key_present is True


@pytest.mark.anyio
async def test_demo_resolver_supports_base64_field(tmp_path: Path):
    resources = tmp_path / "resources"
    private = resources / "private"
    private.mkdir(parents=True, exist_ok=True)

    key = "demo-key-xyz"
    encoded = base64.b64encode(key.encode("utf-8")).decode("utf-8")
    (private / "demo-provider.json").write_text(
        f'{{"api_key_b64":"{encoded}","model":"gemma-4-26b-a4b-it"}}',
        encoding="utf-8",
    )

    resolver = DemoCredentialResolver(resources_dir=resources)
    resolved = await resolver.resolve(
        demo_source_order=["bundled_file", "offline_mock"],
        remote_demo_file_url=None,
        remote_demo_file_format=None,
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemma-4-26b-a4b-it",
        default_timeout_ms=60000,
    )

    assert resolved.api_key == key
    assert resolved.status.api_key_present is True

