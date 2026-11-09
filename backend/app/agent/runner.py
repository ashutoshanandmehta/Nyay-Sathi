"""Bounded 10-step resolution copilot runner with certified pre-retrieval and risk-calibrated review."""

import copy
import json
import re
import time
from pathlib import Path

from app.agent.blocks import (
    BLOCK_TITLES,
    append_citation_markers,
    assemble_resolution_blocks,
    claim_uses_legal_source,
    effective_block_order,
    format_claim_text,
    handoff_template_id,
    infer_block_type,
)
from app.agent.budget import TurnBudget
from app.agent.contracts import (
    AgentAnswer,
    AgentTask,
    AnswerClaim,
    RepairPatch,
    ResearchRequest,
)
from app.agent.provider import ResponsesProvider
from app.agent.research import ResearchService
from app.agent.safety import classify_urgent_context, detect_india_context, safety_event
from app.agent.verification import (
    TEMPLATES,
    is_sentence_complete,
    mechanical_checks,
    needs_semantic_review,
    propagate_dependencies,
    template_text,
)
from app.answers.evidence import EvidenceRegistry
from app.db import Database
from app.memory.patches import PatchEngine
from app.routing.contracts import RequestInterpretation, TaskIntent
from app.routing.policy import WorkflowPolicy
from app.routing.segments import segment_message
from app.schemas.models import CaseMemory
from app.services.model_calls import model_calls
from app.services.progress import publisher

# Everyday words people use, mapped to the legal concepts the local packs are indexed under.
CONCEPT_EXPANSIONS = (
    (
        re.compile(
            r"\b(?:jail|arrest\w*|custody|giraftar\w*|hirasat|lock-?up|thana)\b|जेल|गिरफ्तार|हिरासत",
            re.I,
        ),
        "bail custody arrest legal aid",
    ),
    (
        re.compile(r"\b(?:jail|arrest\w*|custody|giraftar\w*|hirasat)\b|जेल|गिरफ्तार|हिरासत", re.I),
        "free legal aid custody legal services",
    ),
    (
        re.compile(
            r"\b(?:complaint|fir|thana|police\s+station|report\s+to\s+police)\b|शिकायत|shikayat",
            re.I,
        ),
        "information cognizable offence police station complaint superintendent",
    ),
    (
        re.compile(
            r"\b(?:police\s+refused|not\s+registering|complaint\s+not\s+taken)\b|fir\s+nah[ií]\s+likh\w*|शिकायत\s+न(?:हीं|ही)\s+लिख\w*",
            re.I,
        ),
        "non-cognizable information superintendent magistrate investigate",
    ),
    (
        re.compile(
            r"\b(?:harass\w*|threat\w*|dhamki|pareshan)\b|परेशान|धमकी",
            re.I,
        ),
        "criminal intimidation",
    ),
    (
        re.compile(
            r"\b(?:abuse\w*|gaali|beat\w*|maar-?peet)\b|मारपीट|गाली",
            re.I,
        ),
        "criminal intimidation hurt wrongful restraint insult breach of peace",
    ),
    (
        re.compile(
            r"\b(?:land|zameen|jameen|khet|plot|kabza|boundary|encroach\w*)\b|ज़मीन|जमीन|खेत|कब्ज़ा|कब्जा",
            re.I,
        ),
        "land dispute possession breach of peace trespass mutation",
    ),
    (
        re.compile(
            r"\b(?:died|death|expired|inheritance|wirasat|waris|hissa|batwara|partition|property\s+share)\b|guzar\s+ga[ye]|गुज़र\s+गए|विरासत|वारिस|बंटवारा|हिस्सा|उत्तराधिकार",
            re.I,
        ),
        "succession heirs inheritance class I share coparcenary mutation",
    ),
    (
        re.compile(
            r"\b(?:salary|wages?|tankhwah|vetan|payslip)\b|वेतन|तनख्वाह",
            re.I,
        ),
        "wages payment claims",
    ),
    (
        re.compile(
            r"\b(?:lawyer(?:\s+fees?)?|free\s+lawyer|can['’]t\s+afford|vakil(?:\s+ka\s+paisa)?|advocate)\b|वकील|मुफ्त\s+वकील",
            re.I,
        ),
        "free legal aid legal services criteria",
    ),
    (
        re.compile(r"\b(?:car|vehicle|bike|scooter|truck|gaadi|gadi)\b|गाड़ी|गाडी", re.I),
        "vehicle seized confiscation release penalty",
    ),
)


def matched_concepts(message: str) -> list[str]:
    return [concepts for pattern, concepts in CONCEPT_EXPANSIONS if pattern.search(message)]


def _public_prequery_terms(
    message: str, domain: str, urgent_continuation: bool, emergency: bool = False
) -> str:
    # Strip identifiers, numbers, emails and quoted personal strings before local index lookup.
    cleaned = re.sub(r"\S+@\S+|https?://\S+|\b\d[\d\-/.,]*\b|[\"“”'‘’][^\"“”'‘’]*[\"“”'‘’]", " ", message)
    words = [w for w in re.findall(r"[A-Za-z\u0900-\u097f]{3,}", cleaned.casefold())][:48]
    extras = matched_concepts(message)
    if domain and domain not in {"unknown", "general"}:
        extras.append(domain)
    if urgent_continuation:
        extras.extend(["police", "bribe", "corruption", "emergency", "liberty"])
    elif emergency:
        extras.extend(["emergency", "response", "erss"])
    return " ".join(words + extras).strip()


class PrimaryAgent:
    engine_version = "primary-agent-v2.0"

    def __init__(self, settings, retriever, *, provider=None, research=None):
        self.settings, self.retriever = settings, retriever
        self.provider = provider or ResponsesProvider(settings)
        self.research = research or ResearchService(settings, retriever)
        prompts = Path(__file__).parents[1] / "prompts"
        self.prompt = (prompts / "primary.md").read_text()
        self.review_prompt = (prompts / "primary-review.md").read_text()

    def delete_thread(self, thread_id):
        # No provider-managed conversation or graph checkpoint is created by this runner.
        return None

    def _pre_retrieve_certified(self, state):
        if not hasattr(self.research, "retrieve_certified"):
            return
        # Follow-ups ("is that okay?") carry their topic in the user's earlier turns.
        earlier = [
            t.get("content", "")
            for t in state.get("context", {}).get("recent_turns", [])
            if t.get("role") == "user" and t.get("content") != state["current_message"]
        ][-2:]
        conversation_text = " ".join([state["current_message"], *reversed(earlier)])
        query_text = _public_prequery_terms(
            conversation_text,
            state.get("memory", {}).get("domain", "unknown"),
            bool(state.get("urgent_continuation")),
            emergency=bool(state.get("safety_messages")),
        )
        if len(query_text.split()) < 2:
            return
        # Certified propositions keep their own top-4 lookup; packs are searched separately below.
        hits, diag = self.research.retrieve_certified(
            query_text, jurisdiction="India", limit=4, exclude_origin="official_pack"
        )
        trusted = [h for h in hits if h.get("certified_proposition")]
        # Verbatim official sections go straight into the first call, so common questions need no
        # live search round. Their own floor keeps loosely related sections out.
        pack_hits, _ = self.research.retrieve_certified(
            query_text,
            jurisdiction="India",
            limit=12,
            min_relative_score=0.65,
            origin="official_pack",
        )
        # Each everyday concept gets its own small lookup, so a strong topic (say, Bihar liquor
        # law) cannot crowd out a needed one (free legal aid for someone in custody).
        concept_guaranteed = []
        concept_extras = []
        for concepts in matched_concepts(conversation_text):
            extra, _ = self.research.retrieve_certified(
                concepts, jurisdiction="India", limit=2, origin="official_pack"
            )
            if extra:
                concept_guaranteed.append(extra[0])
                concept_extras.extend(extra[1:])

        # Cap at agent_max_passages (8) for the first primary call, keeping order by relevance;
        # follow-up turns merging earlier conversation context allow up to agent_max_passages * 2.
        cap = self.settings.agent_max_passages if not earlier else self.settings.agent_max_passages * 2
        guaranteed_ids = {h["passage_id"] for h in concept_guaranteed}
        selected = list(concept_guaranteed)
        seen = set(guaranteed_ids)

        candidates = []
        for h in (trusted + pack_hits + concept_extras):
            if h["passage_id"] not in seen:
                seen.add(h["passage_id"])
                candidates.append(h)

        candidates.sort(key=lambda h: h.get("search_score", 0.0), reverse=True)
        for h in candidates:
            if len(selected) >= cap:
                break
            selected.append(h)

        trusted = selected
        if trusted:
            merged = {p["passage_id"]: p for p in state["passages"]}
            for hit in trusted:
                merged.setdefault(hit["passage_id"], hit)
            state["passages"] = list(merged.values())[:cap]
            state["tool_records"].append(
                {
                    "tool": "certified_knowledge_pack",
                    "status": "hit",
                    "query_hash": diag["query_hash"],
                    "certified_hit_count": sum(
                        1 for h in state["passages"] if h.get("certified_proposition")
                    ),
                    "official_pack_hit_count": sum(
                        1 for h in state["passages"] if h.get("origin") == "official_pack"
                    ),
                }
            )

    def invoke(self, state, thread_id, progress=None):
        state = copy.deepcopy(state)
        state.update(
            engine_version=self.engine_version,
            pipeline_version="v2",
            base_memory=copy.deepcopy(state["memory"]),
            base_summary=state.get("summary", ""),
            passages=[],
            events=[],
            tool_records=[],
            safety_messages=[],
        )
        database = Database(self.settings.database_path)
        started = time.monotonic()
        budget = TurnBudget(self.settings)

        try:
            prior_safety = database.safety_messages(state["owner_id"], state["conversation_id"])
        except KeyError:
            prior_safety = []
        urgent_ctx = classify_urgent_context(
            state["current_message"], state.get("memory"), prior_safety
        )
        state["urgent_continuation"] = urgent_ctx["urgent_continuation"]
        state["urgent_verification_guidance"] = urgent_ctx["verification_guidance"]
        state["prior_safety_delivered"] = bool(prior_safety)

        def event(stage, status="running", **extra):
            item = {"stage": stage, "status": status, **extra}
            state["events"].append(item)
            if progress:
                progress(item)

        def emit_safety(category=None, *, force=False):
            if state["safety_messages"] or (state.get("prior_safety_delivered") and not force):
                return
            india = detect_india_context(state["current_message"], state.get("memory"))
            cat = category or urgent_ctx["category"] or "emergency"
            if cat == "emergency_followup":
                cat = "emergency"
            item = safety_event(state.get("language", "en"), india=india, category=cat)
            item["request_id"] = state["request_id"]
            state["safety_messages"].append(item)
            state["first_useful_guidance_ms"] = round((time.monotonic() - started) * 1000)
            # Durable before visibility: survives model/research failure and reload.
            database.save_safety(
                state["owner_id"], state["conversation_id"], state["request_id"], item
            )
            if progress:
                progress(item)

        if urgent_ctx["emit_immediate_safety"]:
            emit_safety(urgent_ctx["category"])

        event(
            "context",
            "running",
            agent="Context & Intake Agent",
            tool="certified_knowledge_pack",
            action="Pre-fetching certified statutory provisions & intake facts",
            detail="Loading facts & certified knowledge pack",
        )
        self._pre_retrieve_certified(state)
        event(
            "context",
            "complete",
            agent="Context & Intake Agent",
            tool="certified_knowledge_pack",
            result=f"Loaded {len(state['passages'])} verified statutory provisions & facts",
            passages_count=len(state["passages"]),
            detail=f"Context ready ({len(state['passages'])} legal provisions loaded)",
        )

        scope_token = publisher.set(progress)
        with model_calls.scope(
            self.settings.agent_max_requests,
            sink=lambda item: database.record_model_call(
                state["owner_id"], state["conversation_id"], state["request_id"], item
            ),
        ) as telemetry:
            try:
                answer, rounds = self._reason(state, budget, event, emit_safety)
                if state.get("urgent_continuation"):
                    answer = self._enforce_urgent_followup_continuity(answer)
                registry = self._registry(state)
                blocked, accepted, pending = mechanical_checks(answer, registry)
                review, patch_verdicts = None, []
                if pending or answer.case_patches:
                    if budget.available():
                        event(
                            "review",
                            "running",
                            agent="Verifier Agent",
                            tool="verifier_evaluator",
                            action=f"Auditing grounding and citation integrity for {len(answer.claims)} claims",
                            detail="Verifier Agent auditing claims & legal citations",
                        )
                        try:
                            review = self._review(answer, state, registry, budget, pending)
                            patch_verdicts = review.patch_verdicts
                            accepted.update(self._reviewed(review, pending, answer, registry))
                            if not review.cross_block_coherent:
                                for verdict in review.claims:
                                    if verdict.support != "supported":
                                        accepted.pop(verdict.claim_id, None)
                            min_repair_seconds = getattr(
                                self.settings, "agent_repair_min_remaining_seconds", 25.0
                            )
                            repairs = 0
                            while (
                                (
                                    any(
                                        c.claim_id not in accepted
                                        and not c.optional
                                        and infer_block_type(c) != "human_handoff"
                                        for c in answer.claims
                                    )
                                    or not review.primary_question_answered
                                    or not review.next_action_useful
                                    or not review.cross_block_coherent
                                )
                                and repairs < self.settings.agent_max_repairs
                                and rounds < self.settings.agent_max_rounds
                                and budget.available(2)
                                and budget.remaining_time() >= min_repair_seconds
                            ):
                                repairs += 1
                                rounds += 1
                                unsupported = [
                                    c.claim_id
                                    for c in answer.claims
                                    if c.claim_id not in accepted
                                    and not c.optional
                                    and infer_block_type(c) != "human_handoff"
                                ]
                                what_went_wrong = (
                                    f"Verifier flagged {len(unsupported)} ungrounded claim(s)"
                                    if unsupported
                                    else "Incoherence detected across advice blocks"
                                    if not review.cross_block_coherent
                                    else "Primary legal question requires more specific guidance"
                                )
                                event(
                                    "revision",
                                    "running",
                                    agent="Feedback Repair Loop",
                                    tool="self_healing_repair",
                                    warning=what_went_wrong,
                                    attempt=repairs,
                                    action=f"Self-healing repair round {repairs}: {what_went_wrong}",
                                    detail=f"Feedback loop: {what_went_wrong} → Repairing",
                                )
                                original_patches = list(answer.case_patches)
                                prior_accepted = dict(accepted)
                                try:
                                    repaired = self._repair(answer, review, state, registry, budget)
                                    if isinstance(repaired, RepairPatch):
                                        existing_ids = {c.claim_id for c in answer.claims}
                                        for cid in repaired.removals:
                                            if cid not in existing_ids:
                                                raise ValueError(f"Repair patch referenced unknown removal claim: {cid}")
                                        for c in repaired.replacements:
                                            if c.claim_id not in existing_ids:
                                                raise ValueError(f"Repair patch referenced unknown replacement claim: {c.claim_id}")
                                        replacements_by_id = {c.claim_id: c for c in repaired.replacements}
                                        merged_claims = []
                                        for c in answer.claims:
                                            if c.claim_id in repaired.removals:
                                                continue
                                            if c.claim_id in replacements_by_id:
                                                merged_claims.append(replacements_by_id[c.claim_id])
                                            else:
                                                merged_claims.append(c)
                                        merged_claims.extend(repaired.additions)
                                        answer = answer.model_copy(update={"claims": merged_claims})
                                    elif isinstance(repaired, AgentAnswer):
                                        if repaired.tasks != answer.tasks:
                                            raise ValueError("Repair changed task scope")
                                        stable_by_id = {
                                            c.claim_id: c
                                            for c in answer.claims
                                            if c.claim_id in accepted
                                        }
                                        merged_claims = [
                                            stable_by_id.pop(c.claim_id)
                                            if c.claim_id in stable_by_id
                                            else c
                                            for c in repaired.claims
                                        ]
                                        repaired.claims = list(stable_by_id.values()) + merged_claims
                                        answer = AgentAnswer.model_validate(repaired.model_dump())
                                    else:
                                        raise ValueError("Unknown repair response type")
                                    blocked, mechanical, pending = mechanical_checks(
                                        answer, registry
                                    )
                                    accepted = {**prior_accepted, **mechanical}
                                    event(
                                        "review",
                                        "running",
                                        agent="Verifier Agent",
                                        tool="verifier_evaluator",
                                        phase="repair",
                                        action="Re-auditing repaired claims against statutory sources",
                                        detail="Re-verifying repaired draft against statutes",
                                    )
                                    re_review = self._review(
                                        answer, state, registry, budget, pending
                                    )
                                    review = re_review
                                    for key in pending:
                                        accepted.pop(key, None)
                                    accepted.update(
                                        self._reviewed(re_review, pending, answer, registry)
                                    )
                                    patch_verdicts = re_review.patch_verdicts
                                    event(
                                        "revision",
                                        "complete",
                                        agent="Feedback Repair Loop",
                                        tool="self_healing_repair",
                                        result="Claims revised to align strictly with verified statutory authorities",
                                        detail="Repair successful · Grounded against statutory authorities",
                                    )
                                except Exception as exc:
                                    event(
                                        "review",
                                        "limited",
                                        agent="Verifier Agent",
                                        error_type=type(exc).__name__,
                                        warning=f"Repair limited by {type(exc).__name__}",
                                    )
                                    if answer.case_patches != original_patches:
                                        patch_verdicts = []
                                    self._preserve_safe_practical(
                                        answer, accepted, blocked, registry
                                    )
                                    break
                        except Exception as exc:
                            event(
                                "review",
                                "limited",
                                agent="Verifier Agent",
                                error_type=type(exc).__name__,
                                warning=f"Review limited by {type(exc).__name__}",
                            )
                            patch_verdicts = []
                            self._preserve_safe_practical(answer, accepted, blocked, registry)
                    else:
                        event(
                            "review",
                            "budget_exhausted",
                            agent="Verifier Agent",
                            warning="Verification budget exhausted",
                        )
                        self._preserve_safe_practical(answer, accepted, blocked, registry)
                accepted = propagate_dependencies(
                    answer, {k: v for k, v in accepted.items() if k not in blocked}
                )
                event(
                    "structuring",
                    "running",
                    agent="Output Structuring Agent",
                    tool="format_composer",
                    action="Structuring response with numbered steps, checklists & citations",
                    detail="Structuring formatted response & citations",
                )
                result = self._compose(
                    answer, state, registry, accepted, patch_verdicts, review is not None
                )
                event(
                    "verify",
                    "passed",
                    agent="Output Certification Agent",
                    result="Output verified & certified for safe publication",
                    detail="Verified legal guidance ready · Certified",
                )
            except Exception as exc:
                event("primary", "fallback", error_type=type(exc).__name__)
                answer = self._fallback(
                    state, "limited_research" if self.settings.ai_configured else "configuration"
                )
                result = self._compose(
                    answer,
                    state,
                    self._registry(state),
                    {c.claim_id: "approved_template" for c in answer.claims},
                    [],
                    False,
                )
            finally:
                publisher.reset(scope_token)
        result["call_telemetry"] = telemetry.records
        result["token_usage"] = telemetry.totals()
        result["model_calls"] = len(telemetry.records)
        result["usage_completeness"] = (
            "complete"
            if telemetry.records
            and all(r["usage_completeness"] == "complete" for r in telemetry.records)
            else "partial"
            if any(r["usage_reported"] for r in telemetry.records)
            else "unknown"
        )
        result["metrics"] = {
            **budget.snapshot(),
            "total_ms": round((time.monotonic() - started) * 1000),
            "timing_scope": "runner; excludes API authorization and final database commit",
            "time_to_first_useful_guidance_ms": state.get(
                "first_useful_guidance_ms", round((time.monotonic() - started) * 1000)
            ),
            "reasoning_ms": sum(
                r.get("elapsed_ms", 0)
                for r in telemetry.records
                if r["stage"] in {"primary", "repair"}
            ),
            "review_ms": sum(
                r.get("elapsed_ms", 0) for r in telemetry.records if r["stage"] == "review"
            ),
            "retrieval_ms": sum(
                e.get("duration_ms", 0)
                for e in state["events"]
                if e.get("stage") == "web_research" and e.get("status") == "complete"
            ),
        }
        result["events"].append(
            {
                "stage": "complete",
                "status": result["publication_status"],
                "duration_ms": result["metrics"]["total_ms"],
            }
        )
        return result

    @staticmethod
    def _registry(state):
        return EvidenceRegistry(state, include_recent_user_turns=True)

    @staticmethod
    def _preserve_safe_practical(answer: AgentAnswer, accepted: dict, blocked: dict, registry):
        """When semantic review times out, preserve explicitly tagged non-confrontational practical/user claims."""
        public_ids = registry.public_ids()
        for claim in answer.claims:
            if (
                claim.claim_id not in accepted
                and claim.claim_id not in blocked
                and claim.grounding in {"practical_precaution", "reported_by_user"}
                and claim.kind in {"factual", "practical", "document"}
                and claim.block_type not in {"recommended_route", "human_handoff"}
                and claim.text.strip()
                and not needs_semantic_review(claim.text)
                and all(k in registry.entries and k not in public_ids for k in claim.evidence_ids)
            ):
                accepted[claim.claim_id] = "timeout_safe_practical_precaution"

    @staticmethod
    def _enforce_urgent_followup_continuity(answer: AgentAnswer) -> AgentAnswer:
        """Keep urgent follow-ups bound to the active urgent case rather than demoting to 'practice'."""
        updated_tasks = []
        for t in answer.tasks:
            intent = "legal_options" if t.intent in {"practice", "conversation"} else t.intent
            case_link = "existing" if t.case_link in {"new", "unrelated", "uncertain"} else t.case_link
            domain = "criminal" if t.domain in {"general", "unknown"} else t.domain
            updated_tasks.append(
                t.model_copy(update={"intent": intent, "case_link": case_link, "domain": domain})
            )
        risk = "urgent" if answer.risk == "ordinary" else answer.risk
        return answer.model_copy(update={"tasks": updated_tasks, "risk": risk})

    def _context(self, state):
        registry = self._registry(state)
        context = copy.deepcopy(state.get("context", {}))
        for key in ("recent_turns", "rolling_summary", "current_drafts", "staged_case_proposals"):
            if len(json.dumps(context, ensure_ascii=False)) > self.settings.agent_context_chars:
                context[key] = []
        if len(json.dumps(context, ensure_ascii=False)) > self.settings.agent_context_chars:
            context = {
                k: context.get(k)
                for k in (
                    "runtime",
                    "contradictions",
                    "actions_completed",
                    "responses_received",
                    "complaint_journey",
                    "prior_assistant_coverage",
                )
            }
        prior_cov = context.get("prior_assistant_coverage") or {}
        covered_sources = set(prior_cov.get("covered_source_ids") or [])
        private = [e for e in registry.payload() if e["kind"] != "public_passage"]
        bounded, used = [], 0
        for entry in private:
            size = len(json.dumps(entry, ensure_ascii=False))
            if used + size <= self.settings.agent_context_chars:
                bounded.append(entry)
                used += size
        public_entries = []
        for entry in registry.payload():
            if entry["kind"] != "public_passage":
                continue
            item = dict(entry)
            if covered_sources and (
                item.get("source_id") in covered_sources
                or item.get("passage_id") in covered_sources
                or item.get("evidence_id") in covered_sources
            ):
                item["already_cited_in_prior_turn"] = True
            public_entries.append(item)
        payload = {
            "current_message": state["current_message"],
            "language": state.get("language", "en"),
            "segments": segment_message(state["current_message"]),
            "conversation_context": context,
            "case_version": state["memory"].get("version", 0),
            "case_domain": state["memory"].get("domain", "unknown"),
            "evidence": bounded + public_entries,
            "templates": {
                key: template_text(key, state.get("language", "en")) for key in TEMPLATES
            },
            "safety_already_delivered": state.get("safety_messages", []),
        }
        if state.get("urgent_continuation"):
            payload["urgent_case_continuity"] = {
                "active_urgent_followup": True,
                "prior_safety_already_shown": bool(state.get("prior_safety_delivered")),
                "do_not_repeat_generic_safety_banner": True,
                "prior_assistant_turn_count": int(prior_cov.get("assistant_turn_count") or 0),
                "already_delivered_block_types": list(prior_cov.get("delivered_block_types") or []),
                "prioritize_new_turn_delta": bool(prior_cov.get("assistant_turn_count")),
                "recommended_verification_precautions": state.get(
                    "urgent_verification_guidance", []
                ),
            }
        return payload

    def _reason(self, state, budget, event, emit_safety):
        if not self.settings.ai_configured:
            return self._fallback(state, "configuration"), 0
        items = [{"role": "user", "content": json.dumps(self._context(state), ensure_ascii=False)}]
        for round_index in range(self.settings.agent_max_rounds):
            event(
                "primary",
                "running",
                agent="Primary Reasoning Agent",
                tool="reasoning_engine",
                round=round_index + 1,
                action=f"Synthesizing legal claims & response strategy (Round {round_index + 1})",
                detail=f"Synthesizing response & legal claims (Round {round_index + 1})",
            )
            allow_tools = (
                round_index + 1 < self.settings.agent_max_rounds
                and budget.available(3, reserve=self.settings.agent_repair_reserve)
                and budget.batches < self.settings.agent_max_batches
            )
            output, calls, answer = self.provider.complete(
                items, self.prompt, budget, allow_tools=allow_tools
            )
            if answer is not None:
                if answer.risk == "urgent":
                    emit_safety()
                return answer, round_index + 1
            items.extend(output)
            for call in calls:
                if call.get("name") == "emit_safety" and allow_tools:
                    emit_safety(force=not state.get("prior_safety_delivered"))
                    event(
                        "safety",
                        "delivered",
                        agent="Protective Safety Agent",
                        tool="emit_safety",
                        action="Issuing protective emergency advisory",
                        detail="Protective safety guidance delivered",
                    )
                    tool_result = {
                        "status": "delivered",
                        "approved_guidance": state["safety_messages"],
                    }
                elif call.get("name") != "research_legal_issue" or not allow_tools:
                    tool_result = {"status": "rejected", "limitations": ["Tool is unavailable."]}
                else:
                    try:
                        request = ResearchRequest.model_validate_json(call["arguments"])
                        search_query_str = (
                            ", ".join(q.query for q in request.questions[:2])
                            if getattr(request, "questions", None)
                            else "Statutory provisions"
                        )
                        event(
                            "web_research",
                            "running",
                            agent="Legal Retrieval Agent",
                            tool="research_legal_issue",
                            query=search_query_str,
                            action=f"Searching statutory corpus & official portals for: {search_query_str}",
                            detail=f"Searching legal provisions: {search_query_str}",
                        )
                        tool_result = self.research.run(request, state, budget)
                        fetched_count = len(tool_result.get("evidence", []))
                        event(
                            "web_research",
                            "complete",
                            agent="Legal Retrieval Agent",
                            tool="research_legal_issue",
                            result=f"Fetched {fetched_count} statutory passages from official registry",
                            duration_ms=tool_result.get("elapsed_ms", 0),
                            detail=f"Retrieved {fetched_count} verified legal passages ({tool_result.get('elapsed_ms', 0)}ms)",
                        )
                        state["tool_records"].extend(tool_result.get("tool_records", []))
                        merged = {p["passage_id"]: p for p in state["passages"]}
                        merged.update({p["passage_id"]: p for p in tool_result.get("evidence", [])})
                        state["passages"] = list(merged.values())[
                            : self.settings.agent_max_passages * 2
                        ]
                    except Exception as exc:
                        tool_result = {
                            "status": "unavailable",
                            "limitations": [type(exc).__name__],
                            "evidence": [],
                        }
                        event(
                            "web_research",
                            "failed",
                            agent="Legal Retrieval Agent",
                            tool="research_legal_issue",
                            warning=f"Retrieval limited: {type(exc).__name__}",
                            detail=f"Retrieval unavailable ({type(exc).__name__})",
                        )
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
        raise ValueError("No final answer within primary-round allowance")

    def _review(self, answer, state, registry, budget, pending=None):
        pending_list = list(pending) if pending is not None else [c.claim_id for c in answer.claims]
        pending_ids = set(pending_list)
        compact_claims = [
            {
                "claim_id": c.claim_id,
                "block_type": c.block_type or infer_block_type(c),
                "grounding": c.grounding,
                "kind": c.kind,
                "text": c.text,
                "evidence_ids": c.evidence_ids,
            }
            for c in answer.claims
        ]
        needed_evidence_ids = {
            eid
            for c in answer.claims
            if c.claim_id in pending_ids
            for eid in c.evidence_ids
        }
        review_evidence = [
            entry
            for entry in registry.payload()
            if entry.get("evidence_id") in needed_evidence_ids
        ]
        payload = {
            "context": self._context(state),
            "claims": compact_claims,
            "draft": {"claims": compact_claims},
            "pending_claim_ids": pending_list,
            "evidence": review_evidence,
        }
        if answer.case_patches:
            payload["case_patches"] = [p.model_dump(mode="json") for p in answer.case_patches]
        _, calls, review = self.provider.complete(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            self.review_prompt,
            budget,
            review=True,
            allow_tools=False,
            stage="review",
        )
        if calls or review is None:
            raise ValueError("Review did not complete")
        return review

    @staticmethod
    def _reviewed(review, pending, answer, registry):
        return {
            key: "independent_semantic_review"
            for key in pending
            if len([v for v in review.claims if v.claim_id == key]) == 1
            and next(v for v in review.claims if v.claim_id == key).support == "supported"
            and is_sentence_complete(next((c.text for c in answer.claims if c.claim_id == key), ""))
            and (
                not next(v for v in review.claims if v.claim_id == key).requires_public_evidence
                or any(
                    e in registry.public_ids()
                    for c in answer.claims
                    if c.claim_id == key
                    for e in c.evidence_ids
                )
            )
        }

    def _repair(self, answer, review, state, registry, budget):
        rejected_or_uncertain_ids = {
            v.claim_id
            for v in review.claims
            if v.support in {"unsupported", "uncertain"}
        }
        claims_to_repair = [
            c for c in answer.claims if c.claim_id in rejected_or_uncertain_ids
        ]
        other_claims_compact = [
            {"claim_id": c.claim_id, "block_type": c.block_type or infer_block_type(c), "text": c.text}
            for c in answer.claims
            if c.claim_id not in rejected_or_uncertain_ids
        ]
        needed_evidence_ids = {
            eid for c in claims_to_repair for eid in c.evidence_ids
        }
        cited_evidence = [
            entry
            for entry in registry.payload()
            if entry.get("evidence_id") in needed_evidence_ids
        ]
        payload = {
            "current_message": state.get("current_message", ""),
            "rejected_or_uncertain_claims": [c.model_dump(mode="json") for c in claims_to_repair],
            "repair_instructions": review.repair_instructions,
            "cited_evidence": cited_evidence,
            "other_claims": other_claims_compact,
            "prior_assistant_coverage": state.get("context", {}).get("prior_assistant_coverage", {}),
            "instruction": "Repair only specific rejected or uncertain claims. Propose replacements, removals or additions in a RepairPatch. Do not rewrite supported claims.",
            "context": self._context(state),
            "previous_answer": answer.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
        }
        repair_instructions = (
            "You are repairing specific rejected or uncertain claims. "
            "Return a RepairPatch with replacements, removals, or additions. "
            "Preserve verified statutory references and ensure claims end with terminal punctuation."
        )
        _, calls, repaired = self.provider.complete(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            repair_instructions,
            budget,
            allow_tools=False,
            stage="repair",
            schema=RepairPatch,
        )
        if calls or repaired is None:
            raise ValueError("Repair did not complete")
        return repaired

    @staticmethod
    def _fallback(state, template):
        return AgentAnswer(
            central_question="Respond to the current request within available evidence.",
            tasks=[
                AgentTask(
                    task_id="task-1",
                    title="Available help",
                    intent="conversation",
                    domain="general",
                    case_link="unrelated",
                )
            ],
            claims=[
                AnswerClaim(
                    claim_id="fallback",
                    task_id="task-1",
                    kind="template",
                    text="",
                    template_id=template,
                ),
                AnswerClaim(
                    claim_id="preserve",
                    task_id="task-1",
                    kind="template",
                    text="",
                    template_id="preserve_records",
                ),
            ],
        )

    def _compose(self, answer, state, registry, accepted, patch_verdicts, review_fresh):
        if not any(
            c.claim_id in accepted and infer_block_type(c) == "human_handoff" for c in answer.claims
        ) and (template_id := handoff_template_id(answer, state)):
            referral = AnswerClaim(
                claim_id="runtime-handoff",
                task_id=answer.tasks[-1].task_id,
                kind="template",
                text="",
                template_id=template_id,
                block_type="human_handoff",
            )
            answer = answer.model_copy(update={"claims": [*answer.claims, referral]})
            accepted = {**accepted, referral.claim_id: "approved_template"}
        segments = {s["id"]: s["text"] for s in segment_message(state["current_message"])}
        tasks = []
        domains = {
            "consumer",
            "employment",
            "tenancy",
            "criminal",
            "general",
            "health",
            "animal_health",
            "other_legal",
            "unknown",
        }
        for t in answer.tasks:
            refs = [r for r in t.source_segment_ids if r in segments]
            tasks.append(
                TaskIntent(
                    task_id=t.task_id,
                    source_text="\n".join(segments[r] for r in refs) or state["current_message"],
                    intent=t.intent,
                    domain=t.domain if t.domain in domains else "other_legal",
                    relationship=t.relationship,
                    entities=[],
                    case_link=t.case_link,
                    requires_research=False,
                    requires_case_update=any(p.task_id == t.task_id for p in answer.case_patches),
                    risk_level=answer.risk,
                    uncertainty=[],
                    public_query=None,
                    source_segment_ids=refs,
                )
            )
        interpretation = RequestInterpretation(
            schema_version="request-v2",
            tasks=tasks,
            case_relevance="mixed" if len({t.case_link for t in tasks}) > 1 else tasks[0].case_link,
            clarification_needed=False,
        )
        state["interpretation"] = interpretation.model_dump(mode="json")
        permitted = WorkflowPolicy.case_tasks(
            interpretation, CaseMemory.model_validate(state["base_memory"])
        )
        state["case_task_ids"] = [t.task_id for t in permitted]
        state["case_update_allowed"] = bool(permitted)
        memory, decisions, staged, summary = PatchEngine().apply(
            state, answer.case_patches, patch_verdicts, registry, review_fresh
        )
        state.update(
            memory=memory.model_dump(mode="json"),
            summary=summary,
            patch_decisions=decisions,
            staged_patches=staged,
            staged_case_memory={},
        )
        language = state.get("language", "en")
        block_order = effective_block_order(answer, state)
        order_rank = {bt: idx for idx, bt in enumerate(block_order)}
        pieces, documents, published, outcomes = [], [], set(), []
        # Passage ID -> in-text citation number, assigned in on-screen order across all tasks.
        citation_numbers: dict[str, int] = {}
        for task in answer.tasks:
            claims = [c for c in answer.claims if c.task_id == task.task_id]
            core_claims = [
                c for c in claims if not c.optional and infer_block_type(c) != "human_handoff"
            ]
            visible_ranked, document = [], []
            for idx, claim in enumerate(claims):
                if claim.claim_id not in accepted:
                    continue
                btype = infer_block_type(claim)
                text = format_claim_text(claim, language)
                cited_ids = (
                    [k for k in dict.fromkeys(claim.evidence_ids) if k in registry.public_ids()]
                    if claim_uses_legal_source(claim, btype)
                    else []
                )
                visible_ranked.append(
                    (
                        order_rank.get(btype, len(block_order)),
                        idx,
                        btype,
                        text,
                        cited_ids,
                    )
                )
                published.update(set(claim.evidence_ids) & registry.public_ids())
                if claim.in_document:
                    document.append(text)
            visible_ranked.sort(key=lambda item: (item[0], item[1]))

            section_groups: list[tuple[str, list[str]]] = []
            for item in visible_ranked:
                _, _, btype, text, cited_ids = item
                for passage_id in cited_ids:
                    citation_numbers.setdefault(passage_id, len(citation_numbers) + 1)
                claim_rendered = append_citation_markers(
                    text, sorted(citation_numbers[p] for p in cited_ids)
                )
                if not section_groups or section_groups[-1][0] != btype:
                    section_groups.append((btype, [claim_rendered]))
                else:
                    section_groups[-1][1].append(claim_rendered)

            lang_key = language if language in {"en", "hi", "hinglish"} else "en"
            formatted_sections: list[str] = []
            for btype, items in section_groups:
                if btype in {"immediate_actions", "alternatives", "recommended_route"} and len(items) > 1:
                    formatted_items = []
                    for idx, it in enumerate(items):
                        stripped = it.strip()
                        if not re.match(r"^(?:\d+[\.\)]|[-*•])\s+", stripped):
                            formatted_items.append(f"{idx + 1}. {stripped}")
                        else:
                            formatted_items.append(stripped)
                    joined = "\n\n".join(formatted_items)
                elif btype in {"evidence_checklist", "question", "limitation", "human_handoff"} and len(items) > 1:
                    formatted_items = []
                    for it in items:
                        stripped = it.strip()
                        if not re.match(r"^(?:\d+[\.\)]|[-*•])\s+", stripped):
                            formatted_items.append(f"- {stripped}")
                        else:
                            formatted_items.append(stripped)
                    joined = "\n\n".join(formatted_items)
                else:
                    joined = "\n\n".join(items)

                already_has_header = any(
                    ln.lstrip().startswith("#") for it in items for ln in it.splitlines()
                )
                if btype != "direct_answer" and not already_has_header and btype in BLOCK_TITLES:
                    header_title = BLOCK_TITLES[btype].get(lang_key, BLOCK_TITLES[btype]["en"])
                    formatted_sections.append(f"### {header_title}\n\n{joined}")
                else:
                    formatted_sections.append(joined)

            if formatted_sections:
                pieces.append("\n\n---\n\n".join(formatted_sections))
            if document and all(c.claim_id in accepted for c in claims if c.in_document):
                documents.append(
                    {
                        "task_id": task.task_id,
                        "unit_id": task.task_id,
                        "title": task.title,
                        "content": "\n\n".join(document),
                    }
                )
            task_supported = (
                all(c.claim_id in accepted for c in core_claims) and bool(core_claims or visible_ranked)
            )
            outcomes.append(
                {
                    "task_id": task.task_id,
                    "status": "supported" if task_supported else "partial" if visible_ranked else "deferred",
                }
            )

        core_all = [  # noqa: F841
            c for c in answer.claims if not c.optional and infer_block_type(c) != "human_handoff"
        ]
        task_all_supported = bool(outcomes) and all(o["status"] == "supported" for o in outcomes)
        core_rejected = (
            not task_all_supported
            or not answer.claims
            or not pieces
        )
        # Generic "I could not verify..." text appears ONLY when no useful supported answer exists.
        # A runtime referral alone is not an answer, so the honest message still leads.
        answered = any(
            c.claim_id in accepted and c.claim_id != "runtime-handoff" for c in answer.claims
        )
        if not answered:
            # Nothing else is published, so the text must not promise preparation "below".
            pieces.insert(0, template_text("no_verified_answer", language))

        resolution_blocks = assemble_resolution_blocks(
            answer, accepted, registry, state, documents
        )
        if not answered:
            resolution_blocks.insert(
                0,
                {
                    "block_id": "block-limitation",
                    "block_type": "limitation",
                    "title": "Unresolved point",
                    "content": pieces[0],
                    "items": [],
                    "claim_ids": [],
                    "source_ids": [],
                    "grounding": "requires_confirmation",
                    "document_title": None,
                },
            )
        elif not resolution_blocks and pieces:
            resolution_blocks = [
                {
                    "block_id": "block-limitation",
                    "block_type": "limitation",
                    "title": "Unresolved point",
                    "content": pieces[-1],
                    "items": [],
                    "claim_ids": [],
                    "source_ids": [],
                    "grounding": "requires_confirmation",
                    "document_title": None,
                }
            ]

        safety = [item["text"] for item in state.get("safety_messages", [])]
        certified_used = any(
            registry.entries.get(pid, {}).get("certified_proposition")
            for pid in published
        )
        state.update(
            response="\n\n".join(safety + pieces),
            resolution_blocks=resolution_blocks,
            factual_issues=answer.factual_issues,
            legal_issues=answer.legal_issues,
            case_stage=answer.case_stage or (memory.journey.outcome if memory.journey.outcome != "unknown" else "intake"),
            next_action=answer.next_action,
            approved_documents=documents,
            published_passage_ids=sorted(published),
            citations=[
                {"number": number, "passage_id": passage_id}
                for passage_id, number in citation_numbers.items()
            ],
            publication_status="partial" if core_rejected else "supported",
            verification={
                "passed": not core_rejected,
                "publication_safe": True,
                "scope": "published_claims_only",
                "claim_checks": accepted,
                "independent_review_performed": review_fresh,
                "legal_certification": certified_used,
            },
            request_coverage=[
                {
                    "request_id": o["task_id"],
                    "status": "answered" if o["status"] == "supported" else "deferred",
                    "reason": None
                    if o["status"] == "supported"
                    else "Some requested content could not be verified.",
                }
                for o in outcomes
            ],
            unit_outcomes=outcomes,
            task_plan=[p.model_dump(mode="json") for p in WorkflowPolicy.plan(interpretation)],
        )
        return state
