from __future__ import annotations

import base64
import importlib.util
import subprocess
import tempfile
import threading
from pathlib import Path

from app.providers.interfaces import SpeechToTextProvider, TextToSpeechProvider, WakeWordProvider
from app.providers.openai_compatible import OpenAICompatibleClient


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


class UnavailableSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        if transcript_hint:
            return transcript_hint
        raise RuntimeError(self.reason)

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "unavailable",
            "available": False,
            "offline": True,
            "reason": self.reason,
        }


class OpenAICompatibleSpeechToTextProvider(SpeechToTextProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        bearer_token: str | None = None,
        provider_label: str = "openai-compatible-audio",
        timeout_ms: int = 30000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.bearer_token = (bearer_token or "").strip()
        self.provider_label = provider_label
        self.timeout_ms = timeout_ms

    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        if transcript_hint:
            return transcript_hint
        if not audio_base64:
            raise RuntimeError("No audio payload was provided to the model-backed STT provider.")

        client = OpenAICompatibleClient(
            base_url=self.base_url,
            bearer_token=self.bearer_token,
            timeout_s=max(5, self.timeout_ms / 1000),
        )
        transcript = await client.chat_completions(
            {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Transcribe this audio. Return only the spoken transcript text. "
                                    "Do not add labels, commentary, or extra explanation."
                                ),
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_base64,
                                    "format": (audio_format or "wav").lower(),
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0,
                "max_tokens": 256,
            }
        )
        transcript = transcript.strip()
        if not transcript:
            raise RuntimeError("The local audio model returned an empty transcript.")
        return transcript

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": self.provider_label,
            "available": bool(self.base_url and self.model_name),
            "offline": self.base_url.startswith("http://127.0.0.1") or self.base_url.startswith("http://localhost"),
            "base_url": self.base_url,
            "model": self.model_name,
            "token_configured": bool(self.bearer_token),
        }


class CascadingSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, providers: list[SpeechToTextProvider]) -> None:
        self.providers = providers

    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        if transcript_hint:
            return transcript_hint
        errors: list[str] = []
        for provider in self.providers:
            try:
                text = await provider.transcribe(
                    audio_base64=audio_base64,
                    audio_format=audio_format,
                    transcript_hint=None,
                )
                if text.strip():
                    return text.strip()
            except Exception as exc:
                provider_name = str(provider.diagnostics().get("provider") or provider.__class__.__name__)
                errors.append(f"{provider_name}: {exc}")
        raise RuntimeError("; ".join(errors) if errors else "No speech-to-text provider is configured.")

    def diagnostics(self) -> dict[str, object]:
        provider_details = [provider.diagnostics() for provider in self.providers]
        return {
            "provider": "cascade",
            "available": any(bool(item.get("available")) for item in provider_details),
            "offline": all(bool(item.get("offline")) for item in provider_details if item.get("available")),
            "providers": provider_details,
        }


class OptionalWhisperSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, model_name: str = "tiny", download_root: Path | None = None) -> None:
        self._has_faster_whisper = _module_available("faster_whisper")
        self._has_whisper = _module_available("whisper")
        self.model_name = model_name
        self.download_root = download_root

    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        if transcript_hint:
            return transcript_hint
        if not audio_base64:
            raise RuntimeError("No audio payload was provided to the local STT provider.")

        suffix = f".{audio_format or 'wav'}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
            handle.write(base64.b64decode(audio_base64))

        try:
            attempted_provider = False
            provider_errors: list[str] = []
            if self._has_faster_whisper:
                attempted_provider = True
                from faster_whisper import WhisperModel  # type: ignore

                try:
                    model = WhisperModel(self.model_name, device="cpu", compute_type="int8", download_root=str(self.download_root) if self.download_root else None)
                    segments, _info = model.transcribe(str(temp_path))
                    text = " ".join(segment.text.strip() for segment in segments).strip()
                    if text:
                        return text
                except Exception as exc:
                    provider_errors.append(f"faster-whisper: {type(exc).__name__}: {exc}")
            if self._has_whisper:
                attempted_provider = True
                import whisper  # type: ignore

                try:
                    model = whisper.load_model(self.model_name, download_root=str(self.download_root) if self.download_root else None)
                    result = model.transcribe(str(temp_path))
                    text = str(result.get("text") or "").strip()
                    if text:
                        return text
                except Exception as exc:
                    provider_errors.append(f"whisper: {type(exc).__name__}: {exc}")
            if provider_errors:
                raise RuntimeError("; ".join(provider_errors))
            if attempted_provider:
                raise RuntimeError("No speech detected in the recording.")
            raise RuntimeError("No supported local Whisper package is available for transcription.")
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "local-whisper",
            "available": self._has_faster_whisper or self._has_whisper,
            "offline": True,
            "model": self.model_name,
            "packages": {
                "faster_whisper": self._has_faster_whisper,
                "whisper": self._has_whisper,
            },
        }


class MockSpeechToTextProvider(SpeechToTextProvider):
    async def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        transcript_hint: str | None = None,
    ) -> str:
        if transcript_hint:
            return transcript_hint
        raise RuntimeError("Mock STT provider is active. No local speech-to-text engine is configured.")

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "mock",
            "available": False,
            "offline": True,
            "reason": "No supported local STT package was detected.",
        }


class PowerShellSpeechTtsProvider(TextToSpeechProvider):
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    async def speak(self, text: str) -> dict[str, object]:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$synth.Speak([Console]::In.ReadToEnd())"
        )
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.kill()
            self._process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            process = self._process

        stdout, stderr = process.communicate(input=text)
        with self._lock:
            if self._process is process:
                self._process = None
        if process.returncode != 0:
            return {
                "spoken": False,
                "mode": "powershell-tts",
                "message": (stderr or stdout or "PowerShell speech synthesis failed.").strip(),
                "preview": text[:120],
            }
        return {
            "spoken": True,
            "mode": "powershell-tts",
            "message": "Spoken with the Windows System.Speech voice.",
            "preview": text[:120],
        }

    async def stop(self) -> dict[str, object]:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.kill()
                self._process = None
                return {"stopped": True, "mode": "powershell-tts", "message": "Speech stopped."}
        return {"stopped": False, "mode": "powershell-tts", "message": "No active speech playback."}

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "powershell-system-speech",
            "available": True,
            "offline": True,
        }


class OptionalPyttsx3TextToSpeechProvider(TextToSpeechProvider):
    def __init__(self) -> None:
        self.available = _module_available("pyttsx3")
        self._engine = None
        self._lock = threading.Lock()

    async def speak(self, text: str) -> dict[str, object]:
        if not self.available:
            raise RuntimeError("pyttsx3 is not installed.")
        import pyttsx3  # type: ignore

        with self._lock:
            if self._engine is None:
                self._engine = pyttsx3.init()
            engine = self._engine
        engine.say(text)
        engine.runAndWait()
        return {
            "spoken": True,
            "mode": "pyttsx3",
            "message": "Spoken with pyttsx3.",
            "preview": text[:120],
        }

    async def stop(self) -> dict[str, object]:
        if not self.available:
            return {"stopped": False, "mode": "pyttsx3", "message": "pyttsx3 is not installed."}
        with self._lock:
            if self._engine is None:
                return {"stopped": False, "mode": "pyttsx3", "message": "No active speech playback."}
            self._engine.stop()
        return {"stopped": True, "mode": "pyttsx3", "message": "Speech stopped."}

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "pyttsx3",
            "available": self.available,
            "offline": True,
        }


class MockTextToSpeechProvider(TextToSpeechProvider):
    async def speak(self, text: str) -> dict[str, object]:
        return {
            "spoken": False,
            "mode": "mock",
            "message": "Text-to-speech is running in mock mode in this environment.",
            "preview": text[:120],
        }

    async def stop(self) -> dict[str, object]:
        return {
            "stopped": False,
            "mode": "mock",
            "message": "No active speech playback.",
        }

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "mock",
            "available": False,
            "offline": True,
            "reason": "No supported local TTS engine was detected.",
        }


class DisabledWakeWordProvider(WakeWordProvider):
    def is_enabled(self) -> bool:
        return False
