"""Live-research quality: statute section splitting, BM25 ranking and search/fetch time split."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import ResearchRequest
from app.agent.research import ResearchService, rank_passages
from app.config import Settings
from app.rag.statutes import split_statute, statute_passages

ORIGINALS = Path(__file__).parents[2] / "data" / "sources" / "originals"

ACT_PAGES = [
    "ARRANGEMENT OF SECTIONS\n1. Short title.\n2. Definitions.\n3. Prohibition.\n4. Penalty.\n",
    "BE it enacted by Parliament as follows:—\n"
    "1. Short title.—(1) This Act may be called the Sample Act.\n"
    "2. Definitions.—In this Act, unless the context otherwise requires, “liquor” means spirit.\n"
    "3. Prohibition.—No person shall transport liquor.\n",
    "4. Penalty for transport.—Whoever transports liquor shall be punished with imprisonment.\n"
    "5. Release of vehicle.—A seized vehicle may be released on payment of penalty.\n"
    "SCHEDULE\n1. Form of application.\n",
]


def test_statute_is_split_into_numbered_sections_skipping_index_and_schedule():
    sections = split_statute(ACT_PAGES)
    assert [s["number"] for s in sections] == ["1", "2", "3", "4", "5"]
    assert sections[3]["heading"] == "Penalty for transport"
    assert sections[3]["page"] == 3
    assert "SCHEDULE" in sections[4]["text"]  # trailing schedule stays inside the last section
    assert split_statute(["Welcome to the portal.\nContact us.\n"]) == []


def test_long_sections_become_parts_with_section_locators():
    pages = ACT_PAGES[:2] + [
        ACT_PAGES[2].replace("imprisonment.", "imprisonment. " + "word " * 900)
    ]
    source = {
        "source_id": "web-x",
        "title": "Sample Act",
        "canonical_url": "https://x.gov.in/a.pdf",
        "retrieved_at": "t",
        "known_limitations": "L",
        "source_type": "official_web_research",
        "jurisdiction": "India",
    }
    locators = [p["locator"] for p in statute_passages(source, pages)]
    assert "Section 4: Penalty for transport (part 1 of 2) (page 3)" in locators
    assert "Section 5: Release of vehicle (page 3)" in locators


def _passage(pid, locator, text):
    return {
        "passage_id": pid,
        "source_id": pid,
        "title": "Sample Act",
        "locator": locator,
        "text": text,
        "canonical_url": "https://x.gov.in/a.pdf",
    }


DEFS = _passage(
    "defs",
    "Section 2: Definitions",
    "In this Act, unless the context otherwise requires, liquor means alcohol; vehicle includes "
    "car; transport means moving liquor; arrest has its meaning; possession of liquor.",
)
PENALTY = _passage(
    "penalty",
    "Section 30: Penalty for transport",
    "Whoever transports or possesses liquor in a vehicle shall be punished with imprisonment.",
)
RELEASE = _passage(
    "release",
    "Section 57B: Things liable to be released upon penalty",
    "A vehicle used for an offence may be released upon payment of penalty.",
)


def test_definitions_do_not_outrank_the_operative_section():
    ranked = rank_passages([DEFS, PENALTY], "liquor transport vehicle arrest punishment", 2, 2)
    assert [p["passage_id"] for p in ranked] == ["penalty", "defs"]


def test_definitions_rank_first_when_the_user_asks_what_a_word_means():
    ranked = rank_passages([PENALTY, DEFS], "what is the meaning of liquor in this act", 2, 2)
    assert ranked[0]["passage_id"] == "defs"


def test_named_section_is_preferred():
    ranked = rank_passages([PENALTY, RELEASE], "section 57B vehicle penalty", 2, 2)
    assert ranked[0]["passage_id"] == "release"


def test_searches_leave_the_rest_of_the_window_for_fetching():
    timeouts = []

    class Provider:
        def search_public(self, query, timeout):
            timeouts.append(timeout)
            return [], None

    settings = Settings(
        openai_api_key="fixture-not-real", agent_research_seconds=10, agent_search_share=0.5
    )
    service = ResearchService(
        settings,
        SimpleNamespace(passages=[]),
        provider=Provider(),
        fetcher=SimpleNamespace(read=lambda *a: None),
        repository=SimpleNamespace(save=lambda *a: None),
        knowledge_index=SimpleNamespace(search=lambda *a, **k: ([], {"certified_hit_count": 0})),
    )
    request = ResearchRequest(
        questions=[{"query": "Bihar liquor vehicle release penalty", "material_gap": "Release"}],
        fresh_required=True,
    )
    state = {"current_message": "Car seized.", "context": {}}
    service.run(request, state, TurnBudget(settings))
    assert timeouts and max(timeouts) <= 5.0


def test_real_bihar_gazette_splits_into_its_hundred_sections():
    path = ORIGINALS / "bihar-prohibition-excise-act-2016-gazette.pdf"
    if not path.exists():
        pytest.skip("Official original not downloaded (data/sources/originals is gitignored)")
    import fitz

    sections = {s["number"]: s for s in split_statute([p.get_text() for p in fitz.open(path)])}
    assert len(sections) == 100
    assert sections["76"]["heading"] == "Offences to be Cognizable and Non-Bailable"


def test_gap_covered_by_official_pack_skips_web_search():
    calls = []

    class Provider:
        def search_public(self, query, timeout):
            calls.append(query)
            return [], None

    settings = Settings(openai_api_key="fixture", agent_research_seconds=10)
    covered_passage = {
        "passage_id": "pack-bnss-2023-s173",
        "title": "BNSS Section 173",
        "locator": "Section 173: Information in cognizable cases",
        "text": "Every information relating to the commission of a cognizable offence...",
        "canonical_url": "https://example.gov.in",
        "retrieved_at": "2026-11-09",
        "origin": "official_pack",
    }
    service = ResearchService(
        settings,
        SimpleNamespace(passages=[]),
        provider=Provider(),
        fetcher=SimpleNamespace(read=lambda *a: None),
        repository=SimpleNamespace(save=lambda *a: None),
        knowledge_index=SimpleNamespace(search=lambda *a, **k: ([covered_passage], {"certified_hit_count": 0})),
    )
    request = ResearchRequest(
        questions=[{"query": "BNSS Section 173 cognizable offence", "material_gap": "Procedure for FIR registration"}],
        fresh_required=False,
    )
    state = {"current_message": "How to register FIR?", "context": {}}
    res = service.run(request, state, TurnBudget(settings))
    assert len(calls) == 0  # Skipped because local coverage exists
    assert any(p["passage_id"] == "pack-bnss-2023-s173" for p in res["evidence"])


def test_uncovered_gap_searches_once():
    calls = []

    class Provider:
        def search_public(self, query, timeout):
            calls.append(query)
            return [], None

    settings = Settings(openai_api_key="fixture", agent_research_seconds=10)
    service = ResearchService(
        settings,
        SimpleNamespace(passages=[]),
        provider=Provider(),
        fetcher=SimpleNamespace(read=lambda *a: None),
        repository=SimpleNamespace(save=lambda *a: None),
        knowledge_index=SimpleNamespace(search=lambda *a, **k: ([], {"certified_hit_count": 0})),
    )
    request = ResearchRequest(
        questions=[{"query": "Uncovered novel municipal circular", "material_gap": "Local rule"}],
        fresh_required=False,
    )
    state = {"current_message": "Municipal circular rule", "context": {}}
    service.run(request, state, TurnBudget(settings))
    assert len(calls) == 1  # Exactly one search executed
