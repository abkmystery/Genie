from __future__ import annotations

import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.contracts import SourceRecord
from app.providers.source_parsers import ParserRegistry
from app.providers.interfaces import SourceRepository


class SourceIngestionService:
    def __init__(self, repository: SourceRepository, parser_registry: ParserRegistry, data_dir: Path) -> None:
        self.repository = repository
        self.parser_registry = parser_registry
        self.source_dir = data_dir / "sources"
        self.source_dir.mkdir(parents=True, exist_ok=True)

    def ingest_file(self, upload_path: Path, original_filename: str | None = None) -> SourceRecord:
        source_id = str(uuid4())
        stored_name = f"{source_id}-{(original_filename or upload_path.name)}"
        destination = self.source_dir / stored_name
        shutil.copy2(upload_path, destination)

        now = datetime.now(timezone.utc)
        try:
            parser = self.parser_registry.get_parser(destination)
            chunks = parser.parse(destination)
            for ordinal, chunk in enumerate(chunks):
                chunk.source_id = source_id
                chunk.ordinal = ordinal
            source = SourceRecord(
                id=source_id,
                filename=original_filename or upload_path.name,
                content_type=mimetypes.guess_type(destination.name)[0] or "application/octet-stream",
                path=str(destination),
                status="indexed",
                size_bytes=destination.stat().st_size,
                chunk_count=len(chunks),
                error=None,
                created_at=now,
                updated_at=now,
            )
            self.repository.save_source(source, chunks)
        except Exception as exc:
            source = SourceRecord(
                id=source_id,
                filename=original_filename or upload_path.name,
                content_type=mimetypes.guess_type(destination.name)[0] or "application/octet-stream",
                path=str(destination),
                status="failed",
                size_bytes=destination.stat().st_size,
                chunk_count=0,
                error=str(exc),
                created_at=now,
                updated_at=now,
            )
            self.repository.save_source(source, [])
        return source

    def list_sources(self) -> list[SourceRecord]:
        return self.repository.list_sources()

    def remove_source(self, source_id: str) -> None:
        source = self.repository.get_source(source_id)
        if source:
            path = Path(source.path)
            if path.exists():
                path.unlink()
        self.repository.delete_source(source_id)

    def reindex_source(self, source_id: str) -> SourceRecord:
        source = self.repository.get_source(source_id)
        if not source:
            raise ValueError("Source not found")
        path = Path(source.path)
        try:
            parser = self.parser_registry.get_parser(path)
            chunks = parser.parse(path)
            for ordinal, chunk in enumerate(chunks):
                chunk.source_id = source_id
                chunk.ordinal = ordinal
            updated = source.model_copy(
                update={
                    "status": "indexed",
                    "chunk_count": len(chunks),
                    "updated_at": datetime.now(timezone.utc),
                    "error": None,
                }
            )
            self.repository.save_source(updated, chunks)
        except Exception as exc:
            updated = source.model_copy(
                update={
                    "status": "failed",
                    "chunk_count": 0,
                    "updated_at": datetime.now(timezone.utc),
                    "error": str(exc),
                }
            )
            self.repository.save_source(updated, [])
        return updated
