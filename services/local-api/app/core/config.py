from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
SERVICE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    db_path: Path
    profile_config_dir: Path
    resources_dir: Path
    demo_gateway_url: str
    default_profile_id: str = "demo"


def load_config() -> AppConfig:
    def resolve_path(env_key: str, default_rel: str) -> Path:
        raw = os.getenv(env_key, "").strip()
        if raw:
            candidate = Path(raw)
            return candidate if candidate.is_absolute() else (ROOT_DIR / candidate)
        return ROOT_DIR / default_rel

    data_dir = resolve_path("GENIE_DATA_DIR", "services/local-api/data")
    db_path = resolve_path("GENIE_DB_PATH", "services/local-api/data/genie.db")
    profile_config_dir = resolve_path("GENIE_PROFILE_CONFIG_DIR", "config/profiles")
    resources_dir = resolve_path("GENIE_RESOURCES_DIR", "resources")
    demo_gateway_url = os.getenv("GENIE_DEMO_GATEWAY_URL", "http://127.0.0.1:8788")

    data_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # resources_dir may be inside packaged app resources (read-only). Do not attempt to create it.

    return AppConfig(
        data_dir=data_dir,
        db_path=db_path,
        profile_config_dir=profile_config_dir,
        resources_dir=resources_dir,
        demo_gateway_url=demo_gateway_url,
    )
