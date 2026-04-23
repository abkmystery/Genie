from __future__ import annotations

from app.models.contracts import EvidenceItem, RegionContext, ScreenContext


def fallback_grounded_answer(
    prompt: str,
    evidence: list[EvidenceItem],
    screen_context: ScreenContext | None,
    region_context: RegionContext | None,
) -> str:
    def clean_quote(value: str | None) -> str:
        return " ".join((value or "").strip().split())

    quoted_items = [item for item in evidence if clean_quote(item.quote)]
    source_quotes = [item for item in quoted_items if item.label.startswith("[Source:")]
    visual_quotes = [item for item in quoted_items if item.label in {"[Screen]", "[Region]"}]

    if source_quotes:
        lead = clean_quote(source_quotes[0].quote)
        response = [f"Based on your sources, the clearest matching evidence says: {lead}"]
        if len(source_quotes) > 1:
            response.append("I also found supporting details in other attached material.")
        if visual_quotes:
            response.append("I considered the current screen context too.")
        response.append("Ask a narrower follow-up if you want me to summarize or explain it further.")
        return " ".join(response)

    if visual_quotes:
        lead = clean_quote(visual_quotes[0].quote)
        return (
            f"I found readable content in the captured screen or selected region: {lead} "
            "Ask a specific follow-up and I can focus on that content."
        )

    if region_context:
        return (
            "I captured the selected region, but I do not have enough readable text from it to answer confidently. "
            "Try selecting a tighter area with visible text, or make sure the live demo provider is active instead of the offline fallback."
        )

    if screen_context:
        return (
            "I captured your screen, but I do not have enough readable on-screen text to answer confidently in fallback mode. "
            "That usually means the live demo provider is not active or OCR could not extract usable text from the image."
        )

    return (
        "I do not have enough grounded evidence yet to answer that confidently. "
        "Attach a file, select a region, or ask about visible text on the screen and I will use that evidence."
    )
