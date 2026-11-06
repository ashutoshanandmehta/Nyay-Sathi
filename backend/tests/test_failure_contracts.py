from app.services.intake import deterministic_extract


def test_guaranteed_outcome_request_does_not_change_scope_to_supported_fact():
    result = deterministic_extract("Guarantee that I will win")
    assert result.domain == "unknown"
    assert result.proposed_facts == []


def test_imminent_court_deadline_has_specific_reason():
    result = deterministic_extract("My hearing tomorrow is about this")
    assert result.urgent_reason and "hearing" in result.urgent_reason.lower()


def test_criminal_matter_is_unsupported_and_urgent():
    result = deterministic_extract("Police say they may arrest me")
    assert result.domain == "criminal"
    assert result.urgent_reason and "criminal" in result.urgent_reason.lower()


def test_unsupported_landlord_domain_still_extracts_amount():
    result = deterministic_extract("My landlord kept my ₹40,000 deposit")
    assert result.domain == "landlord_deposit"
    assert result.proposed_facts[0]["value"] == "40000"
