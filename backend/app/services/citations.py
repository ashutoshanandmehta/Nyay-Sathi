"""Resolve visible source markers against the passages actually retrieved.

The supported-marker resolution approach is adapted from LawGlance's Apache-2.0
`citations.py`; Nyay Saathi uses its own title/locator marker and passage schema.
"""

import re
from dataclasses import dataclass
from typing import Any

MARKER = re.compile(r"\[Source:\s*(?P<title>[^\]—]+?)\s+—\s+(?P<locator>[^\]]+?)\]")


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def canonicalise_source_markers(answer: str, passages: list[dict[str, Any]]) -> str:
    """Repair identity-only formatting before semantic review, never invent support.

    A title + exact fetched URL may be rewritten to its stored locator only when
    that pair resolves to one source/locator. Unknown or ambiguous markers stay
    unchanged and fail the normal hard gate.
    """

    def replace(match):
        matches = [
            p
            for p in passages
            if _normalise(p.get("title", "")) == _normalise(match.group("title"))
            and p.get("canonical_url") == match.group("locator").strip()
        ]
        identities = {(p["source_id"], p["title"], p["locator"]) for p in matches}
        if len(identities) == 1:
            _, title, locator = next(iter(identities))
            return f"[Source: {title} — {locator}]"
        return match.group(0)

    return MARKER.sub(replace, answer)


@dataclass(frozen=True)
class CitationResolution:
    cited_passage_ids: tuple[str, ...]
    unsupported_markers: tuple[str, ...]


def resolve_citations(answer: str, passages: list[dict[str, Any]]) -> CitationResolution:
    """Match every visible marker to an exact retrieved title and locator."""
    supported = {
        (_normalise(str(item.get("title", ""))), _normalise(str(item.get("locator", "")))): str(
            item.get("passage_id", "")
        )
        for item in passages
    }
    cited: list[str] = []
    unsupported: list[str] = []
    for match in MARKER.finditer(answer):
        key = (_normalise(match.group("title")), _normalise(match.group("locator")))
        passage_id = supported.get(key)
        if passage_id:
            cited.append(passage_id)
        else:
            unsupported.append(match.group(0))
    return CitationResolution(tuple(dict.fromkeys(cited)), tuple(unsupported))
