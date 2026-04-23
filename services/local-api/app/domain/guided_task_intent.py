from __future__ import annotations


_GUIDANCE_PHRASES = (
    "guide me through",
    "show me where to click",
    "help me do this step by step",
    "point to the next step",
    "walk me through this",
    "tell me exactly where to click",
    "guide me",
)


def parse_guided_task_prompt(prompt: str) -> dict[str, object] | None:
    lowered = prompt.lower().strip()
    if not lowered:
        return None
    if any(phrase in lowered for phrase in _GUIDANCE_PHRASES):
        return {"intent": "start", "goal": prompt.strip()}
    if lowered in {"stop guidance", "stop guiding me"}:
        return {"intent": "stop"}
    if lowered in {"pause guidance", "pause guide"}:
        return {"intent": "pause"}
    if lowered in {"resume guidance", "resume guide"}:
        return {"intent": "resume"}
    if lowered in {"next step", "mark this done", "i did it"}:
        return {"intent": "advance"}
    return None
