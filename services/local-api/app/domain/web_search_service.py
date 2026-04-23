from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from urllib.parse import quote, urlparse
import re

import httpx

from app.models.contracts import EvidenceItem


_WEB_HINTS = {
    "current",
    "currently",
    "latest",
    "today",
    "news",
    "recent",
    "recently",
    "price",
    "stock",
    "weather",
    "forecast",
    "version",
    "release",
    "update",
    "updated",
    "score",
    "standing",
    "standings",
    "election",
    "president",
    "ceo",
}


def should_search_web(prompt: str) -> bool:
    lowered = prompt.lower()
    if any(token in lowered for token in _WEB_HINTS):
        return True
    patterns = [
        r"\bwhat(?:'s| is) the weather\b",
        r"\bwho is the (?:current|latest)\b",
        r"\bwhat(?:'s| is) the latest\b",
        r"\bnews about\b",
        r"\bhow much is\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


@dataclass
class WebSearchResult:
    title: str
    snippet: str
    url: str


class WebSearchService:
    async def search(self, prompt: str, *, limit: int = 3) -> list[EvidenceItem]:
        results = await self._search_duckduckgo(prompt, limit=limit)
        evidence: list[EvidenceItem] = []
        for index, item in enumerate(results, start=1):
            host = urlparse(item.url).netloc or "web"
            quote = item.snippet.strip() or item.title.strip()
            evidence.append(
                EvidenceItem(
                    id=f"web-{index}-{host}",
                    label=f"[Web: {host}]",
                    kind="source",
                    quote=quote[:220],
                    locator=item.url,
                    score=0.6 - (index * 0.05),
                )
            )
        return evidence

    async def _search_duckduckgo(self, prompt: str, *, limit: int) -> list[WebSearchResult]:
        headers = {
            "User-Agent": "Genie/0.1.0 (+desktop assistant)",
        }
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            instant = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": prompt,
                    "format": "json",
                    "no_redirect": "1",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            instant.raise_for_status()
            data = instant.json()

            direct_results: list[WebSearchResult] = []
            abstract = (data.get("AbstractText") or "").strip()
            abstract_url = (data.get("AbstractURL") or "").strip()
            heading = (data.get("Heading") or prompt).strip()
            if abstract and abstract_url:
                direct_results.append(WebSearchResult(title=heading, snippet=abstract, url=abstract_url))

            related = data.get("RelatedTopics") or []
            for item in related:
                if len(direct_results) >= limit:
                    break
                if "Topics" in item:
                    for nested in item.get("Topics") or []:
                        if len(direct_results) >= limit:
                            break
                        text = (nested.get("Text") or "").strip()
                        url = (nested.get("FirstURL") or "").strip()
                        if text and url:
                            direct_results.append(WebSearchResult(title=text.split(" - ")[0], snippet=text, url=url))
                else:
                    text = (item.get("Text") or "").strip()
                    url = (item.get("FirstURL") or "").strip()
                    if text and url:
                        direct_results.append(WebSearchResult(title=text.split(" - ")[0], snippet=text, url=url))

            if direct_results:
                return direct_results[:limit]

            html_response = await client.get(f"https://duckduckgo.com/html/?q={quote(prompt)}")
            html_response.raise_for_status()
            html = html_response.text

        matches = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned: list[WebSearchResult] = []
        for url, title, snippet in matches[:limit]:
            cleaned.append(
                WebSearchResult(
                    title=_strip_html(title),
                    snippet=_strip_html(snippet),
                    url=unescape(url),
                )
            )
        return cleaned


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return " ".join(text.split())
