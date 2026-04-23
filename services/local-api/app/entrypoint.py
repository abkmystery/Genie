from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import uvicorn


def _resolve_logfile() -> Path | None:
    """
    In Windows --noconsole builds, sys.stdout/stderr may be None. Uvicorn's default
    log config uses formatters that call .isatty() on the output stream, which can crash.

    We avoid that by logging to a file only.
    """
    log_dir = os.getenv("GENIE_LOG_DIR", "").strip()
    if not log_dir:
        return None
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        return Path(log_dir) / "local-api.log"
    except Exception:
        return None


def _uvicorn_file_log_config(logfile: Path) -> dict[str, Any]:
    formatter = {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"standard": formatter},
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "formatter": "standard",
                "filename": str(logfile),
                "encoding": "utf-8",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "genie": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
        "root": {"handlers": ["file"], "level": "INFO"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Genie Local API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    # Import the FastAPI app directly so packaging tools (PyInstaller) include it without relying on string imports.
    from app.main import app as fastapi_app  # noqa: WPS433

    logfile = _resolve_logfile()
    log_config = _uvicorn_file_log_config(logfile) if logfile else None
    uvicorn.run(fastapi_app, host=args.host, port=args.port, log_level="info", log_config=log_config, access_log=bool(logfile))


if __name__ == "__main__":
    main()
