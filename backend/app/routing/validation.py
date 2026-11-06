"""Hard validation is independent of friendly wording and model agreement."""

import re

from app.services.runtime_tools import add_calendar_days


class ExecutionValidator:
    @staticmethod
    def check(state):
        findings = []
        records = state.get("tool_records", [])
        events = state.get("events", [])
        response = state.get("response", "")
        search_success = any(
            r.get("tool") == "web_search"
            and (r.get("search_completed") or r.get("status") == "succeeded")
            for r in records
        ) or any(e.get("stage") == "web_search" and e.get("status") == "complete" for e in events)
        if (
            re.search(
                r"\bi (?:have )?(?:searched|browsed|looked (?:it |this )?up)|मैंने.*(?:वेब|इंटरनेट).*खोज",
                response,
                re.I,
            )
            and not search_success
            and not (
                any(
                    r.get("tool") == "legal_corpus" and r.get("status") == "succeeded"
                    for r in records
                )
                and re.search(r"saved|stored|corpus|database", response, re.I)
            )
        ):
            findings.append(
                {
                    "code": "unexecuted_search_claim",
                    "reason": "No successful search execution supports this statement.",
                }
            )
        search_available = (
            state.get("capabilities", {}).get("web_search", {}).get("status") == "available"
        )
        if (search_success or search_available) and re.search(
            r"(?:can't|cannot|can’t|unable to) (?:perform (?:a )?live web search|(?:do |access )?(?:a )?live (?:web )?search|check live updates)",
            response,
            re.I,
        ):
            findings.append(
                {
                    "code": "false_search_limitation",
                    "reason": "A successful search contradicts the claimed limitation.",
                }
            )
        envelope = state.get("response_envelope", {})
        for calculation in envelope.get("date_calculations", []):
            try:
                if (
                    add_calendar_days(calculation["start_date"], calculation["days"])
                    != calculation["result_date"]
                ):
                    raise ValueError("Mismatched date")
            except (ValueError, OverflowError):
                findings.append(
                    {
                        "code": "date_arithmetic_error",
                        "reason": "The declared calendar calculation does not reproduce its result.",
                    }
                )
            if calculation["kind"] == "statutory_deadline":
                findings.append(
                    {
                        "code": "unverified_statutory_clock",
                        "reason": "No validated statutory deadline policy is supplied for this calculation; calendar arithmetic cannot establish a legal deadline.",
                    }
                )
        if envelope.get("document_ready_to_send") and (
            state.get("draft_spec", {}).get("missing_details")
            or any(not c.get("resolved") for c in state.get("memory", {}).get("contradictions", []))
        ):
            findings.append(
                {
                    "code": "document_not_send_ready",
                    "reason": "Missing mandatory details or material contradictions require review before a document is send-ready.",
                }
            )
        if state.get("interpretation"):
            coverage = {item["request_id"]: item for item in state.get("request_coverage", [])}
            for task in state["interpretation"]["tasks"]:
                item = coverage.get(task["task_id"])
                if not item or (item["status"] != "answered" and not item.get("reason")):
                    findings.append(
                        {
                            "code": "task_coverage_missing",
                            "reason": "Every interpreted task requires an answer or an explained deferral/clarification.",
                        }
                    )
                task_plan = next(
                    (p for p in state.get("task_plan", []) if p["task_id"] == task["task_id"]), {}
                )
                if (
                    task["requires_research"]
                    and task_plan.get("status") == "deferred"
                    and item
                    and item["status"] == "answered"
                ):
                    findings.append(
                        {
                            "code": "unsupported_research_answer",
                            "reason": "A research-dependent task cannot be marked answered when its evidence search did not succeed.",
                        }
                    )
        for claim in envelope.get("tool_claims", []):
            matching = [
                r
                for r in records
                if r.get("task_id") == claim["task_id"] and r.get("tool") == claim["tool"]
            ]
            if not matching or not any(r["status"] == claim["status"] for r in matching):
                findings.append(
                    {
                        "code": "tool_record_mismatch",
                        "reason": "A structured tool claim is not supported by runtime records.",
                    }
                )
        passages = {p["passage_id"]: p for p in state.get("passages", [])}
        routes = {
            r["route_id"]: r for r in state.get("resolution_plan", {}).get("alternatives", [])
        }
        for claim in envelope.get("legal_recommendations", []):
            if claim["status"] != "eligible_destination":
                continue
            route = routes.get(claim["route_id"])
            supported = [passages[p] for p in claim["passage_ids"] if p in passages]
            if (
                not route
                or route["eligibility"]["status"] != "eligible"
                or not route["eligibility"].get("filing_verified", False)
                or not supported
                or len(supported) != len(claim["passage_ids"])
                or not claim.get("jurisdiction")
            ):
                findings.append(
                    {
                        "code": "unverified_legal_destination",
                        "reason": "An eligible destination requires a matching verified policy, passages and jurisdiction.",
                    }
                )
            elif any(p.get("source_type") == "public_candidate" for p in supported):
                findings.append(
                    {
                        "code": "unverified_authority_source",
                        "reason": "An unverified public website cannot establish legal eligibility.",
                    }
                )
            elif not claim.get("effective_date") or not any(
                p.get("effective_date") == claim["effective_date"]
                and p.get("jurisdiction") == claim["jurisdiction"]
                for p in supported
            ):
                findings.append(
                    {
                        "code": "unverified_rule_applicability",
                        "reason": "Jurisdiction and effective date must bind to the supporting rule; unknowns require preparation-only guidance.",
                    }
                )
        formal = bool(
            re.search(
                r"(?:eligible|must file|should file|file (?:your |a |the )?complaint (?:with|before))",
                response,
                re.I,
            )
            and re.search(r"commission|ombudsman|\bNCH\b|\bRBI\b", response, re.I)
        )
        if formal and state.get("interpretation") and not envelope.get("legal_recommendations"):
            findings.append(
                {
                    "code": "undeclared_legal_destination",
                    "reason": "Consequential filing advice must declare provenance and eligibility for deterministic checking.",
                }
            )
        return findings
