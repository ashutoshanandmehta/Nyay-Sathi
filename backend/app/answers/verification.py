"""Claim and dependency validation. Candidate and reviewer statuses grant no permission."""

import hashlib
import json
import re

from app.answers.contracts import (
    ActionRecommendation,
    CandidateBatch,
    ClaimReview,
    ResponseQualityScorecard,
    ReviewFinding,
    UnitReviewBatch,
    UsefulnessReview,
    VerifiedClaim,
    VerifiedUnit,
)
from app.answers.evidence import EvidenceRegistry
from app.routing.contracts import RequestInterpretation
from app.routing.task_context import ApplicabilityPolicy, TaskContext
from app.routing.validation import ExecutionValidator
from app.services.request_coverage import contains_internal_rendering

EXTERNAL_AUTHORITY_PATTERN = re.compile(
    r"\b(?:section\s+\d+|consumer protection act|act,\s*\d{4}|rule[s]?,\s*\d{4}|regulation|"
    r"commission|ombudsman|nch|national consumer helpline|rbi|court|tribunal|statut|"
    r"limitation period|legally required|legally entitled|guaranteed by law)\b",
    re.I,
)


def _requires_external_authority(claim) -> bool:
    """Distinguish external legal/authority claims from practical recommendations and preparation."""
    if claim.kind in {"legal", "safety", "external_fact", "legal_procedure", "legal_conclusion"}:
        return True
    if claim.legal_action is not None or claim.date_calculation is not None:
        return True
    if claim.kind == "procedural":
        if not claim.evidence_ids:
            return True
        return bool(EXTERNAL_AUTHORITY_PATTERN.search(claim.text))
    if claim.kind in {"recommendation", "preparation"}:
        return bool(EXTERNAL_AUTHORITY_PATTERN.search(claim.text))
    return False


def digest(batch):
    return hashlib.sha256(
        json.dumps(batch.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def claim_signature(claim, registry, task, state):
    """Bind a review to exact content, evidence, task and case within this turn."""
    data = {
        "claim": claim.model_dump(mode="json"),
        "task": task.model_dump(mode="json"),
        "case_version": state.get("memory", {}).get("version"),
        "evidence": [registry.entries.get(key) for key in claim.evidence_ids],
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def review_binding(state):
    """Bind review to the evidence and runtime context actually assessed."""
    data = {
        "evidence": EvidenceRegistry(state).payload(),
        "interpretation": state["interpretation"],
        "memory": state.get("memory"),
        "executions": state.get("tool_records", []),
        "draft_contract": state.get("draft_spec", {}),
        "context": state.get("context", {}),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class UnitVerifier:
    def verify(self, state):
        batch = CandidateBatch.model_validate(state.get("candidate_batch", {"units": []}))
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        registry = EvidenceRegistry(state)
        if "exposed_evidence_ids" in state:
            registry.entries = {
                key: entry
                for key, entry in registry.entries.items()
                if key in state["exposed_evidence_ids"]
            }
        tasks = {task.task_id: task for task in interpretation.tasks}
        contexts = {key: TaskContext.for_task(task) for key, task in tasks.items()}
        review_data = state.get("unit_review", {})
        review = UnitReviewBatch.model_validate(review_data) if review_data else None
        current_review = (
            review is not None
            and state.get("reviewed_candidate_digest") == digest(batch)
            and state.get("reviewed_context_digest") == review_binding(state)
        )
        verdicts = {}
        if current_review:
            for item in review.claims:
                verdicts.setdefault(item.claim_id, []).append(item)
        all_claims = [claim for unit in batch.units for claim in unit.claims]
        counts = {
            c.claim_id: sum(other.claim_id == c.claim_id for other in all_claims)
            for c in all_claims
        }
        candidates = {c.claim_id: c for c in all_claims}
        findings, approved = {}, set()

        def finding(code, reason, severity="major"):
            return ReviewFinding(code=code, severity=severity, reason=reason)

        for unit in batch.units:
            for claim in unit.claims:
                errors = []
                task = tasks.get(unit.task_id)
                if (
                    not task
                    or counts[claim.claim_id] != 1
                    or sum(u.unit_id == unit.unit_id for u in batch.units) != 1
                ):
                    errors.append(
                        finding(
                            "invalid_claim_identity",
                            "Task and claim identifiers must bind uniquely.",
                        )
                    )
                if not claim.text.strip() or contains_internal_rendering(claim.text):
                    errors.append(
                        finding(
                            "internal_state_leak", "Content is empty or exposes internal state."
                        )
                    )
                missing = set(claim.evidence_ids) - registry.entries.keys()
                if missing:
                    errors.append(
                        finding(
                            "unknown_evidence",
                            "A cited evidence ID is not available in this authorized turn.",
                        )
                    )
                semantic = verdicts.get(claim.claim_id, [])
                semantic_type = semantic[0].content_type if len(semantic) == 1 else None
                needs_external = _requires_external_authority(claim) or semantic_type in {
                    "external_fact",
                    "legal_procedure",
                    "legal_conclusion",
                    "safety",
                }
                if (
                    state.get("pipeline_version") == "v2"
                    and semantic_type == "practical"
                    and claim.kind in {"preparation", "procedural"}
                    and not claim.legal_action
                    and not claim.date_calculation
                ):
                    preservation = re.match(
                        r"(?:keep|save|collect|attach|preserve|fill in)\b", claim.text, re.I
                    )
                    consequential = re.search(
                        r"\b(?:must|mandatory|required|entitled|deadline|within \d+|fee|jurisdiction|limitation)\b",
                        claim.text,
                        re.I,
                    )
                    if preservation and not consequential:
                        needs_external = False
                if state.get("pipeline_version") == "v2" and semantic_type is None:
                    errors.append(
                        finding(
                            "missing_content_classification",
                            "Independent classification is required, not just the generator's label.",
                        )
                    )
                if (
                    state.get("extraction_status") == "required_extraction_budget_exhausted"
                    and needs_external
                ):
                    errors.append(
                        finding(
                            "unresolved_research_dependency",
                            "The prerequisite factual assessment did not fit this turn's allowance.",
                        )
                    )
                if re.search(
                    r"\b(?:I (?:have )?(?:saved|updated|committed)|your case (?:has been|was) updated)\b",
                    claim.text,
                    re.I,
                ):
                    errors.append(
                        finding(
                            "unexecuted_persistence_claim",
                            "Only an actual commit receipt can support a persistence acknowledgement.",
                        )
                    )
                if needs_external:
                    public = [
                        registry.entries[k]
                        for k in claim.evidence_ids
                        if k in registry.public_ids()
                    ]
                    if not public:
                        errors.append(
                            finding(
                                "missing_external_support",
                                "This conclusion requires relevant fetched or approved public evidence.",
                            )
                        )
                    if any(
                        p.get("verification_status")
                        in {"public_candidate", "unverified_public_source"}
                        for p in public
                    ):
                        errors.append(
                            finding(
                                "unverified_source_origin",
                                "A discovered candidate is not verified authority for this conclusion.",
                            )
                        )
                    if task and any(
                        not ApplicabilityPolicy.permits(contexts[task.task_id], p) for p in public
                    ):
                        errors.append(
                            finding(
                                "inapplicable_evidence",
                                "Source origin does not establish applicability to this task.",
                            )
                        )
                elif (
                    claim.kind
                    in {"factual", "draft", "recommendation", "preparation", "procedural"}
                    and not claim.evidence_ids
                ):
                    errors.append(
                        finding(
                            "missing_factual_provenance",
                            "A factual statement, practical recommendation, or correspondence needs authorized factual provenance.",
                        )
                    )
                if current_review and review is not None:
                    cr = review.correctness_review
                    if claim.claim_id in cr.unsupported_claims:
                        errors.append(
                            finding(
                                "unsupported_claim_flagged",
                                "Reviewer correctness check marked this claim unsupported.",
                            )
                        )
                    if claim.claim_id in cr.legal_source_failures:
                        errors.append(
                            finding(
                                "legal_source_failure",
                                "Reviewer correctness check flagged a legal source failure.",
                            )
                        )
                    if claim.claim_id in cr.provenance_failures:
                        errors.append(
                            finding(
                                "provenance_failure",
                                "Reviewer correctness check flagged a provenance failure.",
                            )
                        )
                # A model can label a sentence incorrectly. Semantic review still
                # checks all assertions, and obvious legal timing cannot be hidden.
                if (
                    claim.kind in {"legal", "procedural"}
                    and re.search(
                        r"(?:you (?:must|have to)|your (?:last date|deadline)|file (?:by|within)).{0,45}\d+\s*(?:days?|months?|years?)",
                        claim.text,
                        re.I,
                    )
                    and not claim.date_calculation
                ):
                    errors.append(
                        finding(
                            "undeclared_deadline",
                            "A consequential timing statement requires explicit validation.",
                        )
                    )
                envelope = {
                    "tool_claims": [c.model_dump() for c in claim.tool_claims],
                    "legal_recommendations": [claim.legal_action.model_dump()]
                    if claim.legal_action
                    else [],
                    "date_calculations": [claim.date_calculation.model_dump()]
                    if claim.date_calculation
                    else [],
                    "document_ready_to_send": unit.document_ready_to_send,
                }
                if claim.legal_action and not set(claim.legal_action.passage_ids) <= (
                    set(claim.evidence_ids) & registry.public_ids()
                ):
                    errors.append(
                        finding(
                            "legal_action_evidence_mismatch",
                            "Filing provenance must reference public evidence attached to this claim and exposed in this turn.",
                        )
                    )
                runtime = {
                    **state,
                    "interpretation": {},
                    "response": claim.text,
                    "response_envelope": envelope,
                    "tool_records": [
                        r for r in state.get("tool_records", []) if r.get("task_id") == unit.task_id
                    ],
                    "events": [],
                }
                errors += [
                    finding(f["code"], f["reason"]) for f in ExecutionValidator.check(runtime)
                ]
                if (
                    not claim.legal_action
                    and re.search(
                        r"(?:eligible|must file|should file|file (?:your |a |the )?complaint (?:with|before))",
                        claim.text,
                        re.I,
                    )
                    and re.search(r"commission|ombudsman|\bNCH\b|\bRBI\b", claim.text, re.I)
                ):
                    errors.append(
                        finding(
                            "undeclared_legal_destination",
                            "Filing advice needs a verified eligibility declaration.",
                        )
                    )
                reviews = verdicts.get(claim.claim_id, [])
                if not current_review and task:
                    cached = state.get("verified_claim_reviews", {}).get(
                        claim_signature(claim, registry, task, state)
                    )
                    if cached:
                        reviews = [ClaimReview.model_validate(cached)]
                if len(reviews) != 1:
                    errors.append(
                        finding(
                            "review_missing",
                            "A fresh independent semantic review is required for this claim.",
                        )
                    )
                else:
                    errors += reviews[0].findings
                    if reviews[0].support != "supported":
                        errors.append(
                            finding(
                                "semantic_support_unresolved",
                                "The reviewer has not established support for all assertions in this claim.",
                                "moderate",
                            )
                        )
                if current_review:
                    errors += (
                        review.findings
                    )  # Turn-wide privacy/safety failures genuinely affect every unit.
                else:
                    errors += [
                        ReviewFinding.model_validate(f)
                        for f in state.get("turn_review_findings", [])
                    ]
                findings[claim.claim_id] = errors
                if not any(f.severity in {"critical", "major", "moderate"} for f in errors):
                    approved.add(claim.claim_id)

        # Verify a dependency DAG. Cycles, missing references and downstream
        # dependencies on blocked content never acquire approval by iteration.
        visiting, resolved = set(), {}

        def valid(identifier):
            if identifier in resolved:
                return resolved[identifier]
            if identifier in visiting or identifier not in approved:
                return False
            visiting.add(identifier)
            okay = all(
                dep in candidates and valid(dep) for dep in candidates[identifier].depends_on
            )
            visiting.remove(identifier)
            resolved[identifier] = okay
            return okay

        for identifier in list(approved):
            if not valid(identifier):
                findings[identifier].append(
                    finding(
                        "blocked_dependency", "A required claim is missing, blocked, or cyclic."
                    )
                )
        approved = {identifier for identifier in approved if resolved.get(identifier)}

        units = []
        for unit in batch.units:
            if unit.task_id not in tasks:
                continue
            good = [
                VerifiedClaim(
                    claim_id=c.claim_id,
                    kind=c.kind,
                    text=registry.strip_generated_citations(c.text),
                    evidence_ids=c.evidence_ids,
                )
                for c in unit.claims
                if c.claim_id in approved
            ]
            bad = [c for c in unit.claims if c.claim_id not in approved]
            bad_ids = {c.claim_id for c in bad}
            unit_claim_ids = {c.claim_id for c in unit.claims}
            unresolved = list(unit.unresolved)
            if bad:
                unresolved.append(
                    "Some requested content could not be verified and has been withheld."
                )
            task_findings = [f for c in unit.claims for f in findings[c.claim_id]]
            valid_actions: list[ActionRecommendation] = []
            for rec in unit.action_recommendations:
                unknown_ev = set(rec.evidence_ids) - set(registry.entries.keys())
                unapproved_rationale = set(rec.rationale_claim_ids) - approved
                requires_external = bool(
                    EXTERNAL_AUTHORITY_PATTERN.search(rec.action)
                    or re.search(
                        r"\b(?:file (?:with|before)|eligible|must file)\b", rec.action, re.I
                    )
                )
                has_public = bool(set(rec.evidence_ids) & registry.public_ids())
                has_user_support = bool(
                    rec.rationale_claim_ids and not unapproved_rationale
                ) or bool(rec.evidence_ids and not unknown_ev)
                if (
                    unknown_ev
                    or unapproved_rationale
                    or not has_user_support
                    or (requires_external and not has_public)
                ):
                    task_findings.append(
                        finding(
                            "unverified_action_recommendation",
                            "Action recommendation lacks required rationale or external authority support.",
                            "moderate",
                        )
                    )
                else:
                    valid_actions.append(rec)
            coverage = (
                [t for t in review.task_reviews if t.task_id == unit.task_id]
                if current_review
                else []
            )
            unresolved_explanations: list[str] = []
            if current_review and review is not None:
                for item in review.unresolved_claims:
                    if (
                        item.claim_id in bad_ids or item.claim_id in unit_claim_ids
                    ) and item.explanation.strip():
                        unresolved_explanations.append(item.explanation.strip())
                if coverage and coverage[0].user_limitation and coverage[0].user_limitation.strip():
                    unresolved_explanations.append(coverage[0].user_limitation.strip())
                unresolved_explanations = list(dict.fromkeys(unresolved_explanations))
            substantive = any(c.kind not in {"question", "limitation"} for c in good)
            task_answered = len(coverage) == 1 and coverage[0].completion == "answered"
            status = (
                "partial"
                if substantive and (bad or not task_answered)
                else "supported"
                if substantive
                else "blocked"
                if any(f.severity == "critical" for f in task_findings)
                else "deferred"
            )
            # No half-letter is exported as a complete document.
            doc_ids = unit.document_claim_ids
            doc = (
                "\n\n".join(
                    next(c.text for c in good if c.claim_id == identifier) for identifier in doc_ids
                )
                if doc_ids
                and len(set(doc_ids)) == len(doc_ids)
                and set(doc_ids) <= {c.claim_id for c in good}
                else None
            )
            units.append(
                VerifiedUnit(
                    unit_id=unit.unit_id,
                    task_id=unit.task_id,
                    status=status,
                    claims=good,
                    action_recommendations=valid_actions,
                    unresolved=unresolved,
                    unresolved_explanations=unresolved_explanations,
                    findings=task_findings,
                    document_title=unit.document_title if doc else None,
                    document=doc,
                    assistance_status={"supported": "delivered"}.get(status, status),
                    document_status="needs_material_review"
                    if doc_ids and not doc
                    else "needs_user_details"
                    if doc and unresolved
                    else "prepared"
                    if doc
                    else "not_applicable",
                    legal_verification_status="unresolved"
                    if any(
                        f.code
                        in {
                            "missing_external_support",
                            "inapplicable_evidence",
                            "unverified_legal_destination",
                        }
                        for f in task_findings
                    )
                    else "supported"
                    if any(c.kind in {"legal", "legal_procedure", "legal_conclusion"} for c in good)
                    else "not_required",
                )
            )
        covered = {u.task_id for u in units}
        for task in interpretation.tasks:
            if task.task_id not in covered:
                units.append(
                    VerifiedUnit(
                        unit_id=f"missing-{task.task_id}",
                        task_id=task.task_id,
                        status="deferred",
                        claims=[],
                        unresolved=["This part of your request could not be completed reliably."],
                        findings=[
                            finding(
                                "task_not_generated", "No candidate was generated for this task."
                            )
                        ],
                        document_title=None,
                        document=None,
                    )
                )
        return units, registry

    def evaluate_usefulness(self, state, units=None) -> UsefulnessReview:
        """Independently check whether the response did what the user requested."""
        if units is None:
            units, _ = self.verify(state)
        review_data = state.get("unit_review", {})
        review = UnitReviewBatch.model_validate(review_data) if review_data else None
        base = (
            review.usefulness_review.model_copy(deep=True)
            if review is not None
            else UsefulnessReview()
        )
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        batch = CandidateBatch.model_validate(state.get("candidate_batch", {"units": []}))
        all_candidate_claims = [c for u in batch.units for c in u.claims]
        approved_claims = [c for u in units for c in u.claims]
        if not approved_claims:
            base.primary_question_answered = False
            base.requested_deliverables_complete = False
            base.recommended_action_clear = False
        if any(u.status in {"deferred", "blocked"} for u in units):
            base.requested_deliverables_complete = False
        if "complaint_draft" in interpretation.requested_deliverables:
            has_draft = any(u.document or any(c.kind == "draft" for c in u.claims) for u in units)
            if not has_draft:
                base.requested_deliverables_complete = False
        question_count = sum(1 for c in all_candidate_claims if c.kind == "question")
        if question_count > 1:
            base.avoidable_clarification = True
        if any(
            "One part of this request remains unverified; the supported material above is available to use as provisional preparation."
            in c.text
            for c in all_candidate_claims
        ):
            base.unnecessary_disclaimer = True
        if approved_claims and all(c.kind in {"question", "limitation"} for c in approved_claims):
            if any(
                t.intent in {"draft", "revision", "summary", "evidence"}
                for t in interpretation.tasks
            ):
                base.primary_question_answered = False
        return base

    def needs_usefulness_repair(self, state, units=None) -> bool:
        """Trigger targeted repair when reviewer or runtime flags a usefulness failure."""
        review_data = state.get("unit_review", {})
        if not review_data or "usefulness_review" not in review_data:
            return False
        ur = self.evaluate_usefulness(state, units=units)
        return bool(
            not ur.requested_deliverables_complete
            or not ur.primary_question_answered
            or not ur.recommended_action_clear
            or not ur.important_supported_facts_preserved
            or ur.avoidable_clarification
            or ur.unnecessary_disclaimer
        )

    def score_response(self, state, composition, units=None) -> ResponseQualityScorecard:
        """Compute the weighted response-quality scorecard without letting usefulness mask safety failures."""
        if units is None:
            units, _ = self.verify(state)
        ur = self.evaluate_usefulness(state, units=units)
        safety_codes = {
            "undeclared_deadline",
            "unverified_statutory_clock",
            "unverified_legal_destination",
            "undeclared_legal_destination",
            "unauthorized_case_update",
            "unsafe_verdict",
            "internal_state_leak",
        }
        all_findings = [f for u in units for f in u.findings]
        serious_safety = any(
            f.severity == "critical" or f.code in safety_codes for f in all_findings
        )
        supported_ratio = (
            sum(1 for u in units if u.status == "supported") / len(units) if units else 0.0
        )
        task_completion = (
            5.0
            if ur.requested_deliverables_complete and ur.primary_question_answered
            else round(2.5 * supported_ratio, 2)
        )
        accuracy = 0.0 if serious_safety else (5.0 if not all_findings else 4.0)
        actionability = (
            5.0 if ur.recommended_action_clear and not ur.avoidable_clarification else 2.5
        )
        has_doc_request = "complaint_draft" in state.get("interpretation", {}).get(
            "requested_deliverables", []
        )
        doc_useful = (
            5.0 if (not has_doc_request or bool(composition.get("approved_documents"))) else 1.5
        )
        clarity = 5.0 if not ur.unnecessary_disclaimer and not ur.avoidable_clarification else 3.0
        return ResponseQualityScorecard(
            requested_task_completion=task_completion,
            factual_and_legal_accuracy=accuracy,
            actionability_and_next_steps=actionability,
            document_usefulness=doc_useful,
            clarity_and_concision=clarity,
            serious_safety_failure=serious_safety,
        )
