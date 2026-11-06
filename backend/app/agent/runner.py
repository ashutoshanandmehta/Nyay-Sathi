"""One primary reasoning session, bounded research, adaptive review, existing commit boundary."""

import copy
import json
import time
from pathlib import Path

from app.agent.budget import TurnBudget
from app.agent.contracts import AgentAnswer, AgentTask, AnswerClaim, ResearchRequest
from app.agent.provider import ResponsesProvider
from app.agent.research import ResearchService
from app.agent.safety import safety_event, urgent_trigger
from app.agent.verification import (
    TEMPLATES,
    mechanical_checks,
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

        def event(stage, status="running", **extra):
            item = {"stage": stage, "status": status, **extra}
            state["events"].append(item)
            if progress:
                progress(item)

        def emit_safety():
            if state["safety_messages"]:
                return
            india = "india" in state["current_message"].casefold() or any(
                f.get("value", "").casefold() == "india"
                for k, f in state["memory"].get("facts", {}).items()
                if k in {"transaction_country", "country"}
            )
            item = safety_event(state.get("language", "en"), india=india)
            item["request_id"] = state["request_id"]
            state["safety_messages"].append(item)
            state["first_useful_guidance_ms"] = round((time.monotonic() - started) * 1000)
            # Durable before visibility: survives model/research failure and reload.
            database.save_safety(
                state["owner_id"], state["conversation_id"], state["request_id"], item
            )
            if progress:
                progress(item)

        if urgent_trigger(state["current_message"]):
            emit_safety()
        scope_token = publisher.set(progress)
        with model_calls.scope(
            self.settings.agent_max_requests,
            sink=lambda item: database.record_model_call(
                state["owner_id"], state["conversation_id"], state["request_id"], item
            ),
        ) as telemetry:
            try:
                answer, rounds = self._reason(state, budget, event, emit_safety)
                registry = EvidenceRegistry(state)
                blocked, accepted, pending = mechanical_checks(answer, registry)
                review, patch_verdicts = None, []
                if pending or answer.case_patches:
                    if budget.available():
                        event("review")
                        try:
                            review = self._review(answer, state, registry, budget)
                            patch_verdicts = review.patch_verdicts
                            accepted.update(self._reviewed(review, pending, answer, registry))
                            defects = [
                                c.claim_id for c in answer.claims if c.claim_id not in accepted
                            ]
                            if (
                                (
                                    defects
                                    or not review.primary_question_answered
                                    or not review.next_action_useful
                                )
                                and rounds < self.settings.agent_max_rounds
                                and budget.available(2)
                            ):
                                event("revision")
                                repaired = self._repair(answer, review, state, registry, budget)
                                if repaired.tasks != answer.tasks:
                                    raise ValueError("Repair changed task scope")
                                # Preserve supported claims byte-for-byte.
                                prior_accepted = dict(accepted)
                                stable = [c for c in answer.claims if c.claim_id in accepted]
                                repaired.claims = stable + [
                                    c for c in repaired.claims if c.claim_id not in accepted
                                ]
                                answer = AgentAnswer.model_validate(repaired.model_dump())
                                blocked, mechanical, pending = mechanical_checks(answer, registry)
                                accepted = {**prior_accepted, **mechanical}
                                event("review", phase="repair")
                                review = self._review(answer, state, registry, budget)
                                # A fresh semantic rejection supersedes an earlier approval;
                                # an unavailable re-review does not erase unchanged support.
                                for key in pending:
                                    accepted.pop(key, None)
                                accepted.update(self._reviewed(review, pending, answer, registry))
                                patch_verdicts = review.patch_verdicts
                        except Exception as exc:
                            event("review", "limited", error_type=type(exc).__name__)
                            # Keep only approvals bound to unchanged claims; patches remain staged.
                            patch_verdicts = []
                    else:
                        event("review", "budget_exhausted")
                accepted = propagate_dependencies(
                    answer, {k: v for k, v in accepted.items() if k not in blocked}
                )
                result = self._compose(
                    answer, state, registry, accepted, patch_verdicts, review is not None
                )
            except Exception as exc:
                event("primary", "fallback", error_type=type(exc).__name__)
                answer = self._fallback(
                    state, "limited_research" if self.settings.ai_configured else "configuration"
                )
                result = self._compose(
                    answer,
                    state,
                    EvidenceRegistry(state),
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

    def _context(self, state):
        registry = EvidenceRegistry(state)
        # Expose stable whole records. The current message is always verbatim and never dropped.
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
                )
            }
        private = [e for e in registry.payload() if e["kind"] != "public_passage"]
        bounded, used = [], 0
        for entry in private:
            size = len(json.dumps(entry, ensure_ascii=False))
            if used + size <= self.settings.agent_context_chars:
                bounded.append(entry)
                used += size
        return {
            "current_message": state["current_message"],
            "language": state.get("language", "en"),
            "segments": segment_message(state["current_message"]),
            "conversation_context": context,
            "case_version": state["memory"].get("version", 0),
            "case_domain": state["memory"].get("domain", "unknown"),
            "evidence": bounded + [e for e in registry.payload() if e["kind"] == "public_passage"],
            "templates": {
                key: template_text(key, state.get("language", "en")) for key in TEMPLATES
            },
            "safety_already_delivered": state.get("safety_messages", []),
        }

    def _reason(self, state, budget, event, emit_safety):
        if not self.settings.ai_configured:
            return self._fallback(state, "configuration"), 0
        items = [{"role": "user", "content": json.dumps(self._context(state), ensure_ascii=False)}]
        for round_index in range(self.settings.agent_max_rounds):
            event("primary", round=round_index + 1)
            allow_tools = (
                round_index + 1 < self.settings.agent_max_rounds
                and budget.available(3)
                and budget.batches < self.settings.agent_max_batches
            )
            output, calls, answer = self.provider.complete(
                items, self.prompt, budget, allow_tools=allow_tools
            )
            if answer is not None:
                if answer.risk == "urgent":
                    emit_safety()
                return answer, round_index + 1
            # Preserve encrypted reasoning and all original tool-call items, not just output text.
            items.extend(output)
            for call in calls:
                if call.get("name") == "emit_safety" and allow_tools:
                    emit_safety()
                    tool_result = {
                        "status": "delivered",
                        "approved_guidance": state["safety_messages"],
                    }
                elif call.get("name") != "research_legal_issue" or not allow_tools:
                    tool_result = {"status": "rejected", "limitations": ["Tool is unavailable."]}
                else:
                    try:
                        request = ResearchRequest.model_validate_json(call["arguments"])
                        event("web_research")
                        tool_result = self.research.run(request, state, budget)
                        event(
                            "web_research", "complete", duration_ms=tool_result.get("elapsed_ms", 0)
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
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
        raise ValueError("No final answer within primary-round allowance")

    def _review(self, answer, state, registry, budget):
        payload = {
            "context": self._context(state),
            "draft": answer.model_dump(mode="json"),
            "evidence": registry.payload(),
        }
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
        payload = {
            "context": self._context(state),
            "previous_answer": answer.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "instruction": "Repair only specific rejected claims and material omissions. Preserve tasks, evidence IDs and all supported claims. Do not add tools.",
        }
        _, calls, repaired = self.provider.complete(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            self.prompt,
            budget,
            allow_tools=False,
            stage="repair",
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
        pieces, documents, published, outcomes = [], [], set(), []
        for task in answer.tasks:
            claims = [c for c in answer.claims if c.task_id == task.task_id]
            visible, document = [], []
            for claim in claims:
                if claim.claim_id not in accepted:
                    continue
                text = (
                    template_text(claim.template_id, state.get("language", "en"))
                    if claim.kind == "template"
                    else ("You report: “" + claim.text + "”")
                    if claim.kind == "quote"
                    else claim.text
                )
                citation = registry.citations(claim.evidence_ids)
                visible.append(text + ("\n\n" + citation if citation else ""))
                published.update(set(claim.evidence_ids) & registry.public_ids())
                if claim.in_document:
                    document.append(text)
            if visible:
                pieces.append("\n\n".join(visible))
            if document and all(c.claim_id in accepted for c in claims if c.in_document):
                documents.append(
                    {
                        "task_id": task.task_id,
                        "unit_id": task.task_id,
                        "title": task.title,
                        "content": "\n\n".join(document),
                    }
                )
            outcomes.append(
                {
                    "task_id": task.task_id,
                    "status": "supported"
                    if all(c.claim_id in accepted for c in claims) and claims
                    else "partial"
                    if visible
                    else "deferred",
                }
            )
        rejected = (
            len(accepted) < len(answer.claims) or bool(answer.unresolved) or not answer.claims
        )
        if rejected or not pieces:
            pieces.append(template_text("limited_research", state.get("language", "en")))
        safety = [item["text"] for item in state.get("safety_messages", [])]
        state.update(
            response="\n\n".join(safety + pieces),
            approved_documents=documents,
            published_passage_ids=sorted(published),
            publication_status="partial" if rejected else "supported",
            verification={
                "passed": not rejected,
                "publication_safe": True,
                "scope": "published_claims_only",
                "claim_checks": accepted,
                "independent_review_performed": review_fresh,
                "legal_certification": False,
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
