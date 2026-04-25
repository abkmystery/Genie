from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

from app.core.database import Database
from app.models.contracts import ProviderConfig, SettingsState
from app.providers.interfaces import ProfileConfigLoader, SecureCredentialStore
from app.providers.demo_credentials import DemoCredentialResolver, DemoResolverResult
from app.providers.model_provider import (
    DemoModelProvider,
    GatewayModelProvider,
    HttpModelProvider,
    MockModelProvider,
    OpenAICompatibleHttpModelProvider,
)
from app.providers.speech_provider import (
    CascadingSpeechToTextProvider,
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    OpenAICompatibleSpeechToTextProvider,
    OptionalPyttsx3TextToSpeechProvider,
    OptionalWhisperSpeechToTextProvider,
    PowerShellSpeechTtsProvider,
    UnavailableSpeechToTextProvider,
)


@dataclass
class ProviderRegistry:
    credential_store: SecureCredentialStore
    demo_resolver: DemoCredentialResolver | None = None
    data_dir: Path | None = None
    _text_to_speech_client: Any | None = field(default=None, init=False, repr=False)

    def create_model_client(
        self, profile: ProviderConfig
    ) -> MockModelProvider | HttpModelProvider | GatewayModelProvider | DemoModelProvider | OpenAICompatibleHttpModelProvider:
        if profile.id == "demo" and self.demo_resolver is not None:
            async def resolve_demo_config(resolved_profile: ProviderConfig) -> DemoResolverResult:
                return await self.demo_resolver.resolve(
                    demo_source_order=resolved_profile.demo_source_order,
                    remote_demo_file_url=resolved_profile.remote_demo_file_url,
                    remote_demo_file_format=resolved_profile.remote_demo_file_format,
                    default_base_url=(resolved_profile.backend_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"),
                    default_model=(resolved_profile.default_model or resolved_profile.model_name or "gemma-4-26b-a4b-it"),
                    default_timeout_ms=resolved_profile.timeout_ms or 60000,
                )

            return DemoModelProvider(resolve_demo_config=resolve_demo_config)

        credentials = self.credential_store.get(profile.id) or {}
        if profile.transport == "gateway":
            return GatewayModelProvider(credentials)
        if profile.transport == "http" and (profile.endpoint_override or profile.backend_base_url):
            if (profile.api_style or "genie_gateway") == "openai_compatible":
                return OpenAICompatibleHttpModelProvider(credentials)
            return HttpModelProvider(credentials)
        return MockModelProvider()

    def create_speech_to_text_client(self, profile: ProviderConfig, credentials: dict[str, Any] | None = None):
        resolved_credentials = credentials if credentials is not None else (self.credential_store.get(profile.id) or {})
        endpoint = (profile.endpoint_override or profile.backend_base_url or "").rstrip("/")
        whisper_provider = OptionalWhisperSpeechToTextProvider(download_root=(self.data_dir / "speech-models") if self.data_dir else None)
        whisper_available = bool(whisper_provider.diagnostics().get("available"))
        if (
            profile.id in {"local", "custom"}
            and (profile.api_style or "genie_gateway") == "openai_compatible"
            and endpoint
            and (profile.capabilities.supports_stt or self._looks_audio_native_model(profile.model_name))
            and profile.model_name
        ):
            model_audio_provider = OpenAICompatibleSpeechToTextProvider(
                base_url=endpoint,
                model_name=profile.model_name,
                bearer_token=resolved_credentials.get("token"),
                provider_label=f"{profile.id}:model-audio",
                timeout_ms=profile.timeout_ms,
            )
            return CascadingSpeechToTextProvider([model_audio_provider, whisper_provider]) if whisper_available else model_audio_provider

        if whisper_available:
            return whisper_provider
        return UnavailableSpeechToTextProvider(
            "No model-backed or offline STT provider is available. Browser speech recognition can still be used in the desktop UI."
        )

    def _looks_audio_native_model(self, model_name: str | None) -> bool:
        normalized = (model_name or "").lower()
        return "gemma-4-e2b" in normalized or "gemma-4-e4b" in normalized or "gemma-4-edge" in normalized

    def create_text_to_speech_client(self, profile: ProviderConfig, credentials: dict[str, Any] | None = None):
        if self._text_to_speech_client is None:
            pyttsx3_provider = OptionalPyttsx3TextToSpeechProvider()
            if pyttsx3_provider.diagnostics().get("available"):
                self._text_to_speech_client = pyttsx3_provider
            else:
                powershell_provider = PowerShellSpeechTtsProvider()
                if powershell_provider.diagnostics().get("available"):
                    self._text_to_speech_client = powershell_provider
                else:
                    self._text_to_speech_client = MockTextToSpeechProvider()
        return self._text_to_speech_client


class ProfileManager:
    def __init__(
        self,
        loader: ProfileConfigLoader,
        database: Database,
        credential_store: SecureCredentialStore,
        demo_gateway_url: str,
    ) -> None:
        self.loader = loader
        self.database = database
        self.credential_store = credential_store
        self.demo_gateway_url = demo_gateway_url

    def load_active_profile(self) -> ProviderConfig:
        active_profile_id = self.database.get_setting("active_profile_id", "demo") or "demo"
        return self.get_resolved_provider_config(active_profile_id)

    def list_profiles(self) -> list[ProviderConfig]:
        return [self.get_resolved_provider_config(profile.id) for profile in self.loader.list_profiles()]

    def set_active_profile(self, profile_id: str) -> ProviderConfig:
        self.database.set_setting("active_profile_id", profile_id)
        return self.get_resolved_provider_config(profile_id)

    def get_resolved_provider_config(self, profile_id: str | None = None) -> ProviderConfig:
        profile = self.loader.get_profile(profile_id or self.database.get_setting("active_profile_id", "demo") or "demo")
        custom_endpoint = self.database.get_setting("custom_endpoint", "") or ""
        local_endpoint = self.database.get_setting("local_endpoint", "") or ""
        custom_model = self.database.get_setting("custom_model", "") or ""
        local_model = self.database.get_setting("local_model", "") or ""

        if profile.id == "local":
            if local_endpoint:
                profile.endpoint_override = local_endpoint
                profile.backend_base_url = local_endpoint
            if local_model:
                profile.model_name = local_model
        if profile.id == "custom":
            if custom_endpoint:
                profile.endpoint_override = custom_endpoint
                profile.backend_base_url = custom_endpoint
            if custom_model:
                profile.model_name = custom_model
        if profile.id == "demo":
            # Demo model can be overridden by settings (optional) but no demo key is stored in Settings.
            demo_model = self.database.get_setting("demo_model", "") or ""
            if demo_model:
                profile.model_name = demo_model

        profile.token_present = self.credential_store.has(profile.id)
        return profile

    def resolve_startup_profile(self, cli_profile_id: str | None) -> ProviderConfig:
        if cli_profile_id:
            return self.set_active_profile(cli_profile_id)
        return self.load_active_profile()

    def get_settings(self) -> SettingsState:
        profile = self.load_active_profile()
        tts_enabled = (self.database.get_setting("tts_enabled", "false") or "false").lower() == "true"
        screen_share_enabled = (self.database.get_setting("screen_share_enabled", "true") or "true").lower() == "true"
        activity_recording_enabled = (self.database.get_setting("activity_recording_enabled", "true") or "true").lower() == "true"
        activity_sampling_hz = float(self.database.get_setting("activity_sampling_hz", "1.0") or "1.0")
        activity_max_duration_seconds = int(self.database.get_setting("activity_max_duration_seconds", "60") or "60")
        guided_task_enabled = (self.database.get_setting("guided_task_enabled", "true") or "true").lower() == "true"
        guided_overlay_style = self.database.get_setting("guided_overlay_style", "arrow_pulse") or "arrow_pulse"
        guided_auto_advance_sensitivity = float(self.database.get_setting("guided_auto_advance_sensitivity", "0.85") or "0.85")
        guided_completion_mode = self.database.get_setting("guided_completion_mode", "conservative") or "conservative"
        guided_max_planning_steps = int(self.database.get_setting("guided_max_planning_steps", "6") or "6")
        guided_show_debug_labels = (self.database.get_setting("guided_show_debug_labels", "false") or "false").lower() == "true"
        custom_endpoint = self.database.get_setting("custom_endpoint", "")
        local_endpoint = self.database.get_setting("local_endpoint", "")
        custom_model = self.database.get_setting("custom_model", "")
        local_model = self.database.get_setting("local_model", "")
        local_model_path = self.database.get_setting("local_model_path", "")
        demo_model = self.database.get_setting("demo_model", "")
        onboarding_complete = (self.database.get_setting("onboarding_complete", "false") or "false").lower() == "true"
        return SettingsState(
            active_profile_id=profile.id,
            tts_enabled=tts_enabled,
            screen_share_enabled=screen_share_enabled,
            activity_recording_enabled=activity_recording_enabled,
            activity_sampling_hz=activity_sampling_hz,
            activity_max_duration_seconds=activity_max_duration_seconds,
            guided_task_enabled=guided_task_enabled,
            guided_overlay_style=guided_overlay_style,
            guided_auto_advance_sensitivity=guided_auto_advance_sensitivity,
            guided_completion_mode=guided_completion_mode,
            guided_max_planning_steps=guided_max_planning_steps,
            guided_show_debug_labels=guided_show_debug_labels,
            secure_storage_warning=self.credential_store.warning,
            custom_endpoint=custom_endpoint or None,
            custom_token_present=self.credential_store.has("custom"),
            local_endpoint=local_endpoint or None,
            local_token_present=self.credential_store.has("local"),
            local_model=local_model or None,
            local_model_path=local_model_path or None,
            custom_model=custom_model or None,
            demo_model=demo_model or None,
            onboarding_complete=onboarding_complete,
        )

    def update_settings(
        self,
        *,
        active_profile_id: str | None = None,
        tts_enabled: bool | None = None,
        screen_share_enabled: bool | None = None,
        activity_recording_enabled: bool | None = None,
        activity_sampling_hz: float | None = None,
        activity_max_duration_seconds: int | None = None,
        guided_task_enabled: bool | None = None,
        guided_overlay_style: str | None = None,
        guided_auto_advance_sensitivity: float | None = None,
        guided_completion_mode: str | None = None,
        guided_max_planning_steps: int | None = None,
        guided_show_debug_labels: bool | None = None,
        custom_endpoint: str | None = None,
        local_endpoint: str | None = None,
        custom_model: str | None = None,
        local_model: str | None = None,
        local_model_path: str | None = None,
        demo_model: str | None = None,
        onboarding_complete: bool | None = None,
    ) -> SettingsState:
        if active_profile_id:
            self.database.set_setting("active_profile_id", active_profile_id)
        if tts_enabled is not None:
            self.database.set_setting("tts_enabled", str(tts_enabled).lower())
        if screen_share_enabled is not None:
            self.database.set_setting("screen_share_enabled", str(screen_share_enabled).lower())
        if activity_recording_enabled is not None:
            self.database.set_setting("activity_recording_enabled", str(activity_recording_enabled).lower())
        if activity_sampling_hz is not None:
            self.database.set_setting("activity_sampling_hz", f"{activity_sampling_hz}")
        if activity_max_duration_seconds is not None:
            self.database.set_setting("activity_max_duration_seconds", str(activity_max_duration_seconds))
        if guided_task_enabled is not None:
            self.database.set_setting("guided_task_enabled", str(guided_task_enabled).lower())
        if guided_overlay_style is not None:
            self.database.set_setting("guided_overlay_style", guided_overlay_style)
        if guided_auto_advance_sensitivity is not None:
            self.database.set_setting("guided_auto_advance_sensitivity", f"{guided_auto_advance_sensitivity}")
        if guided_completion_mode is not None:
            self.database.set_setting("guided_completion_mode", guided_completion_mode)
        if guided_max_planning_steps is not None:
            self.database.set_setting("guided_max_planning_steps", str(guided_max_planning_steps))
        if guided_show_debug_labels is not None:
            self.database.set_setting("guided_show_debug_labels", str(guided_show_debug_labels).lower())
        if custom_endpoint is not None:
            self.database.set_setting("custom_endpoint", custom_endpoint)
        if local_endpoint is not None:
            self.database.set_setting("local_endpoint", local_endpoint)
        if custom_model is not None:
            self.database.set_setting("custom_model", custom_model)
        if local_model is not None:
            self.database.set_setting("local_model", local_model)
        if local_model_path is not None:
            self.database.set_setting("local_model_path", local_model_path)
        if demo_model is not None:
            self.database.set_setting("demo_model", demo_model)
        if onboarding_complete is not None:
            self.database.set_setting("onboarding_complete", str(onboarding_complete).lower())
        return self.get_settings()
