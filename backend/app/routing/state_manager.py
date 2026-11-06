"""Trusted runtime scope and validated proposals control persistent case writes."""

from app.routing.policy import WorkflowPolicy
from app.schemas.models import CaseMemory


class UnauthorizedCaseUpdate(ValueError):
    pass


class CaseStateManager:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def material_snapshot(memory):
        value = memory.model_dump(mode="json")
        for key in (
            "version",
            "pending_questions",
            "last_proposed_fact_keys",
            "last_draft_spec",
            "stale_draft_ids",
        ):
            value.pop(key, None)
        value.get("journey", {}).pop("recommendations", None)
        return value

    @staticmethod
    def validate(before, proposal, interpretation):
        after = CaseMemory.model_validate(proposal.proposed_memory)
        permitted = WorkflowPolicy.case_tasks(interpretation, before)
        permitted_ids = {task.task_id for task in permitted}
        if proposal.base_version != before.version:
            raise UnauthorizedCaseUpdate("Proposal base version does not match loaded case")
        if not set(proposal.source_task_ids) <= permitted_ids:
            raise UnauthorizedCaseUpdate("Proposal includes unauthorized task updates")
        changed = after.model_dump() != before.model_dump()
        if changed and (not permitted_ids or not proposal.source_task_ids):
            raise UnauthorizedCaseUpdate("This request cannot change private case state")
        if changed and after.version <= before.version:
            # Every committed semantic change must have a monotonic case version.
            after.version = before.version + 1
        if changed and after.journey.recommendations:
            after.journey.recommendations[-1].case_version = after.version
        if changed and after.last_draft_spec:
            after.last_draft_spec.case_version = after.version
        if after.version < before.version:
            raise UnauthorizedCaseUpdate("Case versions cannot move backwards")
        if before.domain != "unknown" and after.domain != before.domain:
            raise UnauthorizedCaseUpdate(
                "A new legal domain requires a separate case or targeted review"
            )
        for key, original in before.facts.items():
            if key not in after.facts:
                raise UnauthorizedCaseUpdate("Existing facts cannot be silently removed")
            updated = after.facts[key]
            if original.value != updated.value and not any(
                v.get("value") == original.value for v in updated.previous_values
            ):
                raise UnauthorizedCaseUpdate("Fact correction is missing its prior value")
        old_events = {event.id: event for event in before.journey.events}
        new_events = {event.id: event for event in after.journey.events}
        if any(new_events.get(key) != value for key, value in old_events.items()):
            raise UnauthorizedCaseUpdate("Complaint audit events cannot be rewritten")
        return after

    def commit(
        self,
        *,
        owner_id,
        conversation_id,
        before,
        proposal,
        interpretation,
        graph_state,
        _connection=None,
    ):
        # Owner/case scope is injected by the API, never selected by the model.
        self.database.get_conversation(owner_id, conversation_id)
        _, current_summary = self.database.load_memory(owner_id, conversation_id)
        if (
            not WorkflowPolicy.case_tasks(interpretation, before)
            and proposal.summary != current_summary
        ):
            raise UnauthorizedCaseUpdate("An unrelated request cannot rewrite the case summary")
        after = self.validate(before, proposal, interpretation)
        if after.journey.recommendations and graph_state.get("resolution_plan"):
            graph_state["resolution_plan"] = after.journey.recommendations[-1].model_dump(
                mode="json"
            )
        if graph_state.get("draft_spec"):
            graph_state["draft_spec"]["case_version"] = after.version
        allowed_sources = {proposal.source_message_id} | {
            item["id"] for item in self.database.attachments(owner_id, conversation_id)
        }
        for key, fact in after.facts.items():
            old = before.facts.get(key)
            if not old or old.value != fact.value:
                if not fact.provenance or any(
                    p.source_id not in allowed_sources and (not old or p not in old.provenance)
                    for p in fact.provenance
                ):
                    raise UnauthorizedCaseUpdate(
                        "New fact provenance is outside the authorized message/evidence scope"
                    )
        changed = after.model_dump() != before.model_dump()
        self.database.save_memory(
            conversation_id,
            after,
            proposal.summary,
            graph_state,
            expected_version=proposal.base_version,
            owner_id=owner_id,
            invalidate_drafts=self.material_snapshot(before) != self.material_snapshot(after),
            audit={
                "message_id": proposal.source_message_id,
                "task_ids": proposal.source_task_ids,
                "decision": "validated_commit" if changed else "no_case_change",
            },
            staged_proposal={
                "message_id": proposal.source_message_id,
                "task_ids": graph_state.get("case_proposal_task_ids", []),
                "memory": graph_state["staged_case_memory"],
            }
            if graph_state.get("staged_case_memory")
            else None,
            _connection=_connection,
        )
        return after
