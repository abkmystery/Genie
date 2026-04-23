from __future__ import annotations

from app.models.contracts import EvidenceItem
from app.providers.interfaces import RetrievalEngine, SourceRepository


class RetrievalService:
    def __init__(self, engine: RetrievalEngine, repository: SourceRepository) -> None:
        self.engine = engine
        self.repository = repository

    def retrieve_evidence(self, prompt: str, source_ids: list[str] | None = None) -> list[EvidenceItem]:
        matches = self.engine.retrieve(prompt, source_ids=source_ids, limit=6)
        evidence: list[EvidenceItem] = []
        for chunk, score in matches:
            source = self.repository.get_source(chunk.source_id)
            filename = source.filename if source else chunk.source_id
            label = f"[Source: {filename}"
            if chunk.locator:
                label += f" {chunk.locator}"
            label += "]"
            evidence.append(
                EvidenceItem(
                    id=chunk.id,
                    label=label,
                    kind="source",
                    quote=chunk.text[:220],
                    locator=chunk.locator,
                    score=score,
                )
            )
        return evidence
