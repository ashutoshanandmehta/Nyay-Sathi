"""Split fetched statute text into section passages, so ranking and citation work per section.

Page-sized chunks mix unrelated provisions and lose the section number the verifier checks.
Sections are only accepted in sequence (1, 2, 2A, 3 ... with small gaps for omitted
sections), which keeps arrangement tables and schedules from posing as sections.
"""

import hashlib
import re

ENACTED_RE = re.compile(r"\bbe it enacted\b", re.I)
SECTION_START_RE = re.compile(r"(?m)^[ \t]*(\d{1,3})([A-Z]{0,2})\.[ \t]*(?=\(1\)|\[|[A-Z])")
# "Heading.—Text"; a plain hyphen ("Definitions-In this Act") only when no real dash follows.
HEADING_DASH_RE = re.compile(r"[ \t]*([A-Z][^\n]{1,200}?(?:\n[^\n]{1,120}?)?)\s*[.,]?\s*[–—]")
HEADING_HYPHEN_RE = re.compile(r"[ \t]*([A-Z][^\n]{1,200}?)\s*[.,]?\s*-{1,2}(?=\s*[A-Z(])")
GAZETTE_HEADER_RE = re.compile(r"(?im)^.*\bGAZETTE OF INDIA\b.*$")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
MIN_SECTIONS = 4
MAX_PART_CHARS = 2600
MAX_GAP = 5


def _clean(text: str) -> str:
    text = GAZETTE_HEADER_RE.sub("", text)
    latin = len(re.findall(r"[A-Za-z]", text))
    if latin > 5 * len(DEVANAGARI_RE.findall(text)):
        # English text in a bilingual Gazette: Devanagari lines are page headers.
        text = "\n".join(ln for ln in text.splitlines() if not DEVANAGARI_RE.search(ln))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def split_statute(pages: list[str]) -> list[dict]:
    """Return [{number, heading, page, text}] for an Act's numbered sections, or [] if none."""
    joined, offsets = "", []
    for index, page in enumerate(pages):
        offsets.append((len(joined), index + 1))
        joined += page + "\n"
    enacted = ENACTED_RE.search(joined)
    starts, last = [], None
    for match in SECTION_START_RE.finditer(joined, enacted.end() if enacted else 0):
        key = (int(match.group(1)), match.group(2))
        if last is None:
            if key[0] > MAX_GAP:
                continue
        elif not ((key[0] == last[0] and key[1] > last[1]) or 0 < key[0] - last[0] <= MAX_GAP):
            continue
        starts.append((match, key))
        last = key
    if len(starts) < MIN_SECTIONS:
        return []
    sections = []
    for index, (match, (number, suffix)) in enumerate(starts):
        end = starts[index + 1][0].start() if index + 1 < len(starts) else len(joined)
        heading = HEADING_DASH_RE.match(joined, match.end()) or HEADING_HYPHEN_RE.match(
            joined, match.end()
        )
        sections.append(
            {
                "number": f"{number}{suffix}",
                "heading": re.sub(r"\s+", " ", heading.group(1)).strip().rstrip(".")
                if heading
                else "",
                "page": max(page for offset, page in offsets if offset <= match.start()),
                "text": _clean(joined[match.start() : end]),
            }
        )
    return sections


def _parts(text: str) -> list[str]:
    parts, rest = [], text
    while len(rest) > MAX_PART_CHARS:
        cut = rest.rfind(" ", 0, MAX_PART_CHARS)
        cut = cut if cut > MAX_PART_CHARS // 2 else MAX_PART_CHARS
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return parts + ([rest] if rest else [])


def statute_passages(source: dict, pages: list[str]) -> list[dict]:
    """Section passages in the same shape as rag.ingest.chunk_text, or [] if not a statute."""
    passages = []
    for section in split_statute(pages):
        label = f"Section {section['number']}"
        if section["heading"]:
            label += f": {section['heading']}"
        parts = _parts(section["text"])
        for index, text in enumerate(parts, start=1):
            part = f" (part {index} of {len(parts)})" if len(parts) > 1 else ""
            digest = hashlib.sha256(text.encode()).hexdigest()[:12]
            passages.append(
                {
                    "passage_id": f"{source['source_id']}-s{section['number'].lower()}-{index}-{digest}",
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "locator": f"{label}{part} (page {section['page']})",
                    "text": text,
                    "canonical_url": source["canonical_url"],
                    "retrieved_at": source["retrieved_at"],
                    "limitations": source["known_limitations"],
                    "source_type": source["source_type"],
                    "jurisdiction": source["jurisdiction"],
                    "publication_date": source.get("publication_date"),
                    "effective_date": source.get("effective_date"),
                    "version_information": source.get("version_information"),
                }
            )
    return passages
