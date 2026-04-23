from __future__ import annotations

import json
from pathlib import Path

from app.models.contracts import ProviderConfig
from app.providers.interfaces import ProfileConfigLoader


class JsonProfileConfigLoader(ProfileConfigLoader):
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def list_profiles(self) -> list[ProviderConfig]:
        profiles: list[ProviderConfig] = []
        for profile_id in ("demo", "local", "custom"):
            profiles.append(self.get_profile(profile_id))
        return profiles

    def get_profile(self, profile_id: str) -> ProviderConfig:
        if profile_id == "custom":
            path = self.config_dir / "custom.example.json"
        else:
            path = self.config_dir / f"{profile_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if profile_id == "custom" and data["backend_base_url"].startswith("https://example.invalid"):
            data["backend_base_url"] = ""
            data["model_name"] = "gemma-4-26b-a4b-it"
        return ProviderConfig(**data)
