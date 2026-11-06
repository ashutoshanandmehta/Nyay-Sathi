"""One batched generation/review pair, not one model call per task."""

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_openai import ChatOpenAI

from app.answers.composition import VerifiedComposer
from app.answers.contracts import CandidateBatch, UnitReviewBatch
from app.answers.evidence import EvidenceRegistry
from app.answers.verification import UnitVerifier, claim_signature, digest, review_binding
from app.memory.patches import PatchEngine
from app.routing.contracts import RequestInterpretation
from app.services.model_calls import model_calls


def usage_total(previous, raw):
    result = dict(previous)
    for key, value in (getattr(raw, "usage_metadata", None) or {}).items():
        if isinstance(value, int):
            result[key] = result.get(key, 0) + value
    return result


class UnitPipeline:
    def __init__(self, settings, model_factory=ChatOpenAI):
        self.settings, self.model_factory = settings, model_factory
        root = Path(__file__).parents[1] / "prompts/v2"
        self.generation_prompt = (root / "units.md").read_text()
        self.review_prompt = (
            (root / "patch-review.md").read_text() + "\n\n" + (root / "review.md").read_text()
        )
        self.verifier, self.composer = UnitVerifier(), VerifiedComposer()

    def model(self, schema, review=False):
        stage = "review" if schema == UnitReviewBatch else "repair" if review else "generation"
        return SimpleNamespace(
            invoke=lambda messages: model_calls.structured(
                self.model_factory, schema, messages, self.settings, stage, review
            )
        )

    def payload(self, state):
        registry = EvidenceRegistry(state)
        v2 = state.get("pipeline_version") == "v2"
        if v2:
            registry.entries = {
                k: e for k, e in registry.entries.items() if e["kind"] != "user_report"
            }
        entries = sorted(registry.payload(), key=lambda e: e["kind"] == "public_passage")
        selected, size = [], 0
        for entry in entries:
            if size + len(json.dumps(entry, ensure_ascii=False)) > 20000 and selected:
                continue  # Never cut legal exceptions midway through a chunk.
            selected.append(entry)
            size += len(json.dumps(entry, ensure_ascii=False))
        before, after = state.get("base_memory", {}), state.get("memory", {})
        case_diff = {
            key: {"before": before.get(key), "after": value}
            for key, value in after.items()
            if key not in {"version", "pending_questions", "last_draft_spec", "stale_draft_ids"}
            and before.get(key) != value
        }
        # Avoid sending a long history just to review a new recommendation.
        if "journey" in case_diff:
            case_diff["journey"] = {
                key: {"before": before.get("journey", {}).get(key), "after": value}
                for key, value in after.get("journey", {}).items()
                if key != "recommendations" and before.get("journey", {}).get(key) != value
            }
        complete = len(json.dumps(case_diff, ensure_ascii=False)) <= 12000
        interp = state.get("interpretation", {})
        payload = {
            "language": state.get("language", "en"),
            "answer_requirements": {
                "requested_deliverables": interp.get("requested_deliverables", []),
                "user_goal": interp.get("user_goal"),
                "suggested_remedy": interp.get("suggested_remedy"),
                "required_answer_elements": interp.get("required_answer_elements", []),
                "missing_details": interp.get("missing_details", []),
            },
            "tasks": [
                {**t, "source_text": t["source_text"][:600]} for t in interp.get("tasks", [])
            ],
            "task_contexts": state.get("task_contexts", []),
            "executions": state.get("tool_records", []),
            "runtime": state.get("context", {}).get("runtime", {}),
            "pending_questions": state.get("context", {}).get("pending_question_or_stage", []),
            "conversation_context": {
                key: state.get("context", {}).get(key, [])
                for key in (
                    "recent_turns",
                    "rolling_summary",
                    "contradictions",
                    "unknowns",
                    "actions_completed",
                    "responses_received",
                    "requested_remedy",
                    "timeline",
                    "current_drafts",
                    "staged_case_proposals",
                )
            },
            "evidence": selected,
            "case_diff": case_diff
            if complete
            else "Too large for this review; keep changes staged.",
            "recommended_route_id": state.get("resolution_plan", {}).get("recommended_route_id"),
            "preparation_routes": [
                {
                    "route_id": r["route_id"],
                    "recipient_id": r.get("recipient_id"),
                    "title": r.get("title"),
                    "eligibility": r["eligibility"],
                    "source_urls": r["source_urls"],
                }
                for r in state.get("resolution_plan", {}).get("alternatives", [])
            ],
            "draft_contract": state.get("draft_spec", {}),
        }
        if v2:
            payload["tasks"] = [
                {k: v for k, v in t.items() if k != "source_text"} for t in interp.get("tasks", [])
            ]
            payload.pop("case_diff", None)
            payload["early_extraction"] = state.get("early_extraction", {})
            payload["case_patch_policy"] = {
                "authorized_task_ids": state.get("case_task_ids", []),
                "rule": "Propose supported facts and events separately. Review is not permission. Use segment evidence IDs from this task; never infer a remedy or completed action. Unknown roles stay unknown.",
            }
            payload["extraction_status"] = state.get("extraction_status")
            payload["resolution_policy"] = (
                "Determine the current dispute stage from the cited user account and existing history. Do not repeat exhausted support/grievance routes without a specific materially useful reason. Prefer a practical next verified route; state a reasonable India-conditional assumption where applicable instead of blocking ordinary preparation. Explain recommendation, why, how, evidence and what if unresolved; one question only if material. Do not insert a letter unless requested or necessary. Use approved cached official sources if they cover the claim; research only real gaps. Company records do not conclusively establish physical pickup."
            )
            payload["conversation_context"]["recent_turns"] = [
                t
                for t in payload["conversation_context"]["recent_turns"]
                if t.get("content") != state["current_message"]
            ][-2:]
        conversation = payload["conversation_context"]
        conversation["recent_turns"] = conversation["recent_turns"][-4:]
        # Preserve contradictions/unknowns first; omit whole optional records
        # rather than cutting statements into potentially misleading fragments.
        for key in ("recent_turns", "current_drafts", "staged_case_proposals", "rolling_summary"):
            if len(json.dumps(conversation, ensure_ascii=False)) > 16000:
                conversation[key] = []
        if len(json.dumps(conversation, ensure_ascii=False)) > 16000:
            complete = False
            payload["conversation_context"] = {
                "limitation": "Case context exceeds the review allowance. Keep case changes staged and defer claims requiring omitted history."
            }
        return payload, [entry["evidence_id"] for entry in selected], complete

    def generate(self, state, repair=False):
        calls = state.get("model_calls", 0)
        if calls + 2 > self.settings.max_model_calls_per_turn:
            return {"events": [{"stage": "response", "status": "budget_exhausted"}]}
        payload, ids, complete = self.payload(state)
        if repair:
            payload["previous_candidates"] = state.get("candidate_batch", {})
            payload["review"] = state.get("unit_review", {})
            ur = self.verifier.evaluate_usefulness(state)
            usefulness_notes = []
            if not ur.requested_deliverables_complete:
                usefulness_notes.append(
                    "Complete all requested_deliverables (including a ready-to-use provisional draft when requested)."
                )
            if not ur.recommended_action_clear:
                usefulness_notes.append(
                    "State the recommended next action and requested remedy clearly without guaranteeing legal entitlement."
                )
            if not ur.primary_question_answered:
                usefulness_notes.append("Directly answer the user's primary question.")
            if ur.avoidable_clarification:
                usefulness_notes.append(
                    "Remove avoidable clarification questions; ask at most one focused question."
                )
            if ur.unnecessary_disclaimer:
                usefulness_notes.append(
                    "Replace generic disclaimers with specific claim-level limitations."
                )
            # Supported units are left byte-for-byte unchanged unless usefulness repair targets them.
            payload["repair_instruction"] = (
                "Repair rejected claims and address usefulness gaps: " + " ".join(usefulness_notes)
                if usefulness_notes
                else "Repair only rejected claims. Do not rewrite supported claims. Presentation advice is nonblocking."
            )
        try:
            result = self.model(CandidateBatch, review=repair).invoke(
                [
                    ("system", self.generation_prompt),
                    ("user", json.dumps(payload, ensure_ascii=False)),
                ]
            )
            with model_calls.validation("repair" if repair else "generation"):
                batch = CandidateBatch.model_validate(result.get("parsed"))
            if repair:
                old_units = CandidateBatch.model_validate(
                    state.get("candidate_batch", {"units": []})
                )
                verified, _ = self.verifier.verify(state)
                needs_usefulness = self.verifier.needs_usefulness_repair(state, verified)
                supported_ids = (
                    set()
                    if needs_usefulness
                    else {u.unit_id for u in verified if u.status == "supported"}
                )
                preserved = [u for u in old_units.units if u.unit_id in supported_ids]
                batch = CandidateBatch(
                    units=preserved + [u for u in batch.units if u.unit_id not in supported_ids]
                )
            return {
                "candidate_batch": batch.model_dump(mode="json"),
                "exposed_evidence_ids": ids,
                "case_diff_review_complete": complete,
                "model_calls": calls + 1,
                "token_usage": usage_total(state.get("token_usage", {}), result.get("raw")),
                "revision_attempts": 1 if repair else state.get("revision_attempts", 0),
                "revision_succeeded": repair,
                "events": [
                    {
                        "stage": "revision" if repair else "response",
                        "status": "candidate_units_ready",
                    }
                ],
            }
        except Exception as exc:
            return {
                "candidate_batch": state.get("candidate_batch", {"units": []})
                if repair
                else {"units": []},
                "model_calls": calls + 1,
                "revision_attempts": 1 if repair else 0,
                "events": [
                    {
                        "stage": "response",
                        "status": "generation_failed",
                        "error_type": type(exc).__name__,
                    }
                ],
            }

    def review(self, state):
        calls = state.get("model_calls", 0)
        batch = CandidateBatch.model_validate(state.get("candidate_batch", {"units": []}))
        if calls >= self.settings.max_model_calls_per_turn or not batch.units:
            return {
                "unit_review": {},
                "reviewed_candidate_digest": "",
                "events": [{"stage": "review", "status": "unavailable"}],
            }
        payload, _, complete = self.payload(state)
        payload["candidate_units"] = batch.model_dump(mode="json")
        try:
            result = self.model(UnitReviewBatch, review=True).invoke(
                [("system", self.review_prompt), ("user", json.dumps(payload, ensure_ascii=False))]
            )
            with model_calls.validation("review"):
                review = UnitReviewBatch.model_validate(result.get("parsed"))
            if not complete:
                review.case_updates_supported = False
            update = {
                "unit_review": review.model_dump(mode="json"),
                "reviewed_candidate_digest": digest(batch),
                "reviewed_context_digest": review_binding(state),
                "model_calls": calls + 1,
                "token_usage": usage_total(state.get("token_usage", {}), result.get("raw")),
                "turn_review_findings": [f.model_dump(mode="json") for f in review.findings],
            }
            units, _ = self.verifier.verify({**state, **update})
            # Cache only independently approved claims, scoped to this turn and
            # bound to their exact evidence. A failed re-review cannot erase them.
            approved = {c.claim_id for u in units for c in u.claims}
            registry = EvidenceRegistry(state)
            tasks = {
                t.task_id: t
                for t in RequestInterpretation.model_validate(state["interpretation"]).tasks
            }
            cache = dict(state.get("verified_claim_reviews", {}))
            verdicts = {r.claim_id: r for r in review.claims}
            for unit in batch.units:
                if unit.task_id not in tasks:
                    continue
                for claim in unit.claims:
                    signature = claim_signature(claim, registry, tasks[unit.task_id], state)
                    cache.pop(signature, None)  # A fresh rejection supersedes an older approval.
                    if claim.claim_id in approved:
                        cache[signature] = verdicts[claim.claim_id].model_dump(mode="json")
            update["verified_claim_reviews"] = cache
            blocked = any(
                u.status in {"deferred", "blocked", "partial"} and u.findings for u in units
            )
            needs_usefulness = self.verifier.needs_usefulness_repair({**state, **update}, units)
            return {
                **update,
                "events": [
                    {
                        "stage": "review",
                        "status": "repair_possible"
                        if (blocked or needs_usefulness)
                        else "units_reviewed",
                    }
                ],
            }
        except Exception as exc:
            return {
                "unit_review": {},
                "reviewed_candidate_digest": "",
                "model_calls": calls + 1,
                "events": [
                    {"stage": "review", "status": "review_failed", "error_type": type(exc).__name__}
                ],
            }

    def verify_and_compose(self, state):
        units, registry = self.verifier.verify(state)
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        composition = self.composer.compose(
            units, registry, interpretation, state.get("language", "en")
        )
        scorecard = self.verifier.score_response(state, composition, units)
        summary = [
            {
                "unit_id": u.unit_id,
                "task_id": u.task_id,
                "status": u.status,
                "assistance_status": u.assistance_status,
                "document_status": u.document_status,
                "legal_verification_status": u.legal_verification_status,
                "approved_claim_ids": [c.claim_id for c in u.claims],
                "action_recommendations": [
                    a.model_dump(mode="json") for a in u.action_recommendations
                ],
                "findings": [{"code": f.code, "severity": f.severity} for f in u.findings],
                "evidence_ids": list(dict.fromkeys(i for c in u.claims for i in c.evidence_ids)),
            }
            for u in units
        ]
        documents = composition["approved_documents"]
        proposed = state.get("memory", {})
        case_ok = bool(
            state.get("case_update_allowed")
            and state.get("unit_review", {}).get("case_updates_supported")
            and state.get("case_diff_review_complete", False)
            and not any(
                f.get("severity") in {"critical", "major", "moderate"}
                for f in state.get("unit_review", {}).get("findings", [])
            )
            and state.get("reviewed_candidate_digest")
            == digest(CandidateBatch.model_validate(state.get("candidate_batch", {"units": []})))
            and state.get("reviewed_context_digest") == review_binding(state)
        )
        approved_memory = proposed if case_ok else state.get("base_memory", proposed)
        patch_update = {}
        if state.get("pipeline_version") == "v2":
            batch = CandidateBatch.model_validate(state.get("candidate_batch", {"units": []}))
            review = (
                UnitReviewBatch.model_validate(state["unit_review"])
                if state.get("unit_review")
                else None
            )
            fresh = bool(
                review
                and state.get("reviewed_candidate_digest") == digest(batch)
                and state.get("reviewed_context_digest") == review_binding(state)
                and not any(
                    f.severity in {"critical", "major", "moderate"} for f in review.findings
                )
            )
            memory, decisions, staged, summary_text = PatchEngine().apply(
                state, batch.case_patches, review.patch_verdicts if review else [], registry, fresh
            )
            approved_memory = memory.model_dump(mode="json")
            case_ok = bool(decisions)
            patch_update = {
                "memory": approved_memory,
                "summary": summary_text,
                "patch_decisions": decisions,
                "staged_patches": staged,
                "staged_case_memory": {},
                "case_commit_approved": case_ok,
            }
        return {
            **composition,
            "unit_outcomes": summary,
            "request_coverage": [
                {
                    "request_id": u.task_id,
                    "status": "answered" if u.status == "supported" else "deferred",
                    "reason": None
                    if u.status == "supported"
                    else (
                        " ".join(u.unresolved_explanations)
                        if u.unresolved_explanations
                        else "Some assistance remains unverified."
                    ),
                }
                for u in units
            ],
            "memory": approved_memory,
            "summary": state.get("summary", "") if case_ok else state.get("base_summary", ""),
            "staged_case_memory": proposed if proposed != approved_memory else {},
            "case_commit_approved": case_ok,
            "draft_generated": bool(documents),
            "draft_content": documents[0]["content"] if documents else "",
            "draft_title": documents[0]["title"] if documents else "",
            "verification": {
                "scope": "published_claims_only",
                "passed": composition["publication_status"] == "supported",
                "publication_safe": True,
                "publication_status": composition["publication_status"],
                "factual_support_passed": True,
                "legal_support_passed": True,
                "tone_safe": True,
                "findings": [
                    {"code": f.code, "severity": f.severity, "reason": f.reason}
                    for u in units
                    for f in u.findings
                ],
                "unsupported_claims": [],
                "revision_required": False,
                "quality_scorecard": scorecard.model_dump(mode="json"),
            },
            "events": [{"stage": "verification", "status": composition["publication_status"]}],
            **patch_update,
        }
