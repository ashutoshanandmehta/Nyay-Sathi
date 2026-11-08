"""Durable reviewed turns, transactional patch receipts, post-commit delivery."""

import hashlib
import json
import os

from app.db import now
from app.routing.contracts import CaseUpdateProposal, RequestInterpretation
from app.routing.state_manager import CaseStateManager
from app.schemas.models import CaseMemory


class RequestConflict(ValueError):
    pass


def payload_hash(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class TurnPersistence:
    def __init__(self, database):
        self.db = database

    def _decode_row(self, cid: str, row) -> dict:
        item = dict(row)
        for col in ("verified_json", "result_json"):
            if item.get(col):
                item[col] = self.db.decrypt_case_field(cid, item[col])
        return item

    def get(self, owner, cid, request_id, digest=None):
        self.db.get_conversation(owner, cid)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM turn_executions WHERE conversation_id=? AND request_id=?",
                (cid, request_id),
            ).fetchone()
        if row and digest and row["payload_hash"] != digest:
            raise RequestConflict(
                "The request ID already belongs to a different message or attachments"
            )
        return self._decode_row(cid, row) if row else None

    def begin(self, owner, cid, request_id, digest):
        self.get(owner, cid, request_id, digest)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            running = conn.execute(
                "SELECT * FROM turn_executions t WHERE conversation_id=? AND status='running' AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id=t.conversation_id AND m.request_id=t.request_id AND m.role='assistant')",
                (cid,),
            ).fetchall()
            for row in running:
                raw_v = self.db.decrypt_case_field(cid, row["verified_json"] or "{}", _connection=conn)
                payload = json.loads(raw_v or "{}")
                try:
                    if payload.get("worker_pid", 0) <= 0:
                        raise ProcessLookupError()
                    os.kill(payload["worker_pid"], 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
                except PermissionError:
                    alive = True
                if alive:
                    raise RequestConflict(
                        "Another execution is running for this case. Retry after it finishes."
                    )
                conn.execute(
                    "UPDATE turn_executions SET status='interrupted', updated_at=? WHERE conversation_id=? AND request_id=?",
                    (now(), cid, row["request_id"]),
                )
            conn.execute(
                "INSERT INTO turn_executions VALUES (?, ?, ?, 'running', ?, NULL, NULL, ?) ON CONFLICT(conversation_id,request_id) DO UPDATE SET status='running', verified_json=excluded.verified_json, updated_at=excluded.updated_at WHERE turn_executions.status IN ('failed','interrupted')",
                (cid, request_id, digest, json.dumps({"worker_pid": os.getpid()}), now()),
            )
            current = conn.execute(
                "SELECT status FROM turn_executions WHERE conversation_id=? AND request_id=?",
                (cid, request_id),
            ).fetchone()
            if current[0] != "running":
                raise RequestConflict(
                    "A reviewed execution is ready to resume. Retry with the same request ID."
                )
        return self.get(owner, cid, request_id, digest)

    def mark(self, owner, cid, request_id, status):
        self.db.get_conversation(owner, cid)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE turn_executions SET status=?, updated_at=? WHERE conversation_id=? AND request_id=?",
                (status, now(), cid, request_id),
            )

    def reviewed(self, owner, cid, request_id, snapshot):
        self.db.get_conversation(owner, cid)
        with self.db.connect() as conn:
            enc = self.db.encrypt_case_field(cid, json.dumps(snapshot, default=str), _connection=conn)
            conn.execute(
                "UPDATE turn_executions SET status='reviewed', verified_json=?, updated_at=? WHERE conversation_id=? AND request_id=? AND status='running'",
                (enc, now(), cid, request_id),
            )

    def commit(self, owner, cid, request_id):
        record = self.get(owner, cid, request_id)
        if not record:
            raise RequestConflict("Turn is missing")
        if record["receipt_json"]:
            return json.loads(record["receipt_json"])
        if record["status"] != "reviewed":
            raise RequestConflict("Turn has no independently reviewed output to commit")
        snapshot = json.loads(record["verified_json"])
        state = snapshot["state"]
        before = CaseMemory.model_validate(snapshot["before"])
        proposal = CaseUpdateProposal(
            base_version=before.version,
            source_message_id=state["message_id"],
            source_task_ids=state.get("case_task_ids", []),
            proposed_memory=state["memory"],
            summary=state.get("summary", snapshot["base_summary"]),
        )
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT receipt_json FROM turn_executions WHERE conversation_id=? AND request_id=?",
                (cid, request_id),
            ).fetchone()
            if current and current[0]:
                return json.loads(current[0])
            updated = CaseStateManager(self.db).commit(
                owner_id=owner,
                conversation_id=cid,
                before=before,
                proposal=proposal,
                interpretation=RequestInterpretation.model_validate(state["interpretation"]),
                graph_state=state,
                _connection=conn,
            )
            for decision in state.get("patch_decisions", []) + state.get("staged_patches", []):
                conn.execute(
                    "INSERT OR IGNORE INTO case_patch_audit VALUES (?, ?, ?, ?, ?)",
                    (
                        cid,
                        request_id,
                        decision["patch"]["patch_id"],
                        decision["decision"],
                        json.dumps(decision),
                    ),
                )
            artifacts = []
            for index, artifact in enumerate(state.get("approved_documents", [])):
                if artifact.get("task_id") not in state.get("case_task_ids", []):
                    continue  # Document storage has a separate case-association gate.
                identifier = artifact.get("unit_id") or str(index)
                draft = self.db.create_draft(
                    owner,
                    cid,
                    artifact["title"],
                    artifact["content"],
                    updated.version,
                    _connection=conn,
                )
                conn.execute(
                    "INSERT INTO turn_artifacts VALUES (?, ?, ?, ?)",
                    (cid, request_id, identifier, draft["id"]),
                )
                artifacts.append(draft["id"])
            receipt = {
                "status": "committed"
                if updated.version != before.version
                else "staged_only"
                if state.get("staged_patches")
                else "no_change",
                "case_version": updated.version,
                "committed_patch_ids": [
                    d["patch"]["patch_id"] for d in state.get("patch_decisions", [])
                ],
                "staged_patch_ids": [
                    d["patch"]["patch_id"] for d in state.get("staged_patches", [])
                ],
                "artifact_ids": artifacts,
            }
            conn.execute(
                "UPDATE turn_executions SET status='committed', receipt_json=?, updated_at=? WHERE conversation_id=? AND request_id=?",
                (json.dumps(receipt), now(), cid, request_id),
            )
        return receipt

    def finalize(self, owner, cid, request_id):
        record = self.get(owner, cid, request_id)
        if record["status"] == "completed":
            return json.loads(record["result_json"])
        receipt = self.commit(owner, cid, request_id)
        snapshot = json.loads(record["verified_json"])
        state, user = snapshot["state"], snapshot["user"]
        metadata = {
            key: state.get(key, default)
            for key, default in {
                "verification": {},
                "token_usage": {},
                "events": [],
                "request_coverage": [],
                "interpretation": {},
                "task_plan": [],
                "tool_records": [],
                "unit_outcomes": [],
                "resolution_plan": {},
                "resolution_blocks": [],
                "factual_issues": [],
                "legal_issues": [],
                "case_stage": None,
                "next_action": None,
                "publication_status": None,
                "assistance_status": None,
                "document_status": None,
                "legal_verification_status": None,
                "call_telemetry": [],
                "usage_completeness": "unknown",
                "case_update_allowed": False,
                "engine_version": "legacy",
                "metrics": {},
                "safety_messages": [],
            }.items()
        }
        metadata.update(
            sources=snapshot["sources"],
            case_version=receipt["case_version"],
            commit_receipt=receipt,
        )
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            completed = conn.execute(
                "SELECT result_json FROM turn_executions WHERE conversation_id=? AND request_id=?",
                (cid, request_id),
            ).fetchone()
            if completed and completed[0]:
                dec = self.db.decrypt_case_field(cid, completed[0], _connection=conn)
                return json.loads(dec)
            assistant = self.db.add_message(
                cid,
                "assistant",
                state["response"],
                request_id,
                "complete",
                metadata,
                _connection=conn,
            )
            result = {
                "conversation_id": cid,
                "user_message": user,
                "assistant_message": assistant,
                "case_version": receipt["case_version"],
                "sources": snapshot["sources"],
                "verification": state.get("verification", {}),
                "token_usage": state.get("token_usage", {}),
                "ai_configured": snapshot["ai_configured"],
            }
            enc_res = self.db.encrypt_case_field(cid, json.dumps(result, default=str), _connection=conn)
            conn.execute(
                "UPDATE turn_executions SET status='completed', result_json=?, updated_at=? WHERE conversation_id=? AND request_id=?",
                (enc_res, now(), cid, request_id),
            )
        return result
