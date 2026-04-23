from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.contracts import AttachmentRecord, SourceChunk


@dataclass
class _SessionAttachment:
    record: AttachmentRecord
    chunks: list[SourceChunk]
    path: Path


class SessionService:
    def __init__(self) -> None:
        self._messages: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._attachments: dict[str, dict[str, _SessionAttachment]] = defaultdict(dict)

    def ensure_conversation(self, conversation_id: str | None) -> str:
        return conversation_id or str(uuid4())

    def add_turn(self, conversation_id: str, role: str, text: str) -> None:
        self._messages[conversation_id].append({"role": role, "text": text})

    def get_messages(self, conversation_id: str) -> list[dict[str, str]]:
        return list(self._messages.get(conversation_id, []))

    def add_attachment(self, attachment: _SessionAttachment) -> None:
        self._attachments[attachment.record.conversation_id][attachment.record.id] = attachment

    def list_attachments(self, conversation_id: str) -> list[AttachmentRecord]:
        attachments = self._attachments.get(conversation_id, {})
        return [item.record for item in attachments.values()]

    def list_attachment_chunks(self, conversation_id: str) -> list[SourceChunk]:
        attachments = self._attachments.get(conversation_id, {})
        chunks: list[SourceChunk] = []
        for item in attachments.values():
            chunks.extend(item.chunks)
        return chunks

    def delete_attachment(self, conversation_id: str, attachment_id: str) -> None:
        attachments = self._attachments.get(conversation_id, {})
        item = attachments.pop(attachment_id, None)
        if item and item.path.exists():
            try:
                item.path.unlink()
            except Exception:
                return


def build_attachment_record(
    *,
    attachment_id: str,
    conversation_id: str,
    filename: str,
    content_type: str,
    status: str,
    chunk_count: int,
    error: str | None = None,
) -> AttachmentRecord:
    return AttachmentRecord(
        id=attachment_id,
        conversation_id=conversation_id,
        filename=filename,
        content_type=content_type,
        status=status,
        chunk_count=chunk_count,
        error=error,
        created_at=datetime.now(timezone.utc),
    )
