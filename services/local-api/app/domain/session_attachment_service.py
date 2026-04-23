from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from uuid import uuid4

from app.domain.session_service import _SessionAttachment, build_attachment_record
from app.models.contracts import AttachmentRecord, SourceChunk
from app.providers.source_parsers import ParserRegistry
from app.domain.session_service import SessionService


class SessionAttachmentService:
    def __init__(self, session_service: SessionService, parser_registry: ParserRegistry, data_dir: Path) -> None:
        self.session_service = session_service
        self.parser_registry = parser_registry
        self.base_dir = data_dir / "session_attachments"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def add_files(self, conversation_id: str, upload_paths: list[tuple[Path, str | None]]) -> list[AttachmentRecord]:
        records: list[AttachmentRecord] = []
        convo_dir = self.base_dir / conversation_id
        convo_dir.mkdir(parents=True, exist_ok=True)

        for upload_path, original_filename in upload_paths:
            attachment_id = str(uuid4())
            stored_name = f"{attachment_id}-{(original_filename or upload_path.name)}"
            destination = convo_dir / stored_name
            shutil.copy2(upload_path, destination)

            content_type = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
            try:
                parser = self.parser_registry.get_parser(destination)
                chunks = parser.parse(destination)
                for ordinal, chunk in enumerate(chunks):
                    chunk.source_id = attachment_id
                    chunk.ordinal = ordinal

                record = build_attachment_record(
                    attachment_id=attachment_id,
                    conversation_id=conversation_id,
                    filename=original_filename or upload_path.name,
                    content_type=content_type,
                    status="indexed",
                    chunk_count=len(chunks),
                )
                self.session_service.add_attachment(_SessionAttachment(record=record, chunks=chunks, path=destination))
                records.append(record)
            except Exception as exc:
                record = build_attachment_record(
                    attachment_id=attachment_id,
                    conversation_id=conversation_id,
                    filename=original_filename or upload_path.name,
                    content_type=content_type,
                    status="failed",
                    chunk_count=0,
                    error=str(exc),
                )
                self.session_service.add_attachment(_SessionAttachment(record=record, chunks=[], path=destination))
                records.append(record)

        return records

    def list(self, conversation_id: str) -> list[AttachmentRecord]:
        return self.session_service.list_attachments(conversation_id)

    def delete(self, conversation_id: str, attachment_id: str) -> None:
        self.session_service.delete_attachment(conversation_id, attachment_id)

    def list_chunks(self, conversation_id: str) -> list[SourceChunk]:
        return self.session_service.list_attachment_chunks(conversation_id)
