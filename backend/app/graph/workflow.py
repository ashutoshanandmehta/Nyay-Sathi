import copy
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.answers.pipeline import UnitPipeline
from app.config import Settings
from app.graph.state import LegalAssistantState
from app.rag.retrieval import HybridRetriever
from app.resolution.drafting import DraftPreparationService
from app.resolution.journey import ComplaintJourneyService, deterministic_journey_updates
from app.resolution.planner import ResolutionPlanner
from app.routing.contracts import RequestInterpretation
from app.routing.entities import EntityResolver
from app.routing.interpretation import (
    ContextualInterpreter,
    conservative_interpretation,
    source_span_matches,
)
from app.routing.policy import CapabilityRegistry, WorkflowPolicy
from app.routing.research import TaskResearchService
from app.routing.task_context import ApplicabilityPolicy, ExecutionBudget, TaskContext
from app.routing.validation import ExecutionValidator
from app.schemas.models import (
    CaseFact,
    CaseMemory,
    ExplicitRequest,
    FactStatus,
    Provenance,
    ResponseEnvelope,
    ResponseReview,
    VerificationFinding,
    VerificationResult,
)
from app.services.citations import canonicalise_source_markers, resolve_citations
from app.services.context_builder import ContextBuilder
from app.services.intake import (
    IntakeService,
    deterministic_extract,
    is_explicit_confirmation,
    is_explicit_correction,
)
from app.services.knowledge import SharedKnowledgeService
from app.services.model_calls import model_calls
from app.services.progress import observed, publisher
from app.services.request_coverage import (
    contains_internal_rendering,
    detect_explicit_requests,
    finalise_response,
    merge_requests,
)
from app.services.review_policy import ReviewPolicy
from app.services.web_research import WebResearchService

SUPPORTED = {"consumer"}


class AssistantGraph:
    def __init__(
        self,
        settings: Settings,
        retriever: HybridRetriever,
        *,
        interpreter=None,
        task_research=None,
    ):
        self.settings = settings
        self.retriever = retriever
        self.intake = IntakeService(settings)
        self.knowledge = SharedKnowledgeService()
        self.context_builder = ContextBuilder()
        self.unit_pipeline = UnitPipeline(
            settings, model_factory=lambda **kwargs: ChatOpenAI(**kwargs)
        )
        self.interpreter = interpreter or ContextualInterpreter(settings)
        self.task_research = task_research or TaskResearchService(settings)
        self.web_research = WebResearchService(settings)
        self.journey_service = ComplaintJourneyService()
        self.resolution_planner = ResolutionPlanner()
        self.entity_resolver = EntityResolver(self.resolution_planner.registry)
        self.draft_preparation = DraftPreparationService(self.resolution_planner.registry)
        prompt_dir = Path(__file__).parents[1] / "prompts" / "v1"
        self.system_prompt = (prompt_dir / "system.md").read_text()
        self.verification_prompt = (prompt_dir / "verification.md").read_text()
        self.connection = sqlite3.connect(settings.checkpoint_path, check_same_thread=False)
        serializer = JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=[])
        self.checkpointer = SqliteSaver(self.connection, serde=serializer)
        self.graph = self._build().compile(checkpointer=self.checkpointer)

    def _build(self) -> StateGraph:
        graph = StateGraph(LegalAssistantState)
        for name, operation in (
            ("triage", self.triage),
            ("intake", self.extract_and_update),
            ("research", self.research),
            ("assess_information", self.assess_information),
            ("web_research", self.expand_research),
            ("plan_resolution", self.plan_resolution),
            ("execute_tasks", self.execute_tasks),
            ("respond", self.respond),
            ("review", self.review_response),
            ("revise", self.revise_response),
            ("verify", self.verify),
        ):
            graph.add_node(name, observed(name, operation))
        graph.add_node("rereview", observed("review", self.review_response))
        graph.add_edge(START, "triage")
        graph.add_edge("triage", "intake")
        graph.add_conditional_edges(
            "intake",
            self.route_after_intake,
            {"research": "research", "respond": "plan_resolution"},
        )
        graph.add_edge("research", "assess_information")
        graph.add_conditional_edges(
            "assess_information",
            self.route_after_assessment,
            {"web_research": "web_research", "respond": "plan_resolution"},
        )
        graph.add_edge("web_research", "plan_resolution")
        graph.add_edge("plan_resolution", "execute_tasks")
        graph.add_edge("execute_tasks", "respond")
        graph.add_edge("respond", "review")
        graph.add_conditional_edges(
            "review", self.route_after_review, {"revise": "revise", "verify": "verify"}
        )
        graph.add_edge("revise", "rereview")
        graph.add_edge("rereview", "verify")
        graph.add_edge("verify", END)
        return graph

    def triage(self, state: LegalAssistantState) -> dict[str, Any]:
        context = {**state["context"], "case_domain": state["memory"].get("domain", "unknown")}
        calls, usage, diagnostics = state.get("model_calls", 0), {}, []
        try:
            if calls + 3 > self.settings.max_model_calls_per_turn and self.settings.ai_configured:
                interpretation = conservative_interpretation(state["current_message"], context)
                interpretation = interpretation.model_copy(
                    update={
                        "tasks": [
                            t.model_copy(
                                update={"case_link": "uncertain", "requires_case_update": False}
                            )
                            for t in interpretation.tasks
                        ],
                        "case_relevance": "uncertain",
                    }
                )
                status = "budget_fallback"
            else:
                calls += int(self.settings.ai_configured)
                interpretation, usage, status = self.interpreter.interpret(
                    state["current_message"], context
                )
            interpretation = RequestInterpretation.model_validate(interpretation)
            if interpretation.schema_version != "request-v2" and any(
                not source_span_matches(task.source_text, state["current_message"])
                for task in interpretation.tasks
            ):
                raise ValueError("Task source does not occur in this message")
        except Exception as exc:
            diagnostics = [
                {
                    "stage": "interpretation_validation",
                    "status": "failed",
                    "code": getattr(exc, "code", "contract_or_execution_failure"),
                    "task_ids": getattr(exc, "task_ids", []),
                    "error_type": type(exc).__name__,
                }
            ]
            # An interpretation failure must never fall back to permission to mutate.
            fallback = conservative_interpretation(state["current_message"], {})
            interpretation = fallback.model_copy(
                update={
                    "tasks": [
                        t.model_copy(
                            update={"requires_case_update": False, "case_link": "uncertain"}
                        )
                        for t in fallback.tasks
                    ],
                    "case_relevance": "uncertain",
                    "clarification_needed": True,
                }
            )
            status = "failed_" + type(exc).__name__
        if not context.get("case_confirmation_eligible", False):
            interpretation = interpretation.model_copy(
                update={
                    "tasks": [
                        task.model_copy(
                            update={"case_link": "uncertain", "requires_case_update": False}
                        )
                        if task.intent == "confirmation"
                        else task
                        for task in interpretation.tasks
                    ]
                }
            )
        permitted = WorkflowPolicy.case_tasks(
            interpretation, CaseMemory.model_validate(state["memory"])
        )
        investigation = WorkflowPolicy.investigate_tasks(interpretation)
        plan = WorkflowPolicy.plan(interpretation)
        total = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
        return {
            "interpretation": interpretation.model_dump(mode="json"),
            "interpretation_status": status,
            "entity_candidates": self.entity_resolver.candidates(interpretation),
            "task_plan": [p.model_dump(mode="json") for p in plan],
            "tool_records": [],
            "capabilities": CapabilityRegistry(self.settings).snapshot(calls),
            "case_task_ids": [t.task_id for t in permitted],
            "case_proposal_task_ids": [t.task_id for t in investigation],
            "case_input": "\n".join(dict.fromkeys(t.source_text for t in investigation)),
            "case_update_allowed": bool(permitted),
            "unit_protocol": True,
            "pipeline_version": "v2" if interpretation.schema_version == "request-v2" else "legacy",
            "patch_decisions": [],
            "staged_patches": [],
            "early_extraction": {},
            "base_memory": copy.deepcopy(state["memory"]),
            "base_summary": state.get("summary", ""),
            "task_contexts": [TaskContext.for_task(t).payload() for t in interpretation.tasks],
            "candidate_batch": {"units": []},
            "unit_review": {},
            "reviewed_candidate_digest": "",
            "reviewed_context_digest": "",
            "verified_claim_reviews": {},
            "turn_review_findings": [],
            "corpus_version": getattr(self.retriever, "corpus_version", "unknown"),
            "exposed_evidence_ids": [],
            "unit_outcomes": [],
            "staged_case_memory": {},
            "approved_documents": [],
            "published_passage_ids": [],
            "model_calls": calls,
            "token_usage": total,
            "events": diagnostics + [{"stage": "triage", "status": status, "tasks": len(plan)}],
        }

    def extract_and_update(self, state: LegalAssistantState) -> dict[str, Any]:
        if state.get("pipeline_version") == "v2":
            return self.prepare_v2(state)
        if "interpretation" in state and not state.get(
            "case_proposal_task_ids", state.get("case_task_ids")
        ):
            interpretation = RequestInterpretation.model_validate(state["interpretation"])
            consumer = any(t.domain == "consumer" for t in interpretation.tasks)
            return {
                "intent": "conversation",
                "scope": "consumer" if consumer else "general",
                "needs_retrieval": consumer
                and any(
                    t.requires_research for t in interpretation.tasks if t.domain == "consumer"
                ),
                "request_plan": self.task_requests(interpretation),
                "shared_guidance": {},
                "intake_questions": [],
                "urgent_reason": None,
                "events": [{"stage": "intake", "status": "case_write_not_permitted"}],
            }
        memory = CaseMemory.model_validate(state["memory"])
        case_input = state.get("case_input") or state["current_message"]
        state = {**state, "current_message": case_input}
        guidance = self.knowledge.guidance_for(memory, case_input)
        intake_model_call = 0
        if (
            self.settings.ai_configured
            and state.get("model_calls", 0) + 3 + int(bool(state.get("unit_protocol")))
            > self.settings.max_model_calls_per_turn
        ):
            extraction, usage = deterministic_extract(case_input), {}
        else:
            intake_model_call = int(
                self.settings.ai_configured
                and not ReviewPolicy.simple_intake(case_input, state["context"])
            )
            extraction, usage = self.intake.extract(case_input, state["context"], guidance)
        if state.get("interpretation"):
            interpretation = RequestInterpretation.model_validate(state["interpretation"])
            domains = {
                t.domain
                for t in interpretation.tasks
                if t.task_id in state.get("case_proposal_task_ids", state.get("case_task_ids", []))
            }
            mapped = {"tenancy": "landlord_deposit", "other_legal": "other_unsupported"}
            if len(domains) == 1:
                domain = mapped.get(next(iter(domains)), next(iter(domains)))
                if (memory.domain, domain) in {("unpaid_salary", "employment")}:
                    domain = memory.domain
                extraction = extraction.model_copy(update={"domain": domain})
        provenance = Provenance(source_type="message", source_id=state["message_id"])
        confirmed_existing = False
        changed_material = False
        if is_explicit_confirmation(state["current_message"]):
            # Confirmation is scoped to the facts most recently put forward for
            # review. A casual confirmation must never promote every allegation in
            # an unrelated part of the case.
            for key in memory.last_proposed_fact_keys:
                fact = memory.facts.get(key)
                if fact and fact.status == FactStatus.ALLEGED:
                    fact.status = FactStatus.CONFIRMED
                    fact.provenance.append(
                        Provenance(source_type="message", source_id=state["message_id"])
                    )
                    confirmed_existing = True
            if confirmed_existing:
                memory.pending_questions = [
                    item
                    for item in memory.pending_questions
                    if item.get("kind") != "fact_confirmation"
                ]
                memory.last_proposed_fact_keys = []
        if extraction.domain != "unknown":
            if memory.domain != extraction.domain:
                changed_material = True
            memory.domain = extraction.domain
        explicit_correction = is_explicit_correction(state["current_message"])
        proposed_fact_keys: list[str] = []
        for item in extraction.proposed_facts:
            key, value = item.get("key"), item.get("value")
            if not key or value is None:
                continue
            if key == "requested_remedy":
                continue
            existing = memory.facts.get(key)
            if existing and existing.value != value:
                existing.previous_values.append(
                    {
                        "value": existing.value,
                        "changed_by": state["message_id"],
                        "changed_at": __import__("datetime")
                        .datetime.now(__import__("datetime").UTC)
                        .isoformat(),
                        "confirmation_status": "explicit_correction"
                        if explicit_correction
                        else "unconfirmed_conflict",
                    }
                )
                memory.contradictions.append(
                    {
                        "key": key,
                        "old": existing.value,
                        "new": value,
                        "description": f"Conflicting values for {key}: {existing.value} and {value}.",
                        "resolved": explicit_correction,
                    }
                )
                if explicit_correction:
                    existing.value = value
                    existing.status = FactStatus.CONFIRMED
                    existing.provenance.append(provenance)
                    proposed_fact_keys.append(key)
                changed_material = True
            elif not existing:
                memory.facts[key] = CaseFact(
                    key=key,
                    value=value,
                    status=FactStatus(item.get("status", "user_allegation")),
                    provenance=[provenance],
                )
                proposed_fact_keys.append(key)
                changed_material = True
            else:
                proposed_fact_keys.append(key)
        if proposed_fact_keys:
            memory.last_proposed_fact_keys = list(dict.fromkeys(proposed_fact_keys))
        for item in extraction.parties:
            record = {
                **item.model_dump(mode="json"),
                "status": FactStatus.ALLEGED.value,
                "source_type": "message",
                "source_id": state["message_id"],
            }
            if not any(
                existing.get("name") == record["name"] and existing.get("role") == record["role"]
                for existing in memory.parties
            ):
                memory.parties.append(record)
                changed_material = True
        for item in extraction.locations:
            record = {
                **item.model_dump(mode="json"),
                "status": FactStatus.ALLEGED.value,
                "source_type": "message",
                "source_id": state["message_id"],
            }
            if not any(
                existing.get("value") == record["value"] and existing.get("role") == record["role"]
                for existing in memory.locations
            ):
                memory.locations.append(record)
                changed_material = True
        for item in extraction.events:
            record = {
                **item.model_dump(mode="json"),
                "status": FactStatus.ALLEGED.value,
                "source_type": "message",
                "source_id": state["message_id"],
            }
            if not any(
                existing.get("date") == record["date"]
                and existing.get("description") == record["description"]
                for existing in memory.events
            ):
                memory.events.append(record)
                changed_material = True
        if extraction.requested_remedy:
            if memory.requested_remedy and memory.requested_remedy != extraction.requested_remedy:
                memory.contradictions.append(
                    {
                        "key": "requested_remedy",
                        "old": memory.requested_remedy,
                        "new": extraction.requested_remedy,
                        "description": "The requested remedy changed; confirm the current objective.",
                        "resolved": explicit_correction,
                        "source_id": state["message_id"],
                    }
                )
                changed_material = True
            if memory.requested_remedy is None or (
                memory.requested_remedy != extraction.requested_remedy and explicit_correction
            ):
                memory.requested_remedy = extraction.requested_remedy
                memory.requested_remedy_provenance.append(provenance)
                changed_material = True
        for action in extraction.completed_actions:
            if action not in memory.actions_completed:
                memory.actions_completed.append(action)
                memory.action_provenance.setdefault(action, []).append(provenance)
                changed_material = True
        for item in extraction.responses_received:
            record = {
                **item.model_dump(mode="json"),
                "status": FactStatus.ALLEGED.value,
                "source_type": "message",
                "source_id": state["message_id"],
            }
            if record not in memory.responses_received:
                memory.responses_received.append(record)
                changed_material = True
        for item in extraction.correspondence:
            record = {
                **item.model_dump(mode="json"),
                "status": FactStatus.ALLEGED.value,
                "source_type": "message",
                "source_id": state["message_id"],
            }
            if record not in memory.correspondence_history:
                memory.correspondence_history.append(record)
                changed_material = True
        if extraction.urgent_reason and not any(
            item.get("reason") == extraction.urgent_reason for item in memory.urgent_matters
        ):
            memory.urgent_matters.append(
                {
                    "reason": extraction.urgent_reason,
                    "source_type": "message",
                    "source_id": state["message_id"],
                }
            )
            changed_material = True
        recipient = self.resolution_planner.resolver.resolve(memory, state["current_message"])
        proposals = extraction.journey_updates or deterministic_journey_updates(
            state["current_message"], recipient
        )
        proposals = [
            p.model_copy(
                update={
                    "recipient": self.resolution_planner.resolver.canonical_recipient(p.recipient)
                    or recipient
                }
            )
            for p in proposals
        ]
        changed_journey = self.journey_service.apply(
            memory.journey,
            proposals,
            message_id=state["message_id"],
            evidence=state["context"].get("relevant_evidence", []),
            source_text=state["current_message"],
        )
        lower = state["current_message"].casefold()
        satisfaction = (
            "dissatisfied"
            if re.search(
                r"(?:i(?:'m| am)?|still) (?:not satisfied|unhappy|dissatisfied)|not happy with",
                lower,
            )
            else "accepted"
            if re.search(
                r"\bi (?:am |'m )?(?:satisfied|happy with the resolution)|i accept (?:the |this )?resolution",
                lower,
            )
            else None
        )
        if satisfaction and satisfaction != memory.journey.satisfaction:
            memory.journey.satisfaction = satisfaction
            memory.journey.satisfaction_sources.append(state["message_id"])
            changed_journey = True
        if extraction.urgent_reason:
            memory.journey.severity = "urgent"
        if any(
            term in lower
            for term in ("contaminated", "food poisoning", "unsafe food", "expired food")
        ):
            memory.journey.severity = "safety"
        budget = memory.facts.get("budget_inr")
        if budget:
            memory.journey.preferences.budget_inr = budget.value
            memory.journey.preferences.source_ids = list(
                dict.fromkeys(
                    memory.journey.preferences.source_ids + [p.source_id for p in budget.provenance]
                )
            )
        if re.search(r"\b(?:low effort|least effort|minimum effort|avoid paperwork)\b", lower):
            memory.journey.preferences.effort_preference = "low"
            memory.journey.preferences.source_ids = list(
                dict.fromkeys(memory.journey.preferences.source_ids + [state["message_id"]])
            )
        if changed_material or confirmed_existing or changed_journey:
            memory.version += 1
            for recommendation in memory.journey.recommendations:
                recommendation.stale = True
        if extraction.intent == "draft" and not memory.facts:
            memory.unknowns = list(
                dict.fromkeys(memory.unknowns + ["Facts needed for a personalised draft"])
            )
        summary = self.context_builder.rolling_summary(memory)
        resolved_intent = (
            "draft" if confirmed_existing and state.get("intent") == "draft" else extraction.intent
        )
        requests = merge_requests(
            detect_explicit_requests(state["current_message"]), extraction.explicit_requests
        )
        if state.get("interpretation"):
            requests = [
                ExplicitRequest.model_validate(item)
                for item in self.task_requests(
                    RequestInterpretation.model_validate(state["interpretation"])
                )
            ]
        total_usage = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            total_usage[key] = total_usage.get(key, 0) + value
        return {
            "memory": memory.model_dump(mode="json"),
            "summary": summary,
            "intent": resolved_intent,
            "scope": memory.domain,
            "urgent_reason": extraction.urgent_reason,
            "needs_retrieval": (
                any(
                    t["domain"] == "consumer" and t["requires_research"]
                    for t in state["interpretation"]["tasks"]
                )
                if state.get("unit_protocol")
                else extraction.needs_legal_retrieval
                or any(item.requires_legal_retrieval for item in requests)
                or (memory.domain == "consumer" and resolved_intent == "options")
            ),
            "shared_guidance": guidance,
            "intake_questions": extraction.questions[:2],
            "request_plan": [item.model_dump(mode="json") for item in requests],
            "token_usage": total_usage,
            "model_calls": state.get("model_calls", 0) + intake_model_call,
            "events": [
                {
                    "stage": "intake",
                    "status": "complete",
                    "proposed_updates": len(extraction.proposed_facts)
                    + len(extraction.parties)
                    + len(extraction.locations)
                    + len(extraction.events)
                    + len(extraction.responses_received)
                    + len(extraction.correspondence)
                    + int(bool(extraction.requested_remedy)),
                    "confirmed_existing": confirmed_existing,
                    "explicit_requests": len(requests),
                }
            ],
        }

    @staticmethod
    def route_after_intake(state: LegalAssistantState) -> str:
        return "research" if state.get("needs_retrieval") else "respond"

    def research(self, state: LegalAssistantState) -> dict[str, Any]:
        consumer_tasks = [
            t for t in state.get("interpretation", {}).get("tasks", []) if t["domain"] == "consumer"
        ]
        if state.get("unit_protocol") and not consumer_tasks:
            return {
                "passages": [],
                "events": [{"stage": "research", "status": "corpus_policy_restricted"}],
            }
        consumer_text = "\n".join(
            t["source_text"]
            for t in state.get("interpretation", {}).get("tasks", [])
            if t["domain"] == "consumer"
        )
        rewritten = self.retriever.rewrite_query(
            consumer_text or state["current_message"], state["context"]
        )
        if state.get("unit_protocol"):
            task = RequestInterpretation.model_validate(state["interpretation"]).tasks
            context = TaskContext.for_task(next(t for t in task if t.domain == "consumer"))
            passages = self.retriever.search(rewritten, limit=5, task_context=context)
        else:
            passages = self.retriever.search(rewritten, limit=5)
        return {
            "rewritten_query": rewritten,
            "passages": passages,
            "events": [{"stage": "research", "status": "complete", "passages": len(passages)}],
        }

    def assess_information(self, state):
        if state.get("pipeline_version") == "v2":
            return {
                "research_status": "cached_candidates"
                if state.get("passages")
                else "no_cached_candidates",
                "research_plan": {},
                "events": [
                    {
                        "stage": "assess_information",
                        "status": "deterministic_candidate_check_not_legal_verification",
                    }
                ],
            }
        return self.web_research.assess(state)

    @staticmethod
    def route_after_assessment(state):
        plan = state.get("research_plan", {})
        return (
            "web_research"
            if state.get("research_status") == "search" and plan.get("queries")
            else "respond"
        )

    def expand_research(self, state):
        return self.web_research.expand(state)

    def plan_resolution(self, state):
        if state.get("interpretation") and not any(
            t["domain"] == "consumer" for t in state["interpretation"]["tasks"]
        ):
            return {"resolution_plan": {}, "draft_spec": {}}
        memory = CaseMemory.model_validate(state["memory"])
        if memory.domain not in {"consumer", "unknown"}:
            return {"resolution_plan": {}, "draft_spec": {}}
        v2 = state.get("pipeline_version") == "v2"
        planning_memory = memory.model_copy(deep=True)
        if v2 and planning_memory.domain == "unknown":
            planning_memory.domain = (
                "consumer"  # Read-only task interpretation, never a committed fact.
            )
        elif memory.domain == "unknown" and not memory.facts and not memory.journey.events:
            return {"resolution_plan": {}, "draft_spec": {}}
        legal_message = (
            state.get("case_input")
            or "\n".join(
                t["source_text"]
                for t in state.get("interpretation", {}).get("tasks", [])
                if t["domain"] == "consumer"
            )
            or state["current_message"]
        )
        recommendation = self.resolution_planner.recommend(planning_memory, legal_message)
        if not v2 and state.get("case_update_allowed", True):
            memory.journey.recommendations = (memory.journey.recommendations + [recommendation])[
                -20:
            ]
        interp = state.get("interpretation", {})
        has_draft_task = any(
            t.get("intent") in {"draft", "revision"} for t in interp.get("tasks", [])
        ) or "complaint_draft" in interp.get("requested_deliverables", [])
        draft_intent = (
            "draft" if (state.get("intent") == "draft" or has_draft_task) else state.get("intent")
        )
        spec = self.draft_preparation.prepare(memory, recommendation, legal_message, draft_intent)
        if spec and not v2 and state.get("case_update_allowed", True):
            memory.last_draft_spec = spec
        passages = {p["passage_id"]: p for p in state.get("passages", [])}
        for passage in self.resolution_planner.registry.policy_passages():
            passages.setdefault(passage["passage_id"], passage)
        return {
            "passages": list(passages.values()),
            "memory": memory.model_dump(mode="json"),
            "resolution_plan": recommendation.model_dump(mode="json"),
            "draft_spec": spec.model_dump(mode="json") if spec else {},
            "events": [{"stage": "plan_resolution", "status": "complete"}],
        }

    @staticmethod
    def task_requests(interpretation):
        kinds = {
            "information": "explanation",
            "search": "explanation",
            "legal_options": "options",
            "evidence": "evidence_checklist",
            "summary": "factual_summary",
            "confirmation": "case_update",
            "conversation": "other",
            "clarify": "other",
        }
        return [
            {
                "request_id": t.task_id,
                "kind": kinds.get(t.intent, t.intent),
                "request_text": t.source_text,
                "requires_legal_retrieval": t.domain
                in {"consumer", "employment", "tenancy", "criminal", "other_legal"}
                and t.requires_research,
            }
            for t in interpretation.tasks
        ]

    @staticmethod
    def routing_context(state):
        return (
            "\nTRUSTED ROUTING CONTRACT AND ACTUAL EXECUTIONS (internal; never render keys)\n"
            + json.dumps(
                {
                    "interpretation": state.get("interpretation", {}),
                    "entity_candidates": state.get("entity_candidates", []),
                    "tasks": state.get("task_plan", []),
                    "capabilities": state.get("capabilities", {}),
                    "executions": state.get("tool_records", []),
                    "case_update_allowed": state.get("case_update_allowed", False),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    def execute_tasks(self, state):
        if not state.get("interpretation"):
            return {}
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        working = dict(state)
        records, events, results = [], [], []
        searches = sum(
            1
            for e in state.get("events", [])
            if e.get("stage") == "web_search" and e.get("status") in {"complete", "unavailable"}
        )
        documents = len(state.get("web_sources", []))
        passages = list(state.get("passages", []))
        reused = []
        for plan in WorkflowPolicy.plan(interpretation):
            task = next(t for t in interpretation.tasks if t.task_id == plan.task_id)
            factual_preparation = task.intent in {"draft", "revision", "summary", "evidence"}
            if not task.requires_research or factual_preparation:
                results.append(
                    plan.model_copy(
                        update={
                            "research_status": "not_required_for_factual_preparation"
                            if factual_preparation
                            else "not_required",
                            "status": "ready",
                        }
                    ).model_dump(mode="json")
                )
                continue
            shared = next(
                (
                    (old, record, found)
                    for old, record, found in reused
                    if ApplicabilityPolicy.can_share(old, task)
                ),
                None,
            )
            if shared:
                old, original, found = shared
                for passage in found:
                    passage["applicable_task_ids"] = list(
                        dict.fromkeys(
                            passage.get("applicable_task_ids", [old.task_id]) + [task.task_id]
                        )
                    )
                record = {
                    "tool": "evidence_reuse",
                    "task_id": task.task_id,
                    "status": "succeeded",
                    "source_task_id": old.task_id,
                    "source_ids": original["source_ids"],
                }
            elif (
                task.domain == "consumer"
                and state.get("research_status") == "fetched_pending_review"
            ):
                for passage in passages:
                    if passage.get("origin") == "web":
                        passage["applicable_task_ids"] = list(
                            dict.fromkeys(passage.get("applicable_task_ids", []) + [task.task_id])
                        )
                record = {
                    "tool": "web_search",
                    "task_id": task.task_id,
                    "status": "succeeded",
                    "source_ids": [s["source_id"] for s in state.get("web_sources", [])],
                }
            elif (
                task.domain == "consumer"
                and (
                    state.get("research_status") in {"sufficient", "cached_candidates"}
                    or (
                        passages
                        and any(c.get("profile_id") for c in state.get("entity_candidates", []))
                    )
                )
                and task.intent != "search"
                and (
                    state.get("pipeline_version") != "v2"
                    or any(ApplicabilityPolicy.cache_recent(p) for p in passages)
                )
                and not any(
                    term in (task.public_query or "").casefold()
                    for term in (
                        "latest",
                        "current filing",
                        "changed",
                        "new rules",
                        "deadline",
                        "contact details",
                    )
                )
            ):
                record = {
                    "tool": "legal_corpus",
                    "task_id": task.task_id,
                    "status": "succeeded",
                    "source_ids": list({p["source_id"] for p in passages}),
                }
            elif searches >= self.settings.web_max_queries:
                record = {
                    "tool": "web_search",
                    "task_id": task.task_id,
                    "status": "budget_exhausted",
                    "source_ids": [],
                }
            else:
                record, found, calls, usage = self.task_research.run(
                    task, working, documents_remaining=self.settings.web_max_documents - documents
                )
                working.update(model_calls=calls, token_usage=usage)
                searches += int("query" in record or record["status"] == "execution_failed")
                documents += record.get("documents_attempted", 0)
                passages.extend(found)
                if record["status"] == "succeeded":
                    reused.append((task, record, found))
            records.append(record)
            if record["status"] == "succeeded" and record["tool"] == "web_search":
                records.append(
                    {
                        "tool": "source_fetch",
                        "task_id": task.task_id,
                        "status": "succeeded",
                        "source_ids": record["source_ids"],
                    }
                )
            results.append(
                plan.model_copy(
                    update={
                        "status": "researched" if record["status"] == "succeeded" else "deferred",
                        "research_status": record["status"],
                    }
                ).model_dump(mode="json")
            )
            events.append(
                {"stage": "task_research", "task_id": task.task_id, "status": record["status"]}
            )
        return {
            "task_plan": results,
            "tool_records": records,
            "passages": list({p["passage_id"]: p for p in passages}.values())[:16],
            "capabilities": CapabilityRegistry(self.settings).snapshot(
                working.get("model_calls", 0)
            ),
            "model_calls": working.get("model_calls", 0),
            "token_usage": working.get("token_usage", {}),
            "events": events + [{"stage": "execute_tasks", "status": "complete"}],
        }

    def _offline_response(self, state: LegalAssistantState) -> str:
        memory = CaseMemory.model_validate(state["memory"])
        facts = (
            ", ".join(
                v.value.replace("_", " ") for k, v in memory.facts.items() if k != "issue_type"
            )
            or "the details you shared"
        )
        urgent = (
            f"\n\n**Why prompt professional help matters:** {state['urgent_reason']}"
            if state.get("urgent_reason")
            else ""
        )
        limitation = ""
        if memory.domain not in SUPPORTED and memory.domain != "unknown":
            limitation = (
                "\n\nThis issue is outside the current deep consumer-dispute coverage. "
                "I can keep organising the facts and prepare a factual handoff, but I will not make unsupported legal conclusions."
            )
        return (
            (
                "I saved this turn and organised the case facts I could identify: "
                if state.get("case_update_allowed", True)
                else "Your message is saved in this chat. The existing case has not been changed: "
            )
            + facts
            + "."
            + limitation
            + urgent
            + "\n\n**AI configuration required:** add `OPENAI_API_KEY` to the backend environment to generate or review a conversational answer. "
            "Until then, chat history, case organisation, uploads, source browsing, and exports remain available. "
            "No canned legal answer has been substituted for a live model response."
        )

    def model_memory(self, state):
        interpretation = state.get("interpretation")
        if interpretation and not any(
            t["case_link"] == "existing" or t["task_id"] in state.get("case_task_ids", [])
            for t in interpretation["tasks"]
        ):
            return {}
        return self.context_builder.for_model(state["memory"])

    def respond(self, state: LegalAssistantState) -> dict[str, Any]:
        if state.get("unit_protocol") and self.settings.ai_configured:
            return self.unit_pipeline.generate(state)
        if not self.settings.ai_configured:
            return {
                "response": self._offline_response(state),
                "response_envelope": {},
                "events": [{"stage": "response", "status": "configuration_required"}],
            }
        if state.get("model_calls", 0) >= self.settings.max_model_calls_per_turn:
            return {
                "response": "I reached the configured model-call limit for this turn. Your message and case updates were saved; please retry.",
                "events": [{"stage": "response", "status": "budget_exhausted"}],
            }
        passages = state.get("passages", [])
        legal_context = (
            "\n\n".join(
                f"PASSAGE {p['passage_id']} | {p['title']} | {p['locator']}\n{p['text']}\nURL: {p['canonical_url']}\nLimitations: {p['limitations']}"
                for p in passages
            )
            or "No approved legal passages were retrieved. Withhold material legal conclusions."
        )
        model = ChatOpenAI(
            model=self.settings.openai_chat_model,
            api_key=self.settings.effective_openai_key,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        ).with_structured_output(ResponseEnvelope, method="json_schema", include_raw=True)
        result = model.invoke(
            [
                (
                    "system",
                    self.system_prompt
                    if state.get("case_update_allowed", True)
                    else self.system_prompt
                    + "\nThis turn has no case-write permission. Do not perform complaint intake for unrelated tasks. Do not call general facts legal advice. Answer each routed task and keep case records unchanged.",
                ),
                (
                    "user",
                    "CASE CONTEXT\n"
                    + self.routing_context(state)
                    + json.dumps(
                        {
                            k: v
                            for k, v in state["context"].items()
                            if k
                            in {
                                "runtime",
                                "current_message",
                                "pending_question_or_stage",
                                "rolling_summary",
                                "recent_turns",
                                "relevant_evidence",
                            }
                        },
                        ensure_ascii=False,
                    )
                    + "\n\nUPDATED MEMORY\n"
                    + json.dumps(self.model_memory(state), ensure_ascii=False)
                    + "\n\nRESOLUTION PREPARATION PLAN (application policy; eligibility gaps are not legal approval)\n"
                    + json.dumps(state.get("resolution_plan", {}), ensure_ascii=False)
                    + "\n\nCHANNEL-SPECIFIC DRAFT CONTRACT\n"
                    + json.dumps(state.get("draft_spec", {}), ensure_ascii=False)
                    + "\n\nAPPLICATION PLAYBOOK (not legal authority)\n"
                    + json.dumps(state.get("shared_guidance", {}), ensure_ascii=False)
                    + "\n\nPLAYBOOK-SUGGESTED INTAKE QUESTIONS (ask at most two, and only if unanswered)\n"
                    + json.dumps(state.get("intake_questions", []), ensure_ascii=False)
                    + "\n\nLATEST EXPLICIT REQUESTS (account for every request_id; do not show these IDs to the user)\n"
                    + json.dumps(state.get("request_plan", []), ensure_ascii=False)
                    + "\n\nAPPROVED LEGAL PASSAGES\n"
                    + legal_context
                    + "\n\nRESEARCH ASSESSMENT (internal; never render schema keys)\n"
                    + json.dumps(
                        {
                            "status": state.get("research_status"),
                            "assessment": state.get("research_plan", {}),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\nCURRENT MESSAGE\n"
                    + state["current_message"]
                    + "\n\nRESPONSE LANGUAGE\n"
                    + state.get("language", "en")
                    + "\n\nReturn a concise user-facing answer plus internal request coverage in the required schema. Cite supporting passages as [Source: title — locator]. End with a short legal-information disclaimer only when substantive legal information is given.",
                ),
            ]
        )
        envelope = result.get("parsed")
        if envelope is None:
            envelope = ResponseEnvelope(
                message_markdown="I could not prepare a reliable answer for this turn. Your message and case updates were saved; please retry.",
                request_coverage=[],
                follow_up_questions=[],
            )
        requests = [ExplicitRequest.model_validate(item) for item in state.get("request_plan", [])]
        response, coverage, questions = finalise_response(envelope, requests)
        response = canonicalise_source_markers(response, state.get("passages", []))
        memory = CaseMemory.model_validate(state["memory"])
        if questions and state.get("case_update_allowed", True):
            memory.pending_questions = (
                memory.pending_questions
                + [
                    {
                        "question": question,
                        "kind": "follow_up",
                        "source_message_id": state["message_id"],
                    }
                    for question in questions
                ]
            )[-3:]
        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        total_usage = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            if isinstance(value, int):
                total_usage[key] = total_usage.get(key, 0) + value
        return {
            "response": response,
            "response_envelope": envelope.model_dump(mode="json"),
            "request_coverage": [item.model_dump(mode="json") for item in coverage],
            "follow_up_questions": questions,
            "memory": memory.model_dump(mode="json"),
            "token_usage": total_usage,
            "model_calls": state.get("model_calls", 0) + 1,
            "draft_generated": bool(envelope.document_markdown)
            and any(item.kind in {"draft", "revision", "factual_summary"} for item in requests),
            "draft_content": envelope.document_markdown or "",
            "draft_title": envelope.document_title or "Prepared correspondence",
            "events": [{"stage": "response", "status": "complete"}],
        }

    def review_response(self, state: LegalAssistantState) -> dict[str, Any]:
        """Independent feedback pass before any candidate reaches persistence."""
        if state.get("unit_protocol") and self.settings.ai_configured:
            return self.unit_pipeline.review(state)
        if not self.settings.ai_configured:
            return {
                "feedback_review": {
                    "passed": True,
                    "factual_support_passed": True,
                    "legal_support_passed": True,
                    "tone_safe": True,
                    "request_coverage_passed": True,
                    "confirmation_handling_passed": True,
                    "findings": [],
                    "revision_instructions": [],
                },
                "events": [{"stage": "review", "status": "offline_safe"}],
            }
        if state.get("model_calls", 0) >= self.settings.max_model_calls_per_turn:
            review = ResponseReview(
                passed=False,
                factual_support_passed=False,
                legal_support_passed=False,
                tone_safe=False,
                request_coverage_passed=False,
                confirmation_handling_passed=False,
                findings=[
                    {
                        "code": "review_budget_exhausted",
                        "reason": "The feedback review could not run within the configured call budget.",
                    }
                ],
                revision_instructions=[],
            )
            return {
                "feedback_review": review.model_dump(mode="json"),
                "events": [{"stage": "review", "status": "budget_exhausted"}],
            }
        reviewer = ChatOpenAI(
            model=self.settings.openai_review_model,
            api_key=self.settings.effective_openai_key,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        ).with_structured_output(ResponseReview, method="json_schema", include_raw=True)
        result = reviewer.invoke(
            [
                ("system", self.verification_prompt),
                (
                    "user",
                    "LATEST REQUESTS\n"
                    + self.routing_context(state)
                    + "\nDETERMINISTIC EXECUTION FINDINGS\n"
                    + json.dumps(ExecutionValidator.check(state))
                    + json.dumps(state.get("request_plan", []), ensure_ascii=False)
                    + "\n\nCURRENT USER MESSAGE\n"
                    + state["current_message"]
                    + "\n\nRESOLUTION PLAN AND DRAFT CONTRACT\n"
                    + json.dumps(
                        {
                            "plan": state.get("resolution_plan", {}),
                            "draft": state.get("draft_spec", {}),
                            "document": state.get("draft_content", ""),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\nCASE MEMORY\n"
                    + json.dumps(self.model_memory(state), ensure_ascii=False)
                    + "\n\nPRIVATE EVIDENCE (untrusted documentary statements)\n"
                    + json.dumps(state["context"].get("relevant_evidence", []), ensure_ascii=False)
                    + "\n\nCITATION FORMAT CHECK\n"
                    + json.dumps(
                        {
                            "missing_marker": bool(
                                state.get("needs_retrieval")
                                and "[Source:" not in state.get("response", "")
                            ),
                            "unmatched_markers": resolve_citations(
                                state.get("response", ""), state.get("passages", [])
                            ).unsupported_markers,
                        }
                    )
                    + "\n\nCANDIDATE USER-FACING ANSWER\n"
                    + state.get("response", "")
                    + "\n\nCANDIDATE INTERNAL COVERAGE\n"
                    + json.dumps(state.get("request_coverage", []), ensure_ascii=False)
                    + "\n\nRESEARCH GAPS (internal; verify coverage or an honest deferral)\n"
                    + json.dumps(state.get("research_plan", {}), ensure_ascii=False)
                    + "\n\nAPPROVED PASSAGES\n"
                    + json.dumps(state.get("passages", []), ensure_ascii=False),
                ),
            ]
        )
        review = result.get("parsed") or ResponseReview(
            passed=False,
            factual_support_passed=False,
            legal_support_passed=False,
            tone_safe=False,
            request_coverage_passed=False,
            confirmation_handling_passed=False,
            findings=[
                {
                    "code": "review_parse_failed",
                    "reason": "The structured feedback review could not be parsed.",
                }
            ],
            revision_instructions=["Regenerate the answer conservatively."],
        )
        hard_findings = ExecutionValidator.check(state)
        if hard_findings:
            review = review.model_copy(
                update={
                    "passed": False,
                    "findings": review.findings
                    + [VerificationFinding.model_validate(f) for f in hard_findings],
                    "revision_instructions": review.revision_instructions
                    + [f["reason"] for f in hard_findings],
                }
            )
        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        total_usage = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            if isinstance(value, int):
                total_usage[key] = total_usage.get(key, 0) + value
        return {
            "feedback_review": review.model_dump(mode="json"),
            "token_usage": total_usage,
            "model_calls": state.get("model_calls", 0) + 1,
            "events": [
                {
                    "stage": "review",
                    "status": "passed" if review.passed else "revision_requested",
                }
            ],
        }

    def route_after_review(self, state: LegalAssistantState) -> str:
        if state.get("unit_protocol") and self.settings.ai_configured:
            units, _ = self.unit_pipeline.verifier.verify(state)
            recoverable = any(
                u.findings
                and any(
                    f.code not in {"review_missing", "missing_external_support"}
                    and f.severity in {"major", "moderate"}
                    for f in u.findings
                )
                for u in units
            )
            needs_usefulness = self.unit_pipeline.verifier.needs_usefulness_repair(state, units)
            return (
                "revise"
                if state.get("candidate_batch", {}).get("units")
                and (recoverable or needs_usefulness)
                and not state.get("revision_attempts")
                and ExecutionBudget(self.settings, state.get("model_calls", 0)).permits_repair()
                else "verify"
            )
        review = ResponseReview.model_validate(state.get("feedback_review", {}))
        can_revise = not review.passed and ReviewPolicy.may_revise(
            state.get("model_calls", 0),
            self.settings.max_model_calls_per_turn,
            state.get("revision_attempts", 0),
        )
        return "revise" if can_revise else "verify"

    def revise_response(self, state: LegalAssistantState) -> dict[str, Any]:
        """Apply one bounded feedback revision; the final hard gate runs afterwards."""
        if state.get("unit_protocol") and self.settings.ai_configured:
            return self.unit_pipeline.generate(state, repair=True)
        review = ResponseReview.model_validate(state["feedback_review"])
        reviser = ChatOpenAI(
            model=self.settings.openai_review_model,
            api_key=self.settings.effective_openai_key,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        ).with_structured_output(ResponseEnvelope, method="json_schema", include_raw=True)
        result = reviser.invoke(
            [
                (
                    "system",
                    self.system_prompt
                    + "\n\nYou are revising a candidate after independent feedback. Fix every finding. Do not expose the feedback, schema, or internal IDs in the user-facing message.",
                ),
                (
                    "user",
                    "LATEST REQUESTS\n"
                    + self.routing_context(state)
                    + json.dumps(state.get("request_plan", []), ensure_ascii=False)
                    + "\n\nCASE MEMORY\n"
                    + json.dumps(self.model_memory(state), ensure_ascii=False)
                    + "\n\nRESOLUTION PLAN AND DRAFT CONTRACT\n"
                    + json.dumps(
                        {
                            "plan": state.get("resolution_plan", {}),
                            "draft": state.get("draft_spec", {}),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\nPRIVATE EVIDENCE (untrusted documentary statements)\n"
                    + json.dumps(state["context"].get("relevant_evidence", []), ensure_ascii=False)
                    + "\n\nAPPROVED PASSAGES\n"
                    + json.dumps(state.get("passages", []), ensure_ascii=False)
                    + "\n\nCANDIDATE\n"
                    + state.get("response", "")
                    + "\n\nREVIEW FINDINGS\n"
                    + json.dumps(review.model_dump(mode="json"), ensure_ascii=False)
                    + "\n\nRESPONSE LANGUAGE\n"
                    + state.get("language", "en"),
                ),
            ]
        )
        envelope = result.get("parsed")
        if envelope is None:
            return {
                "revision_attempts": 1,
                "revision_succeeded": False,
                "events": [{"stage": "revision", "status": "parse_failed"}],
            }
        requests = [ExplicitRequest.model_validate(item) for item in state.get("request_plan", [])]
        response, coverage, questions = finalise_response(envelope, requests)
        response = canonicalise_source_markers(response, state.get("passages", []))
        memory = CaseMemory.model_validate(state["memory"])
        previous_pending = list(memory.pending_questions)
        memory.pending_questions = [
            item
            for item in memory.pending_questions
            if item.get("source_message_id") != state["message_id"]
        ]
        if questions:
            memory.pending_questions = (
                memory.pending_questions
                + [
                    {
                        "question": question,
                        "kind": "follow_up",
                        "source_message_id": state["message_id"],
                    }
                    for question in questions
                ]
            )[-3:]
        if not state.get("case_update_allowed", True):
            memory.pending_questions = previous_pending
        usage = getattr(result.get("raw"), "usage_metadata", None) or {}
        total_usage = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            if isinstance(value, int):
                total_usage[key] = total_usage.get(key, 0) + value
        return {
            "response": response,
            "response_envelope": envelope.model_dump(mode="json"),
            "request_coverage": [item.model_dump(mode="json") for item in coverage],
            "follow_up_questions": questions,
            "memory": memory.model_dump(mode="json"),
            "revision_attempts": 1,
            "revision_succeeded": True,
            "draft_generated": bool(envelope.document_markdown)
            and any(item.kind in {"draft", "revision", "factual_summary"} for item in requests),
            "draft_content": envelope.document_markdown or "",
            "draft_title": envelope.document_title or "Prepared correspondence",
            "token_usage": total_usage,
            "model_calls": state.get("model_calls", 0) + 1,
            "events": [{"stage": "revision", "status": "feedback_applied"}],
        }

    def verify(self, state: LegalAssistantState) -> dict[str, Any]:
        if state.get("unit_protocol") and self.settings.ai_configured:
            return self.unit_pipeline.verify_and_compose(state)
        if state.get("unit_protocol") and not state.get("case_update_allowed"):
            state = {
                **state,
                "staged_case_memory": state.get("memory", {}),
                "memory": state.get("base_memory", state.get("memory", {})),
                "summary": state.get("base_summary", ""),
            }
        if state.get("unit_protocol") and not self.settings.ai_configured:
            return {
                "memory": state["memory"],
                "summary": state.get("summary", ""),
                "staged_case_memory": state.get("staged_case_memory", {}),
                "case_commit_approved": state.get("case_update_allowed", False),
                "publication_status": "configuration_required",
                "verification": {
                    "passed": True,
                    "factual_support_passed": True,
                    "legal_support_passed": True,
                    "tone_safe": True,
                    "findings": [
                        {
                            "code": "offline",
                            "reason": "No AI content generated or semantically reviewed.",
                        }
                    ],
                    "unsupported_claims": [],
                    "revision_required": False,
                },
                "events": [{"stage": "verification", "status": "configuration_required"}],
            }
        response = state.get("response", "")
        passages = state.get("passages", [])
        substantive = state.get("needs_retrieval", False) or any(
            r.get("requires_legal_retrieval") for r in state.get("request_plan", [])
        )
        deterministic_findings = ExecutionValidator.check(state)
        passed = not deterministic_findings
        coverage = {item.get("request_id"): item for item in state.get("request_coverage", [])}
        legal_requests = [
            item for item in state.get("request_plan", []) if item.get("requires_legal_retrieval")
        ]
        legal_deferred = bool(legal_requests) and all(
            coverage.get(item.get("request_id"), {}).get("status") == "deferred"
            for item in legal_requests
        )
        if substantive and not passages and not legal_deferred:
            passed = False
            deterministic_findings.append(
                {
                    "code": "no_passages",
                    "reason": "Substantive legal output has no retrieved official passage.",
                }
            )
        if (
            substantive
            and passages
            and not legal_deferred
            and not resolve_citations(response, passages).cited_passage_ids
            and self.settings.ai_configured
        ):
            passed = False
            deterministic_findings.append(
                {
                    "code": "missing_citation",
                    "reason": "The answer did not expose a supporting source locator.",
                }
            )
        citation_resolution = resolve_citations(response, passages)
        if citation_resolution.unsupported_markers:
            passed = False
            deterministic_findings.append(
                {
                    "code": "unsupported_citation_marker",
                    "reason": "A visible citation did not match any passage retrieved for this turn.",
                }
            )
        if contains_internal_rendering(response) or contains_internal_rendering(
            state.get("draft_content", "")
        ):
            passed = False
            deterministic_findings.append(
                {
                    "code": "internal_state_leak",
                    "reason": "The candidate exposed an internal state or schema label.",
                }
            )
        if not self.settings.ai_configured:
            verification = VerificationResult(
                passed=True,
                factual_support_passed=True,
                legal_support_passed=True,
                tone_safe=True,
                findings=[{"code": "offline", "reason": "No legal answer was generated."}],
                unsupported_claims=[],
                revision_required=False,
            )
            return {
                "verification": verification.model_dump(),
                "events": [{"stage": "verification", "status": "offline_safe"}],
            }
        review_payload = state.get("feedback_review")
        review = (
            ResponseReview.model_validate(review_payload)
            if review_payload
            else ResponseReview(
                passed=False,
                factual_support_passed=False,
                legal_support_passed=False,
                tone_safe=False,
                request_coverage_passed=False,
                confirmation_handling_passed=False,
                findings=[
                    {
                        "code": "review_missing",
                        "reason": "No independent feedback result was available.",
                    }
                ],
                revision_instructions=[],
            )
        )
        revision_applied = bool(state.get("revision_succeeded", False))
        if not all(
            (
                review.passed,
                review.factual_support_passed,
                review.legal_support_passed,
                review.tone_safe,
                review.request_coverage_passed,
                review.confirmation_handling_passed,
            )
        ):
            passed = False
            deterministic_findings.extend(item.model_dump() for item in review.findings)
        verification = VerificationResult(
            passed=passed,
            factual_support_passed=review.factual_support_passed,
            legal_support_passed=review.legal_support_passed,
            tone_safe=review.tone_safe,
            findings=deterministic_findings
            + (
                [
                    {
                        "code": "feedback_applied",
                        "reason": "One bounded revision applied the independent review findings.",
                    }
                ]
                if revision_applied
                else []
            ),
            unsupported_claims=[],
            revision_required=not passed,
        )
        if not passed:
            safe = (
                "I saved your account, but I couldn’t verify the legal guidance for this turn, so I’ve withheld that part. "
                "You can still prepare the factual record: keep the order confirmation, invoice, payment record, "
                "and your correspondence together. Record what you ordered, what happened, and the resolution you want. "
                "These documents may support different parts of your account; none automatically proves the whole dispute."
            )
            if state.get("interpretation") and not state.get("case_update_allowed"):
                safe = "I couldn’t verify a reliable answer within this turn’s limits. Your message is saved, and your existing case is unchanged. You can narrow the question or try again later."
            return {
                "response": safe,
                "draft_generated": False,
                "verification": verification.model_dump(),
                "events": [{"stage": "verification", "status": "withheld"}],
            }
        return {
            "verification": verification.model_dump(),
            "events": [{"stage": "verification", "status": "passed_feedback_and_hard_gates"}],
        }

    def prepare_v2(self, state):
        """Read-only preparation. New facts remain proposals until post-review commit."""
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        relevant = [
            t for t in interpretation.tasks if t.task_id in state.get("case_proposal_task_ids", [])
        ]
        material_conflict = any(
            not c.get("resolved") for c in state["memory"].get("contradictions", [])
        )
        needed = any(
            t.needs_early_extraction
            or (material_conflict and t.requires_research and t.intent == "legal_options")
            for t in relevant
        )
        extraction, calls, usage, status = (
            {},
            state.get("model_calls", 0),
            {},
            "batched_with_generation",
        )
        if needed:
            if calls + 3 <= self.settings.max_model_calls_per_turn:
                result, usage = self.intake.extract(
                    state.get("case_input") or state["current_message"], state["context"], {}
                )
                extraction, calls, status = (
                    result.model_dump(mode="json"),
                    calls + 1,
                    "read_only_semantic_extraction",
                )
            else:
                status = "required_extraction_budget_exhausted"
        intent = (
            "draft"
            if any(t.intent in {"draft", "revision"} for t in interpretation.tasks)
            else "options"
            if any(t.intent == "legal_options" for t in interpretation.tasks)
            else "intake"
        )
        total = dict(state.get("token_usage", {}))
        for key, value in usage.items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
        return {
            "intent": intent,
            "scope": state["memory"].get("domain", "unknown"),
            "needs_retrieval": any(
                t.domain == "consumer" and t.requires_research for t in interpretation.tasks
            ),
            "request_plan": self.task_requests(interpretation),
            "early_extraction": extraction,
            "extraction_status": status,
            "model_calls": calls,
            "token_usage": total,
            "shared_guidance": {},
            "intake_questions": [],
            "urgent_reason": None,
            "events": [{"stage": "intake", "status": status}],
        }

    def invoke(
        self, state: LegalAssistantState, thread_id: str, progress=None
    ) -> LegalAssistantState:
        token = publisher.set(progress)
        try:
            from app.db import Database

            database = Database(self.settings.database_path)

            def sink(event):
                if state.get("request_id") and state.get("owner_id"):
                    database.record_model_call(
                        state["owner_id"], state["conversation_id"], state["request_id"], event
                    )

            with model_calls.scope(self.settings.max_model_calls_per_turn, sink=sink) as telemetry:
                try:
                    result = self.graph.invoke(
                        state, {"configurable": {"thread_id": thread_id}, "recursion_limit": 20}
                    )
                except Exception as exc:
                    exc.call_telemetry = telemetry.records
                    raise
                result["call_telemetry"] = telemetry.records
                if telemetry.records:
                    result["token_usage"] = telemetry.totals()
                    result["model_calls"] = sum(
                        r["category"] != "embedding" for r in telemetry.records
                    )
                result["usage_completeness"] = (
                    "complete"
                    if telemetry.records
                    and all(r["usage_completeness"] == "complete" for r in telemetry.records)
                    else "partial"
                    if any(r["usage_reported"] for r in telemetry.records)
                    else "unknown"
                )
                return result
        finally:
            publisher.reset(token)

    def delete_thread(self, thread_id: str) -> None:
        self.checkpointer.delete_thread(thread_id)
