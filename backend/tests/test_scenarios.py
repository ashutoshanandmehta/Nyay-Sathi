import json
from pathlib import Path

import pytest

from app.services.intake import deterministic_extract

SCENARIOS = json.loads(
    (Path(__file__).parents[2] / "evals" / "cases" / "synthetic_scenarios.json").read_text()
)


def test_at_least_40_synthetic_scenarios_are_declared():
    assert len(SCENARIOS) >= 40
    assert len({x["test_id"] for x in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[x["test_id"] for x in SCENARIOS])
def test_scenario_contract_is_complete(scenario):
    assert scenario["category"]
    assert scenario["input_messages"]
    assert scenario["expected_behaviour"]


@pytest.mark.parametrize(
    ("text", "domain", "intent", "urgent"),
    [
        ("My ₹2,000 refund has not arrived. What next?", "consumer", "options", False),
        ("The product is defective", "consumer", "intake", False),
        ("My order was not delivered", "consumer", "intake", False),
        ("My landlord kept the deposit", "landlord_deposit", "intake", False),
        ("My employer owes salary", "unpaid_salary", "intake", False),
        ("Police may arrest me", "criminal", "intake", True),
        ("I have a hearing tomorrow", "unknown", "intake", True),
        ("Draft a complaint email", "unknown", "draft", False),
    ],
)
def test_deterministic_triage(text, domain, intent, urgent):
    result = deterministic_extract(text)
    assert result.domain == domain
    assert result.intent == intent
    assert bool(result.urgent_reason) is urgent
