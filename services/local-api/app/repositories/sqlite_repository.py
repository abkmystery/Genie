from __future__ import annotations

import json
from datetime import datetime

from app.core.database import Database
from app.core.text_matching import terms
from app.models.contracts import SourceChunk, SourceRecord, TraceEvent
from app.providers.interfaces import RetrievalEngine, SourceRepository, TraceLogger


class SQLiteSourceRepository(SourceRepository):
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_source(self, source: SourceRecord, chunks: list[SourceChunk]) -> None:
        with self.database.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sources
                (id, filename, content_type, path, status, size_bytes, chunk_count, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.filename,
                    source.content_type,
                    source.path,
                    source.status,
                    source.size_bytes,
                    source.chunk_count,
                    source.error,
                    source.created_at.isoformat(),
                    source.updated_at.isoformat(),
                ),
            )
            conn.execute("DELETE FROM chunks WHERE source_id = ?", (source.id,))
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (id, source_id, ordinal, text, locator, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.source_id,
                        chunk.ordinal,
                        chunk.text,
                        chunk.locator,
                        json.dumps(chunk.metadata),
                    ),
                )
            conn.commit()

    def list_sources(self) -> list[SourceRecord]:
        with self.database.connection() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY updated_at DESC").fetchall()
        return [SourceRecord(**dict(row)) for row in rows]

    def get_source(self, source_id: str) -> SourceRecord | None:
        with self.database.connection() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return SourceRecord(**dict(row)) if row else None

    def list_chunks(self, source_ids: list[str] | None = None) -> list[SourceChunk]:
        query = "SELECT * FROM chunks"
        params: tuple[object, ...] = ()
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            query += f" WHERE source_id IN ({placeholders})"
            params = tuple(source_ids)
        query += " ORDER BY source_id, ordinal"
        with self.database.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            SourceChunk(
                id=row["id"],
                source_id=row["source_id"],
                ordinal=row["ordinal"],
                text=row["text"],
                locator=row["locator"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def delete_source(self, source_id: str) -> None:
        with self.database.connection() as conn:
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            conn.commit()


class KeywordRetrievalEngine(RetrievalEngine):
    def __init__(self, repository: SourceRepository) -> None:
        self.repository = repository

    def retrieve(self, prompt: str, source_ids: list[str] | None = None, limit: int = 6) -> list[tuple[SourceChunk, float]]:
        prompt_terms = terms(prompt)
        if not prompt_terms:
            return []
        scored: list[tuple[SourceChunk, float]] = []
        for chunk in self.repository.list_chunks(source_ids):
            overlap = len(prompt_terms & terms(chunk.text))
            if overlap:
                scored.append((chunk, overlap / max(1, len(prompt_terms))))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


class SQLiteTraceLogger(TraceLogger):
    def __init__(self, database: Database) -> None:
        self.database = database

    def emit(self, event: TraceEvent) -> None:
        with self.database.connection() as conn:
            conn.execute(
                """
                INSERT INTO trace_events (id, trace_id, type, message, metadata_json, created_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.trace_id,
                    event.type,
                    event.message,
                    json.dumps(event.metadata),
                    event.created_at.isoformat(),
                    event.duration_ms,
                ),
            )
            conn.commit()

    def list_events(self, trace_id: str) -> list[TraceEvent]:
        with self.database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trace_events WHERE trace_id = ? ORDER BY created_at ASC",
                (trace_id,),
            ).fetchall()
        return [
            TraceEvent(
                id=row["id"],
                trace_id=row["trace_id"],
                type=row["type"],
                message=row["message"],
                metadata=json.loads(row["metadata_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]
