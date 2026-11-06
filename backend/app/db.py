import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas.models import CaseMemory

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS owners (
  id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  title TEXT NOT NULL, language TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations(owner_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(conversation_id, request_id, role)
);
CREATE TABLE IF NOT EXISTS turn_safety (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, content_id TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(conversation_id, request_id, content_id)
);
CREATE TABLE IF NOT EXISTS case_memory (
  conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
  version INTEGER NOT NULL DEFAULT 0, memory_json TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  graph_state_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  filename TEXT NOT NULL, stored_path TEXT NOT NULL, mime_type TEXT NOT NULL, size INTEGER NOT NULL,
  extraction_status TEXT NOT NULL, extracted_text TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  title TEXT NOT NULL, content TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
  case_version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answer_sources (
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE, source_id TEXT NOT NULL,
  passage_id TEXT NOT NULL, locator TEXT, quote TEXT NOT NULL, PRIMARY KEY(message_id, passage_id)
);
CREATE TABLE IF NOT EXISTS request_events (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, status TEXT NOT NULL, error_code TEXT, updated_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, request_id)
);
CREATE TABLE IF NOT EXISTS research_sources (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, source_id TEXT NOT NULL, canonical_url TEXT NOT NULL,
  content_hash TEXT NOT NULL, original BLOB NOT NULL, passages_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(conversation_id, request_id, source_id)
);
CREATE TABLE IF NOT EXISTS complaint_events (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  event_id TEXT NOT NULL, payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, event_id)
);
CREATE TABLE IF NOT EXISTS resolution_recommendations (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  recommendation_id TEXT NOT NULL, case_version INTEGER NOT NULL,
  payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, recommendation_id)
);
CREATE TABLE IF NOT EXISTS case_update_audit (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL, base_version INTEGER NOT NULL, new_version INTEGER NOT NULL,
  task_ids_json TEXT NOT NULL, decision TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, message_id)
);
CREATE TABLE IF NOT EXISTS staged_case_updates (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL, base_version INTEGER NOT NULL,
  task_ids_json TEXT NOT NULL, proposed_memory_json TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, message_id)
);
CREATE TABLE IF NOT EXISTS model_call_events (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, call_id TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(conversation_id, request_id, call_id)
);
CREATE TABLE IF NOT EXISTS turn_executions (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, status TEXT NOT NULL,
  verified_json TEXT, receipt_json TEXT, result_json TEXT, updated_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, request_id)
);
CREATE TABLE IF NOT EXISTS case_patch_audit (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, patch_id TEXT NOT NULL, decision TEXT NOT NULL,
  payload_json TEXT NOT NULL, PRIMARY KEY(conversation_id, request_id, patch_id)
);
CREATE TABLE IF NOT EXISTS turn_artifacts (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
  draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  PRIMARY KEY(conversation_id, request_id, artifact_id)
);
"""


class MemoryConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def save_safety(self, owner, conversation_id, request_id, event):
        self.get_conversation(owner, conversation_id)
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO turn_safety VALUES (?,?,?,?,?)",
                (conversation_id, request_id, event["content_id"], json.dumps(event), now()),
            )

    def safety_messages(self, owner, conversation_id):
        self.get_conversation(owner, conversation_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT request_id, payload_json FROM turn_safety WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        return [
            {**json.loads(row["payload_json"]), "request_id": row["request_id"]} for row in rows
        ]

    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_owner(self, token_hash: str) -> str:
        owner_id = str(uuid.uuid4())
        with self.connect() as c:
            c.execute("INSERT INTO owners VALUES (?, ?, ?)", (owner_id, token_hash, now()))
        return owner_id

    def owner_for_hash(self, token_hash: str) -> str | None:
        with self.connect() as c:
            row = c.execute("SELECT id FROM owners WHERE token_hash=?", (token_hash,)).fetchone()
        return row["id"] if row else None

    def record_model_call(self, owner_id, cid, request_id, event):
        self.get_conversation(owner_id, cid)
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO model_call_events VALUES (?, ?, ?, ?)",
                (cid, request_id, event["call_id"], json.dumps(event)),
            )

    def model_call_events(self, owner_id, cid, request_id):
        self.get_conversation(owner_id, cid)
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload_json FROM model_call_events WHERE conversation_id=? AND request_id=?",
                    (cid, request_id),
                )
            ]

    def create_conversation(self, owner_id: str, language: str) -> dict[str, Any]:
        cid, timestamp = str(uuid.uuid4()), now()
        memory = CaseMemory().model_dump(mode="json")
        with self.connect() as c:
            c.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (cid, owner_id, "New case", language, timestamp, timestamp),
            )
            c.execute(
                "INSERT INTO case_memory VALUES (?, 0, ?, '', '{}', ?)",
                (cid, json.dumps(memory), timestamp),
            )
        return self.get_conversation(owner_id, cid)

    def get_conversation(self, owner_id: str, cid: str) -> dict[str, Any]:
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM conversations WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (cid, owner_id),
            ).fetchone()
        if not row:
            raise KeyError("conversation_not_found")
        return dict(row)

    def list_conversations(self, owner_id: str) -> list[dict[str, Any]]:
        sql = """SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id=c.id
                 ORDER BY created_at DESC LIMIT 1) last_message FROM conversations c
                 WHERE owner_id=? AND deleted_at IS NULL ORDER BY updated_at DESC"""
        with self.connect() as c:
            return [dict(x) for x in c.execute(sql, (owner_id,)).fetchall()]

    def rename_conversation(self, owner_id: str, cid: str, title: str) -> None:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            c.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=?", (title, now(), cid)
            )

    def delete_conversation(self, owner_id: str, cid: str) -> list[str]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            files = [
                r[0]
                for r in c.execute(
                    "SELECT stored_path FROM attachments WHERE conversation_id=?", (cid,)
                )
            ]
            c.execute("DELETE FROM conversations WHERE id=? AND owner_id=?", (cid, owner_id))
        return files

    def add_message(
        self,
        cid: str,
        role: str,
        content: str,
        request_id: str | None,
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
        _connection=None,
    ) -> dict[str, Any]:
        mid, timestamp = str(uuid.uuid4()), now()
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            try:
                c.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mid,
                        cid,
                        request_id,
                        role,
                        content,
                        status,
                        json.dumps(metadata or {}),
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError:
                row = c.execute(
                    "SELECT * FROM messages WHERE conversation_id=? AND request_id=? AND role=?",
                    (cid, request_id, role),
                ).fetchone()
                return self._message(dict(row))
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, cid))
            row = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        return self._message(dict(row))

    @staticmethod
    def _message(row: dict[str, Any]) -> dict[str, Any]:
        row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
        return row

    def messages(self, owner_id: str, cid: str, limit: int = 500) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT ?",
                (cid, limit),
            ).fetchall()
        return [self._message(dict(r)) for r in rows]

    def find_turn(self, cid: str, request_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=? AND request_id=? ORDER BY created_at",
                (cid, request_id),
            ).fetchall()
        mapped = [self._message(dict(r)) for r in rows]
        user = next((m for m in mapped if m["role"] == "user"), None)
        assistant = next((m for m in mapped if m["role"] == "assistant"), None)
        return (user, assistant) if user and assistant else None

    def delete_failed_assistant(self, cid: str, request_id: str) -> None:
        with self.connect() as c:
            c.execute(
                "DELETE FROM messages WHERE conversation_id=? AND request_id=? AND role='assistant' AND status='failed'",
                (cid, request_id),
            )

    def load_memory(self, owner_id: str, cid: str) -> tuple[CaseMemory, str]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            row = c.execute("SELECT * FROM case_memory WHERE conversation_id=?", (cid,)).fetchone()
        return CaseMemory.model_validate_json(row["memory_json"]), row["summary"]

    def save_memory(
        self,
        cid: str,
        memory: CaseMemory,
        summary: str,
        graph_state: dict[str, Any] | None = None,
        expected_version: int | None = None,
        invalidate_drafts: bool = False,
        audit: dict | None = None,
        owner_id: str | None = None,
        staged_proposal: dict | None = None,
        _connection=None,
    ) -> None:
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            if _connection is None:
                c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT version FROM case_memory WHERE conversation_id=?", (cid,)
            ).fetchone()
            if not existing:
                raise KeyError("conversation_not_found")
            if (
                owner_id is not None
                and not c.execute(
                    "SELECT 1 FROM conversations WHERE id=? AND owner_id=?", (cid, owner_id)
                ).fetchone()
            ):
                raise KeyError("conversation_not_found")
            if expected_version is not None and existing["version"] != expected_version:
                raise MemoryConflict(
                    "Case changed during processing; retry safely with the same request ID."
                )
            if invalidate_drafts:
                stale = [
                    row[0]
                    for row in c.execute(
                        "SELECT id FROM drafts WHERE conversation_id=? AND case_version<?",
                        (cid, memory.version),
                    )
                ]
                memory.stale_draft_ids = list(dict.fromkeys(memory.stale_draft_ids + stale))
                c.execute(
                    "UPDATE drafts SET status='stale', updated_at=? WHERE conversation_id=? AND case_version<?",
                    (now(), cid, memory.version),
                )
            if audit:
                c.execute(
                    "INSERT OR IGNORE INTO case_update_audit VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        cid,
                        audit["message_id"],
                        existing["version"],
                        memory.version,
                        json.dumps(audit["task_ids"]),
                        audit["decision"],
                        now(),
                    ),
                )
            if staged_proposal:
                c.execute(
                    "INSERT OR IGNORE INTO staged_case_updates VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        cid,
                        staged_proposal["message_id"],
                        existing["version"],
                        json.dumps(staged_proposal["task_ids"]),
                        json.dumps(staged_proposal["memory"], ensure_ascii=False),
                        "requires_review",
                        now(),
                    ),
                )
            for event in memory.journey.events:
                c.execute(
                    "INSERT OR IGNORE INTO complaint_events VALUES (?, ?, ?, ?)",
                    (cid, event.id, event.model_dump_json(), event.recorded_at),
                )
            for recommendation in memory.journey.recommendations:
                c.execute(
                    "INSERT OR IGNORE INTO resolution_recommendations VALUES (?, ?, ?, ?, ?)",
                    (
                        cid,
                        recommendation.id,
                        recommendation.case_version,
                        recommendation.model_dump_json(),
                        recommendation.assessed_at,
                    ),
                )
            if graph_state is None:
                c.execute(
                    "UPDATE case_memory SET version=?, memory_json=?, summary=?, updated_at=? WHERE conversation_id=?",
                    (memory.version, memory.model_dump_json(), summary, now(), cid),
                )
            else:
                c.execute(
                    "UPDATE case_memory SET version=?, memory_json=?, summary=?, graph_state_json=?, updated_at=? WHERE conversation_id=?",
                    (
                        memory.version,
                        memory.model_dump_json(),
                        summary,
                        json.dumps(graph_state, default=str),
                        now(),
                        cid,
                    ),
                )

    def case_proposals(self, owner_id, cid):
        self.get_conversation(owner_id, cid)
        with self.connect() as conn:
            return [
                {
                    "message_id": row["message_id"],
                    "base_version": row["base_version"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "proposed_facts": json.loads(row["proposed_memory_json"]).get("facts", {}),
                }
                for row in conn.execute(
                    "SELECT * FROM staged_case_updates WHERE conversation_id=? ORDER BY created_at DESC LIMIT 10",
                    (cid,),
                )
            ]

    def staged_patches(self, owner_id, cid):
        self.get_conversation(owner_id, cid)
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload_json FROM case_patch_audit WHERE conversation_id=? AND decision='staged' ORDER BY rowid DESC LIMIT 24",
                    (cid,),
                )
            ]

    def add_attachment(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "id",
            "conversation_id",
            "filename",
            "stored_path",
            "mime_type",
            "size",
            "extraction_status",
            "extracted_text",
            "metadata_json",
            "created_at",
        )
        with self.connect() as c:
            c.execute(
                f"INSERT INTO attachments ({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
                tuple(data[x] for x in fields),
            )
        return data

    def attachments(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute("SELECT * FROM attachments WHERE conversation_id=?", (cid,)).fetchall()
        return [dict(r) for r in rows]

    def update_attachment_text(
        self, owner_id: str, cid: str, attachment_id: str, text: str
    ) -> None:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            original = c.execute(
                "SELECT extracted_text, metadata_json FROM attachments WHERE id=? AND conversation_id=?",
                (attachment_id, cid),
            ).fetchone()
            if not original:
                raise KeyError("attachment_not_found")
            metadata = json.loads(original["metadata_json"])
            metadata.setdefault("original_extracted_text", original["extracted_text"])
            metadata.setdefault("original_pages", metadata.get("pages", []))
            metadata.setdefault("corrections", []).append(
                {"previous_text": original["extracted_text"], "corrected_at": now()}
            )
            metadata["pages"] = [
                {
                    "page": 1,
                    "start": 0,
                    "end": len(text),
                    "method": "user_corrected",
                    "locator_note": "User correction; original PDF page mapping not asserted",
                }
            ]
            result = c.execute(
                "UPDATE attachments SET extracted_text=?, extraction_status='user_corrected', metadata_json=? WHERE id=? AND conversation_id=?",
                (text, json.dumps(metadata), attachment_id, cid),
            )
            if result.rowcount != 1:
                raise KeyError("attachment_not_found")

    def create_draft(
        self, owner_id: str, cid: str, title: str, content: str, case_version: int, _connection=None
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        draft_id, timestamp = str(uuid.uuid4()), now()
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            c.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, ?, 1, 'working', ?, ?, ?)",
                (draft_id, cid, title, content, case_version, timestamp, timestamp),
            )
            row = c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(row)

    def drafts(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM drafts WHERE conversation_id=? ORDER BY updated_at DESC", (cid,)
                )
            ]

    def update_draft(
        self,
        owner_id: str,
        cid: str,
        draft_id: str,
        content: str,
        case_version: int,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            current = c.execute(
                "SELECT * FROM drafts WHERE id=? AND conversation_id=?", (draft_id, cid)
            ).fetchone()
            if not current:
                raise KeyError("draft_not_found")
            if expected_version is not None and current["version"] != expected_version:
                raise MemoryConflict("Draft changed; reload before overwriting another edit.")
            c.execute(
                "UPDATE drafts SET content=?, version=version+1, status='working', case_version=?, updated_at=? WHERE id=?",
                (content, case_version, now(), draft_id),
            )
            row = c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(row)

    def mark_drafts_stale(self, cid: str, case_version: int) -> list[str]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT id FROM drafts WHERE conversation_id=? AND case_version<? AND status!='stale'",
                (cid, case_version),
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                c.execute(
                    "UPDATE drafts SET status='stale', updated_at=? WHERE conversation_id=? AND case_version<?",
                    (now(), cid, case_version),
                )
        return ids

    def get_message(self, owner_id: str, cid: str, message_id: str) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM messages WHERE id=? AND conversation_id=?", (message_id, cid)
            ).fetchone()
        if not row:
            raise KeyError("message_not_found")
        return self._message(dict(row))
