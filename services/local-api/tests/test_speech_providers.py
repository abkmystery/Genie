import asyncio
import base64

from app.models.contracts import ProviderCapabilities, ProviderConfig
from app.domain.profile_service import ProviderRegistry
from app.providers.credential_store import FileCredentialStore
from app.providers.speech_provider import OpenAICompatibleSpeechToTextProvider, OptionalWhisperSpeechToTextProvider, PowerShellSpeechTtsProvider, UnavailableSpeechToTextProvider


def test_speech_to_text_provider_reports_diagnostics():
    provider = OptionalWhisperSpeechToTextProvider()
    diagnostics = provider.diagnostics()
    assert diagnostics["provider"] == "local-whisper"
    assert "available" in diagnostics


def test_openai_compatible_speech_to_text_provider_transcribes(monkeypatch):
    provider = OpenAICompatibleSpeechToTextProvider(
        base_url="http://127.0.0.1:8766/v1",
        model_name="google/gemma-4-E4B-it",
        provider_label="local:model-audio",
    )

    async def fake_chat(self, payload):
        assert payload["model"] == "google/gemma-4-E4B-it"
        audio_part = payload["messages"][0]["content"][1]["input_audio"]
        assert audio_part["format"] == "wav"
        return "hello from gemma"

    monkeypatch.setattr("app.providers.speech_provider.OpenAICompatibleClient.chat_completions", fake_chat)
    transcript = asyncio.run(
        provider.transcribe(
            audio_base64=base64.b64encode(b"fake-wav").decode("ascii"),
            audio_format="wav",
        )
    )
    assert transcript == "hello from gemma"
    diagnostics = provider.diagnostics()
    assert diagnostics["provider"] == "local:model-audio"
    assert diagnostics["available"] is True


def test_provider_registry_prefers_model_audio_for_local_openai_profile(tmp_path):
    store = FileCredentialStore(tmp_path / "creds.json")
    registry = ProviderRegistry(store, data_dir=tmp_path)
    profile = ProviderConfig(
        id="local",
        display_name="Local",
        description="Local profile",
        transport="http",
        api_style="openai_compatible",
        backend_base_url="http://127.0.0.1:8766/v1",
        model_name="google/gemma-4-E4B-it",
        timeout_ms=45000,
        capabilities=ProviderCapabilities(supports_screen_input=True, supports_stt=True, supports_tts=False),
        credentials_required=False,
        credentials_stored_locally=True,
    )
    provider = registry.create_speech_to_text_client(profile)
    assert provider.diagnostics()["provider"] == "local:model-audio"


def test_provider_registry_does_not_send_demo_audio_to_raw_provider_without_local_stt(tmp_path, monkeypatch):
    store = FileCredentialStore(tmp_path / "creds.json")
    registry = ProviderRegistry(store, data_dir=tmp_path)
    profile = ProviderConfig(
        id="demo",
        display_name="Demo",
        description="Demo profile",
        transport="http",
        api_style="openai_compatible",
        backend_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_name="gemma-4-26b-a4b-it",
        timeout_ms=45000,
        capabilities=ProviderCapabilities(supports_screen_input=True, supports_stt=True, supports_tts=False),
        credentials_required=False,
        credentials_stored_locally=False,
    )
    monkeypatch.setattr("app.providers.speech_provider.OptionalWhisperSpeechToTextProvider.diagnostics", lambda self: {"available": False})
    provider = registry.create_speech_to_text_client(profile)
    assert isinstance(provider, UnavailableSpeechToTextProvider)


def test_text_to_speech_provider_reports_diagnostics():
    provider = PowerShellSpeechTtsProvider()
    diagnostics = provider.diagnostics()
    assert diagnostics["provider"] == "powershell-system-speech"
    assert diagnostics["available"] is True
