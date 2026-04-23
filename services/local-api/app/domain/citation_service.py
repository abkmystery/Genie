from __future__ import annotations

from app.models.contracts import EvidenceItem, RegionContext, ScreenContext


class CitationService:
    def merge(
        self,
        source_evidence: list[EvidenceItem],
        screen_context: ScreenContext | None = None,
        region_context: RegionContext | None = None,
    ) -> list[EvidenceItem]:
        evidence = list(source_evidence)
        if screen_context:
            evidence.insert(
                0,
                EvidenceItem(
                    id=screen_context.capture.id,
                    label="[Screen]",
                    kind="screen",
                    quote=screen_context.text[:220],
                    locator=screen_context.capture.path,
                ),
            )
        if region_context:
            evidence.insert(
                0,
                EvidenceItem(
                    id=region_context.capture.id,
                    label="[Region]",
                    kind="region",
                    quote=region_context.text[:220],
                    locator=region_context.capture.path,
                ),
            )
        return evidence

