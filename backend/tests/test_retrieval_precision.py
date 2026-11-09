"""Local retrieval brings law for this problem only.

Offline, against the real index and packs. Messages are from real conversations: a Patna hotel
stay where police took ₹5,000, a Nalanda inheritance dispute, a Bihar liquor arrest and unpaid
salary. Before these fixes the hotel follow-up got wage rules, Bihar liquor law, bail and
maintenance sections, and the land case got a hotel-stay ruling.
"""

from types import SimpleNamespace

import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import ResearchRequest
from app.agent.research import ResearchService
from app.config import Settings
from tests.test_answer_friendliness import PAID_POLICE
from tests.test_answer_quality import (
    BIHAR_ARREST,
    _prefetch,
    agent,  # noqa: F401  (module fixture)
)
from tests.test_legal_coverage import UNCLE_LAND_QUERY

HOTEL_T1 = (
    "I'm 20 years old and my girlfriend is also 20. We booked an OYO hotel in Patna for a night "
    "because we wanted some private time together. Both of us have valid Aadhaar cards, and the "
    "hotel allowed us to check in. But after around an hour, the hotel manager knocked on our door "
    "and started questioning us about whether we're married. He said unmarried couples aren't "
    "allowed to stay together and asked us to leave immediately. Is it actually illegal for us to "
    "stay in a hotel together?"
)
LAND_T2 = (
    "We have my grandfather's death certificate, old land papers, revenue receipts, and some "
    "threatening WhatsApp messages. The land is still in my grandfather's name, and as far as we "
    "know, he left no will. My grandmother is alive too. Should we approach the police, the Circle "
    "Officer, or a court? And what if the police refuse to register an FIR, saying it's just a "
    "family land dispute?"
)
UNRELATED_TO_HOTEL = (
    "pack-code-on-wages",
    "pack-bihar-prohibition-excise",
    "pack-bnss-2023-s479",
    "pack-bnss-2023-s480",
    "pack-bnss-2023-s482",
    "pack-bnss-2023-s144",
)


def test_hotel_stay_question_gets_the_rulings_on_adult_couples(agent):  # noqa: F811
    ids = _prefetch(agent, HOTEL_T1)
    assert {"prop-urgent-madras-hc-hotel-unmarried-2019", "prop-urgent-nandakumar-2018"} <= set(ids)
    assert not [i for i in ids if i.startswith(UNRELATED_TO_HOTEL)]


def test_paying_police_gets_intimidation_and_both_bribe_rules_without_unrelated_law(agent):  # noqa: F811
    ids = _prefetch(agent, PAID_POLICE, [HOTEL_T1])
    assert {
        "pack-bns-2023-s351",
        "prop-urgent-pca-1988-bribe-demand-s7",
        "prop-urgent-pca-1988-compelled-reporting-s8",
    } <= set(ids)
    assert not [i for i in ids if i.startswith(UNRELATED_TO_HOTEL)]


def test_land_dispute_gets_no_hotel_or_wage_law(agent):  # noqa: F811
    ids = _prefetch(agent, UNCLE_LAND_QUERY)
    assert "pack-bnss-2023-s164" in ids  # land dispute likely to cause a breach of the peace
    assert "prop-urgent-madras-hc-hotel-unmarried-2019" not in ids
    assert not [i for i in ids if i.startswith("pack-code-on-wages")]


def test_police_refusing_an_fir_brings_the_non_cognizable_route(agent):  # noqa: F811
    assert "pack-bnss-2023-s174" in _prefetch(agent, LAND_T2, [UNCLE_LAND_QUERY])


def test_unpaid_salary_gets_no_bribe_or_banking_rule(agent):  # noqa: F811
    ids = _prefetch(agent, "my company has not paid my salary for 2 months after I resigned")
    assert "pack-code-on-wages-2019-s17" in ids
    assert "prop-urgent-pca-1988-compelled-reporting-s8" not in ids
    assert "prop-banking-rbi-unauthorised-liability" not in ids


def test_one_judgment_cannot_take_every_slot(agent):  # noqa: F811
    ids = _prefetch(agent, BIHAR_ARREST)
    assert len([i for i in ids if "kalam-ansari" in i]) <= 2
    assert "pack-bihar-prohibition-excise-act-2016-s74" in ids


@pytest.mark.parametrize(
    ("saved_text", "kept"),
    [
        ("The police officer must register the case under the law.", False),  # only generic words
        ("An unmarried adult couple may stay in a hotel room.", True),
    ],
)
def test_saved_web_passages_need_two_words_that_say_what_the_problem_is(saved_text, kept):
    saved = {
        "passage_id": "web-saved",
        "title": "Saved official page",
        "locator": "Official webpage",
        "text": saved_text,
        "canonical_url": "https://state.bihar.gov.in/page",
        "retrieved_at": "2026-11-01T00:00:00Z",
        "origin": "web",
    }
    settings = Settings(openai_api_key="fixture", agent_research_seconds=10)
    service = ResearchService(
        settings,
        SimpleNamespace(passages=[saved]),
        provider=SimpleNamespace(search_public=lambda *a: ([], None)),
        fetcher=SimpleNamespace(read=lambda *a: None),
        repository=SimpleNamespace(save=lambda *a: None),
        knowledge_index=SimpleNamespace(search=lambda *a, **k: ([], {"certified_hit_count": 0})),
    )
    request = ResearchRequest(
        questions=[
            {"query": "police officer unmarried couple hotel room", "material_gap": "Hotel stay rule"}
        ],
        fresh_required=False,
    )
    state = {"current_message": "Can police remove an unmarried couple from a hotel?", "context": {}}
    evidence = service.run(request, state, TurnBudget(settings))["evidence"]
    assert any(p["passage_id"] == "web-saved" for p in evidence) is kept
