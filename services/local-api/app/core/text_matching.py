from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "button",
    "by",
    "can",
    "do",
    "field",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "please",
    "that",
    "the",
    "this",
    "to",
    "what",
    "whats",
    "where",
    "who",
    "why",
    "you",
    "your",
}


def terms(value: str) -> set[str]:
    """Normalize user, source, OCR, and UI text into comparable keywords."""

    return {token for token in _WORD_RE.findall(value.lower()) if token and token not in _STOPWORDS}
