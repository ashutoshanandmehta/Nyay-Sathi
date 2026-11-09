"""Tests for legal coverage additions: official packs, BM25 retrieval, and concept expansions."""

import json
from pathlib import Path

import pytest

from app.agent.runner import CONCEPT_EXPANSIONS, PrimaryAgent
from app.config import Settings
from app.knowledge.search_index import OFFICIAL_PACKS_PATH
from app.rag.retrieval import HybridRetriever

UNCLE_LAND_QUERY = (
    "How to file complaint against my uncle who has harassed my father for some land "
    "disputes in my village Chorsua, Bihar; the land was owned by my grandfather who died 1 month back."
)
HINGLISH_QUERY = "chacha zameen ke liye papa ko dhamki de rahe hain, thana mein shikayat kaise karein, Bihar"
CONSUMER_QUERY = "I ordered two fans on Amazon, returned both to the delivery agent, but only received refund for one."


@pytest.fixture(scope="module")
def official_pack_passages():
    assert Path(OFFICIAL_PACKS_PATH).exists(), "Official law pack missing"
    with open(OFFICIAL_PACKS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {p["passage_id"]: p for p in data.get("passages", [])}


@pytest.fixture(scope="module")
def agent():
    settings = Settings(openai_api_key=None)
    return PrimaryAgent(settings, HybridRetriever(settings), provider=object())


def _prefetch(agent, message):
    state = {
        "current_message": message,
        "memory": {},
        "context": {"recent_turns": []},
        "passages": [],
        "tool_records": [],
    }
    agent._pre_retrieve_certified(state)
    return [p["passage_id"] for p in state["passages"]]


def test_bnss_passages_in_official_pack(official_pack_passages):
    expected = {
        "pack-bnss-2023-s164": "Section 164: Procedure where dispute concerning land or water is likely to cause breach of peace",
        "pack-bnss-2023-s173": "Section 173: Information in cognizable cases",
        "pack-bnss-2023-s174": "Section 174: Information as to non-cognizable cases and investigation of such cases",
        "pack-bnss-2023-s175": "Section 175: Police officer’s power to investigate cognizable case",
        "pack-bnss-2023-s223": "Section 223: Examination of complainant",
    }
    for pid, expected_locator in expected.items():
        assert pid in official_pack_passages, f"Passage {pid} not found in pack"
        p = official_pack_passages[pid]
        assert p["locator"] == expected_locator, f"Locator mismatch for {pid}: got {p['locator']}"
        assert len(p["text"]) > 80, f"Passage text too short for {pid}"
        assert p["canonical_url"].startswith("http"), f"Invalid canonical URL for {pid}"
        assert p.get("content_hash"), f"Missing content hash for {pid}"


def test_bns_passages_in_official_pack(official_pack_passages):
    bns_pids = [p for p in official_pack_passages if "bns-2023" in p]
    if not bns_pids:
        pytest.skip("BNS 2023 not yet added to pack")
    expected = {
        "pack-bns-2023-s115": "Section 115: Voluntarily causing hurt",
        "pack-bns-2023-s126": "Section 126: Wrongful restraint",
        "pack-bns-2023-s324": "Section 324: Mischief",
        "pack-bns-2023-s329": "Section 329: Criminal trespass and house-trespass",
        "pack-bns-2023-s351": "Section 351: Criminal intimidation",
        "pack-bns-2023-s352": "Section 352: Intentional insult with intent to provoke breach of peace",
    }
    for pid, expected_locator in expected.items():
        assert pid in official_pack_passages, f"Passage {pid} not found in pack"
        p = official_pack_passages[pid]
        assert p["locator"] == expected_locator
        assert len(p["text"]) > 80
        assert p.get("content_hash")


def test_concept_mappings_match_positives_and_reject_negatives():
    test_cases = [
        (
            ["complaint", "shikayat", "शिकायत", "FIR", "thana", "police station", "report to police"],
            ["affirmative", "first"],
        ),
        (
            ["police refused", "FIR nahi likha", "not registering", "complaint not taken"],
            ["policeman"],
        ),
        (
            ["harass", "pareshan", "परेशान", "threat", "dhamki", "धमकी", "abuse", "gaali", "beat", "maar-peet", "मारपीट"],
            ["theater"],
        ),
        (
            ["land", "zameen", "jameen", "ज़मीन", "जमीन", "khet", "plot", "kabza", "boundary", "encroach"],
            ["landed in Delhi"],
        ),
        (
            ["died", "death", "expired", "guzar gaye", "inheritance", "wirasat", "waris", "hissa", "batwara", "partition", "property share"],
            ["I'm dying to know"],
        ),
        (
            ["lawyer fees", "free lawyer", "can't afford", "vakil ka paisa"],
            ["affordability of goods"],
        ),
    ]

    for positives, negatives in test_cases:
        for pos in positives:
            matched = any(pattern.search(pos) for pattern, _ in CONCEPT_EXPANSIONS)
            assert matched, f"Failed to match positive example: {pos}"
        for neg in negatives:
            matched = any(pattern.search(neg) for pattern, _ in CONCEPT_EXPANSIONS)
            assert not matched, f"Incorrectly matched negative example: {neg}"


def test_pre_retrieval_for_real_query(agent):
    ids = _prefetch(agent, UNCLE_LAND_QUERY)
    assert "pack-bnss-2023-s173" in ids
    assert "pack-bnss-2023-s164" in ids


def test_hinglish_query_pre_retrieval(agent):
    ids = _prefetch(agent, HINGLISH_QUERY)
    assert "pack-bnss-2023-s173" in ids


def test_no_false_matches_on_consumer_refund_query(agent):
    ids = _prefetch(agent, CONSUMER_QUERY)
    for pid in ids:
        assert not pid.startswith("pack-bns-2023-"), f"Unexpected BNS passage {pid} for consumer query"
        assert not pid.startswith("pack-hindu-succession-"), f"Unexpected HSA passage {pid} for consumer query"
        assert not pid.startswith("pack-bihar-land-"), f"Unexpected Bihar land passage {pid} for consumer query"
