from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.providers.interfaces import SecureCredentialStore

try:
    import keyring
except Exception:  # pragma: no cover - import failure is a runtime fallback path
    keyring = None


SERVICE_NAME = "genie-local-api"


class KeyringCredentialStore(SecureCredentialStore):
    def __init__(self) -> None:
        if keyring is None:
            raise RuntimeError("keyring unavailable")

    def save(self, provider_id: str, secret_payload: dict[str, Any]) -> None:
        keyring.set_password(SERVICE_NAME, provider_id, json.dumps(secret_payload))

    def get(self, provider_id: str) -> dict[str, Any] | None:
        value = keyring.get_password(SERVICE_NAME, provider_id)
        return json.loads(value) if value else None

    def delete(self, provider_id: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, provider_id)
        except Exception:
            return

    def has(self, provider_id: str) -> bool:
        return self.get(provider_id) is not None

    @property
    def mode(self) -> str:
        return "os-keyring"

    @property
    def warning(self) -> str | None:
        return None


class FileCredentialStore(SecureCredentialStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save(self, provider_id: str, secret_payload: dict[str, Any]) -> None:
        payload = self._load()
        payload[provider_id] = secret_payload
        self._save(payload)

    def get(self, provider_id: str) -> dict[str, Any] | None:
        return self._load().get(provider_id)

    def delete(self, provider_id: str) -> None:
        payload = self._load()
        payload.pop(provider_id, None)
        self._save(payload)

    def has(self, provider_id: str) -> bool:
        return provider_id in self._load()

    @property
    def mode(self) -> str:
        return "dev-file"

    @property
    def warning(self) -> str | None:
        return "Secure OS storage is unavailable. Genie is using a development-only local credential file store."


def build_credential_store(base_path: Path) -> SecureCredentialStore:
    try:
        return KeyringCredentialStore()
    except Exception:
        return FileCredentialStore(base_path / "credentials.dev.json")

