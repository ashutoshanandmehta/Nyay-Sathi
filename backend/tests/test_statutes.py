"""Unit tests for statute parsing (app.rag.statutes) and BM25 passage ranking (app.agent.research)."""

from __future__ import annotations

import pytest

from app.agent.research import rank_passages
from app.rag.statutes import _clean, _parts, split_statute, statute_passages


SAMPLE_STATUTE_PAGES = [
    """THE GAZETTE OF INDIA EXTRAORDINARY
PART II — Section 1
PUBLISHED BY AUTHORITY

MINISTRY OF LAW AND JUSTICE
(Legislative Department)

The following Act of Parliament received the assent of the President on the 25th December, 2023:
THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023
No. 46 OF 2023
[25th December, 2023.]
An Act to consolidate and amend the law relating to Criminal Procedure.
BE IT ENACTED by Parliament in the Seventy-fourth Year of the Republic of India as follows:—
CHAPTER I
PRELIMINARY
1. Short title, extent and commencement.—(1) This Act may be called the Bharatiya Nagarik Suraksha Sanhita, 2023.
(2) It extends to the whole of India.
2. Definitions.—(1) In this Sanhita, unless the context otherwise requires,—
(a) "audio-video electronic means" shall include use of any communication device;
(b) "bail" means release of a person accused of an offence from the custody of law.
""",
    """2A. Special provisions for electronic records.—All electronic records shall be preserved in accordance with the rules.
3. Construction of references.—Any reference in any enactment to a Magistrate shall be construed as a Magistrate of the first class.
4. Trial of offences under Bharatiya Nyaya Sanhita, 2023 and other laws.—(1) All offences under the Bharatiya Nyaya Sanhita shall be investigated according to this Sanhita.
""",
]


def test_split_statute_parses_sections_and_headings():
    sections = split_statute(SAMPLE_STATUTE_PAGES)
    assert len(sections) == 5
    assert [s["number"] for s in sections] == ["1", "2", "2A", "3", "4"]
    assert sections[0]["heading"] == "Short title, extent and commencement"
    assert sections[1]["heading"] == "Definitions"
    assert sections[2]["heading"] == "Special provisions for electronic records"
    assert sections[3]["heading"] == "Construction of references"
    assert sections[4]["heading"] == "Trial of offences under Bharatiya Nyaya Sanhita, 2023 and other laws"

    # Page tracking
    assert sections[0]["page"] == 1
    assert sections[1]["page"] == 1
    assert sections[2]["page"] == 2
    assert sections[3]["page"] == 2


def test_split_statute_cleans_gazette_headers_and_bilingual_devanagari():
    bilingual_page = (
        "THE GAZETTE OF INDIA EXTRAORDINARY\n"
        "भारत का राजपत्र\n"
        "BE IT ENACTED by Parliament as follows:—\n"
        "1. First Section.—Text of first section.\n"
        "2. Second Section.—Text of second section.\n"
        "3. Third Section.—Text of third section.\n"
        "4. Fourth Section.—Text of fourth section.\n"
    )
    sections = split_statute([bilingual_page])
    assert len(sections) == 4
    # Gazette header and Devanagari lines stripped from first section
    assert "GAZETTE OF INDIA" not in sections[0]["text"]
    assert "भारत का राजपत्र" not in sections[0]["text"]


def test_split_statute_rejects_non_statutes_under_min_sections():
    # Ordinary text without sections returns empty list
    non_statute = ["This is just a policy report with some numbered points.\n1. Introduction\n2. Background"]
    assert split_statute(non_statute) == []


def test_split_statute_handles_omitted_sections_with_reasonable_gaps():
    pages = [
        "BE IT ENACTED by Parliament as follows:—\n"
        "1. Section One.—Text.\n"
        "2. Section Two.—Text.\n"
        "4. Section Four.—Section three was repealed.\n"
        "5. Section Five.—Final text.\n"
    ]
    sections = split_statute(pages)
    assert len(sections) == 4
    assert [s["number"] for s in sections] == ["1", "2", "4", "5"]


def test_split_statute_rejects_large_unreasonable_gap():
    pages = [
        "BE IT ENACTED by Parliament as follows:—\n"
        "1. Section One.—Text.\n"
        "2. Section Two.—Text.\n"
        "20. Section Twenty.—This is likely a table or appendix.\n"
        "21. Section Twenty One.—Text.\n"
    ]
    sections = split_statute(pages)
    # The jump from 2 to 20 is > MAX_GAP (5), so sections 20 and 21 are rejected, leaving < 4 sections
    assert sections == []


def test_statute_passages_formats_metadata_and_hashes():
    source = {
        "source_id": "bnss-test",
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "canonical_url": "https://mha.gov.in/bnss.pdf",
        "retrieved_at": "2026-11-08T00:00:00Z",
        "known_limitations": "Official publication",
        "source_type": "indian_official",
        "jurisdiction": "India",
        "publication_date": "2023-12-25",
        "effective_date": "2024-07-01",
        "version_information": "Act 46 of 2023",
    }
    passages = statute_passages(source, SAMPLE_STATUTE_PAGES)
    assert len(passages) == 5
    p1 = passages[0]
    assert p1["source_id"] == "bnss-test"
    assert "Section 1: Short title, extent and commencement (page 1)" in p1["locator"]
    assert p1["canonical_url"] == "https://mha.gov.in/bnss.pdf"
    assert p1["source_type"] == "indian_official"
    assert p1["effective_date"] == "2024-07-01"
    assert p1["passage_id"].startswith("bnss-test-s1-1-")


def test_parts_splits_long_sections():
    long_text = "word " * 600  # ~3000 chars > MAX_PART_CHARS (2600)
    parts = _parts(long_text)
    assert len(parts) >= 2
    assert all(len(p) <= 2600 for p in parts)


def test_rank_passages_named_section_boosting():
    p35 = {
        "source_id": "bnss",
        "passage_id": "p-35",
        "title": "BNSS 2023",
        "locator": "Section 35: When police may arrest without warrant (page 20)",
        "text": "The police officer may arrest any person without an order from a Magistrate.",
        "canonical_url": "https://mha.gov.in/bnss",
    }
    p47 = {
        "source_id": "bnss",
        "passage_id": "p-47",
        "title": "BNSS 2023",
        "locator": "Section 47: Person arrested to be informed of grounds of arrest (page 24)",
        "text": "Every police officer arresting any person shall communicate grounds of arrest.",
        "canonical_url": "https://mha.gov.in/bnss",
    }
    # For query asking specifically about Section 35, p35 should rank top due to named section boost
    results = rank_passages([p47, p35], "Can police arrest without warrant under Section 35", limit=2)
    assert len(results) == 2
    assert results[0]["passage_id"] == "p-35"


def test_rank_passages_suppresses_definitions_for_procedural_queries():
    def_passage = {
        "source_id": "wages-code",
        "passage_id": "p-def",
        "title": "Code on Wages",
        "locator": "Section 2: Definitions (page 2)",
        "text": "In this Code, unless the context otherwise requires, wages means all remuneration expressed in terms of money payable to employee.",
        "canonical_url": "https://labour.gov.in/wages",
    }
    proc_passage = {
        "source_id": "wages-code",
        "passage_id": "p-proc",
        "title": "Code on Wages",
        "locator": "Section 18: Deductions which may be made from wages (page 10)",
        "text": "Deductions from the wages of an employee shall be made only in accordance with the provisions of this Code.",
        "canonical_url": "https://labour.gov.in/wages",
    }
    # When user asks procedural question about deduction from wages, operative section should outrank Section 2 definitions
    results_proc = rank_passages([def_passage, proc_passage], "What deductions can employer make from my wages", limit=2)
    assert results_proc[0]["passage_id"] == "p-proc"

    # When user asks what wages means, definition passage should rank top
    results_meaning = rank_passages([def_passage, proc_passage], "What does wages mean under Code on Wages definition", limit=2)
    assert results_meaning[0]["passage_id"] == "p-def"
