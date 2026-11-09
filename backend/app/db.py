import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.models import CaseMemory
from app.security.privacy import EnvelopeCipher

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
CREATE TABLE IF NOT EXISTS case_encryption_keys (
  conversation_id TEXT PRIMARY KEY,
  wrapped_dek TEXT NOT NULL,
  key_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  destroyed_at TEXT
);
CREATE TABLE IF NOT EXISTS physical_purge_queue (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  key_destroyed_at TEXT NOT NULL,
  scheduled_purge_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled'
);
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
CREATE TABLE IF NOT EXISTS attachment_consents (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  attachment_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'consented',
  updated_at TEXT NOT NULL,
  PRIMARY KEY(conversation_id, attachment_id)
);
CREATE TABLE IF NOT EXISTS quality_review_consents (
  conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
  opted_in INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_action_tracker (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  notes TEXT NOT NULL DEFAULT '',
  occurred_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submission_audit_steps (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  draft_id TEXT,
  target_channel TEXT NOT NULL,
  step TEXT NOT NULL,
  receipt_reference TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS security_audit_log (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  owner_id TEXT,
  conversation_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
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
CREATE TABLE IF NOT EXISTS practice_sessions (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  scenario_id TEXT NOT NULL,
  title TEXT NOT NULL,
  domain TEXT NOT NULL,
  opponent_role TEXT NOT NULL,
  setting TEXT NOT NULL,
  objective TEXT NOT NULL,
  opening_statement TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_practice_sessions_conv ON practice_sessions(conversation_id, created_at DESC);
CREATE TABLE IF NOT EXISTS practice_turns (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
  turn_index INTEGER NOT NULL,
  user_argument TEXT NOT NULL,
  opponent_reply TEXT NOT NULL,
  coach_feedback_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_practice_turns_session ON practice_turns(session_id, turn_index ASC);
-- A user's own OpenAI key, sealed with a secret only their browser holds; never readable here.
CREATE TABLE IF NOT EXISTS owner_api_keys (
  owner_id TEXT PRIMARY KEY REFERENCES owners(id) ON DELETE CASCADE,
  sealed_key TEXT NOT NULL, key_hint TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


class MemoryConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path, cipher: EnvelopeCipher | None = None, *, encrypt: bool | None = None):
        self.path = path
        self._local = threading.local()
        cfg = get_settings()
        self.encrypt_enabled = cfg.envelope_encryption_enabled if encrypt is None else encrypt
        self.cipher = cipher or EnvelopeCipher(cfg.kms_master_key, cfg.kms_key_id)
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

    def _ensure_wrapped_dek(self, cid: str, _connection=None) -> str:
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            row = c.execute(
                "SELECT wrapped_dek, status FROM case_encryption_keys WHERE conversation_id=?",
                (cid,),
            ).fetchone()
            if row:
                if row["status"] == "destroyed":
                    return ""
                return row["wrapped_dek"]
            wrapped = self.cipher.generate_wrapped_dek(cid)
            c.execute(
                "INSERT INTO case_encryption_keys VALUES (?, ?, ?, 'active', ?, NULL)",
                (cid, wrapped, self.cipher.key_id, now()),
            )
            return wrapped

    def _get_wrapped_dek(self, cid: str, _connection=None) -> str | None:
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            row = c.execute(
                "SELECT wrapped_dek, status FROM case_encryption_keys WHERE conversation_id=?",
                (cid,),
            ).fetchone()
        if not row:
            return None
        return "" if row["status"] == "destroyed" else row["wrapped_dek"]

    def encrypt_case_field(self, cid: str, text: str, _connection=None) -> str:
        if not self.encrypt_enabled or not text:
            return text
        wrapped = self._ensure_wrapped_dek(cid, _connection=_connection)
        return self.cipher.encrypt_text(cid, wrapped, text)

    def decrypt_case_field(self, cid: str, value: str | None, _connection=None) -> str:
        if value is None:
            return ""
        if not value or not value.startswith("enc:v1:"):
            return value
        wrapped = self._get_wrapped_dek(cid, _connection=_connection)
        return self.cipher.decrypt_text(cid, wrapped, value)

    def encrypt_case_bytes(self, cid: str, data: bytes) -> bytes:
        if not self.encrypt_enabled:
            return data
        wrapped = self._ensure_wrapped_dek(cid)
        return self.cipher.encrypt_bytes(cid, wrapped, data)

    def decrypt_case_bytes(self, cid: str, data: bytes) -> bytes:
        if not data.startswith(b"enc:v1:"):
            return data
        wrapped = self._get_wrapped_dek(cid)
        return self.cipher.decrypt_bytes(cid, wrapped, data)

    def case_key_metadata(self, owner_id: str, cid: str) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            row = c.execute(
                "SELECT key_id, status, created_at, destroyed_at FROM case_encryption_keys WHERE conversation_id=?",
                (cid,),
            ).fetchone()
        if not row:
            return {"envelope_encrypted": False, "status": "uninitialized"}
        return {
            "envelope_encrypted": row["status"] == "active",
            "key_id": row["key_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "destroyed_at": row["destroyed_at"],
        }

    def record_security_audit(
        self,
        event_type: str,
        *,
        owner_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record security event metadata without ever storing user prompts or document text."""
        safe_meta = {
            k: v
            for k, v in (metadata or {}).items()
            if k not in {"content", "current_message", "extracted_text", "text", "prompt"}
        }
        with self.connect() as c:
            c.execute(
                "INSERT INTO security_audit_log VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), event_type, owner_id, conversation_id, json.dumps(safe_meta), now()),
            )

    def security_audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM security_audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "owner_id": r["owner_id"],
                "conversation_id": r["conversation_id"],
                "metadata": json.loads(r["metadata_json"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

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

    def create_owner(self, token_hash: str) -> str:
        owner_id = str(uuid.uuid4())
        with self.connect() as c:
            c.execute("INSERT INTO owners VALUES (?, ?, ?)", (owner_id, token_hash, now()))
        return owner_id

    def rotate_owner_token(self, owner_id: str, new_token_hash: str) -> None:
        with self.connect() as c:
            updated = c.execute(
                "UPDATE owners SET token_hash=? WHERE id=?", (new_token_hash, owner_id)
            )
            if updated.rowcount != 1:
                raise KeyError("owner_not_found")
        self.record_security_audit("device_credential_rotated", owner_id=owner_id)

    def owner_for_hash(self, token_hash: str) -> str | None:
        with self.connect() as c:
            row = c.execute("SELECT id FROM owners WHERE token_hash=?", (token_hash,)).fetchone()
        return row["id"] if row else None

    def sealed_api_key(self, owner_id: str) -> dict[str, str] | None:
        with self.connect() as c:
            row = c.execute(
                "SELECT sealed_key, key_hint FROM owner_api_keys WHERE owner_id=?", (owner_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_sealed_api_key(self, owner_id: str, sealed_key: str, key_hint: str) -> None:
        stamp = now()
        with self.connect() as c:
            c.execute(
                "INSERT INTO owner_api_keys VALUES (?, ?, ?, ?, ?) ON CONFLICT(owner_id) DO UPDATE "
                "SET sealed_key=excluded.sealed_key, key_hint=excluded.key_hint, updated_at=excluded.updated_at",
                (owner_id, sealed_key, key_hint, stamp, stamp),
            )
        self.record_security_audit("user_api_key_saved", owner_id=owner_id)

    def delete_sealed_api_key(self, owner_id: str) -> bool:
        with self.connect() as c:
            removed = c.execute("DELETE FROM owner_api_keys WHERE owner_id=?", (owner_id,)).rowcount
        if removed:
            self.record_security_audit("user_api_key_deleted", owner_id=owner_id)
        return bool(removed)

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
            self._ensure_wrapped_dek(cid, _connection=c)
            enc_mem = self.encrypt_case_field(cid, json.dumps(memory), _connection=c)
            c.execute(
                "INSERT INTO case_memory VALUES (?, 0, ?, '', '{}', ?)",
                (cid, enc_mem, timestamp),
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
            rows = [dict(x) for x in c.execute(sql, (owner_id,)).fetchall()]
            for r in rows:
                if r.get("last_message"):
                    r["last_message"] = self.decrypt_case_field(
                        r["id"], r["last_message"], _connection=c
                    )
            return rows

    def rename_conversation(self, owner_id: str, cid: str, title: str) -> None:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            c.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=?", (title, now(), cid)
            )

    def delete_conversation(self, owner_id: str, cid: str) -> list[str]:
        self.get_conversation(owner_id, cid)
        destroyed_at = now()
        purge_at = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        with self.connect() as c:
            files = [
                r[0]
                for r in c.execute(
                    "SELECT stored_path FROM attachments WHERE conversation_id=?", (cid,)
                )
            ]
            # Cryptographically destroy the per-case DEK and schedule physical purge verification.
            c.execute(
                "INSERT INTO case_encryption_keys VALUES (?, '', ?, 'destroyed', ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET wrapped_dek='', status='destroyed', destroyed_at=excluded.destroyed_at",
                (cid, self.cipher.key_id, destroyed_at, destroyed_at),
            )
            c.execute(
                "INSERT INTO physical_purge_queue VALUES (?, ?, ?, ?, ?, 'scheduled')",
                (str(uuid.uuid4()), cid, owner_id, destroyed_at, purge_at),
            )
            c.execute("DELETE FROM conversations WHERE id=? AND owner_id=?", (cid, owner_id))
        self.record_security_audit(
            "case_deleted_and_dek_destroyed", owner_id=owner_id, conversation_id=cid
        )
        return files

    def purge_queue_entries(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM physical_purge_queue WHERE owner_id=? ORDER BY key_destroyed_at DESC",
                (owner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

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
            stored_content = self.encrypt_case_field(cid, content, _connection=c)
            try:
                c.execute(
                    "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mid,
                        cid,
                        request_id,
                        role,
                        stored_content,
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
                return self._decode_message(dict(row), _connection=c)
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, cid))
            row = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
            return self._decode_message(dict(row), _connection=c)

    def _decode_message(self, row: dict[str, Any], _connection=None) -> dict[str, Any]:
        row["content"] = self.decrypt_case_field(
            row["conversation_id"], row.get("content", ""), _connection=_connection
        )
        row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
        return row

    def messages(self, owner_id: str, cid: str, limit: int = 500) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT ?",
                (cid, limit),
            ).fetchall()
            return [self._decode_message(dict(r), _connection=c) for r in rows]

    def find_turn(self, cid: str, request_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=? AND request_id=? ORDER BY created_at",
                (cid, request_id),
            ).fetchall()
            mapped = [self._decode_message(dict(r), _connection=c) for r in rows]
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
            mem_raw = self.decrypt_case_field(cid, row["memory_json"], _connection=c)
            sum_raw = self.decrypt_case_field(cid, row["summary"], _connection=c)
        return CaseMemory.model_validate_json(mem_raw), sum_raw

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
                enc_prop = self.encrypt_case_field(
                    cid, json.dumps(staged_proposal["memory"], ensure_ascii=False), _connection=c
                )
                c.execute(
                    "INSERT OR IGNORE INTO staged_case_updates VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        cid,
                        staged_proposal["message_id"],
                        existing["version"],
                        json.dumps(staged_proposal["task_ids"]),
                        enc_prop,
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
            enc_mem = self.encrypt_case_field(cid, memory.model_dump_json(), _connection=c)
            enc_sum = self.encrypt_case_field(cid, summary, _connection=c)
            if graph_state is None:
                c.execute(
                    "UPDATE case_memory SET version=?, memory_json=?, summary=?, updated_at=? WHERE conversation_id=?",
                    (memory.version, enc_mem, enc_sum, now(), cid),
                )
            else:
                enc_gs = self.encrypt_case_field(
                    cid, json.dumps(graph_state, default=str), _connection=c
                )
                c.execute(
                    "UPDATE case_memory SET version=?, memory_json=?, summary=?, graph_state_json=?, updated_at=? WHERE conversation_id=?",
                    (
                        memory.version,
                        enc_mem,
                        enc_sum,
                        enc_gs,
                        now(),
                        cid,
                    ),
                )

    def case_proposals(self, owner_id, cid):
        self.get_conversation(owner_id, cid)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM staged_case_updates WHERE conversation_id=? ORDER BY created_at DESC LIMIT 10",
                (cid,),
            ).fetchall()
            out = []
            for row in rows:
                dec = self.decrypt_case_field(cid, row["proposed_memory_json"], _connection=conn)
                out.append(
                    {
                        "message_id": row["message_id"],
                        "base_version": row["base_version"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "proposed_facts": json.loads(dec).get("facts", {}),
                    }
                )
            return out

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

    def add_attachment(self, data: dict[str, Any], *, consent_status: str = "consented") -> dict[str, Any]:
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
        cid = data["conversation_id"]
        with self.connect() as c:
            row_values = dict(data)
            row_values["extracted_text"] = self.encrypt_case_field(
                cid, data.get("extracted_text", ""), _connection=c
            )
            c.execute(
                f"INSERT INTO attachments ({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
                tuple(row_values[x] for x in fields),
            )
            c.execute(
                "INSERT OR REPLACE INTO attachment_consents VALUES (?, ?, ?, ?)",
                (cid, data["id"], consent_status, now()),
            )
        return {**data, "consent_status": consent_status}

    def set_attachment_consent(
        self, owner_id: str, cid: str, attachment_id: str, status: str
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        if status not in {"consented", "withheld"}:
            raise ValueError("Invalid attachment consent status")
        with self.connect() as c:
            exists = c.execute(
                "SELECT 1 FROM attachments WHERE id=? AND conversation_id=?", (attachment_id, cid)
            ).fetchone()
            if not exists:
                raise KeyError("attachment_not_found")
            ts = now()
            c.execute(
                "INSERT OR REPLACE INTO attachment_consents VALUES (?, ?, ?, ?)",
                (cid, attachment_id, status, ts),
            )
        self.record_security_audit(
            "attachment_consent_updated",
            owner_id=owner_id,
            conversation_id=cid,
            metadata={"attachment_id": attachment_id, "consent_status": status},
        )
        return {"attachment_id": attachment_id, "consent_status": status, "updated_at": ts}

    def attachments(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                """SELECT a.*, COALESCE(ac.status, 'consented') AS consent_status
                   FROM attachments a
                   LEFT JOIN attachment_consents ac
                     ON ac.conversation_id=a.conversation_id AND ac.attachment_id=a.id
                   WHERE a.conversation_id=?""",
                (cid,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["extracted_text"] = self.decrypt_case_field(
                    cid, d.get("extracted_text", ""), _connection=c
                )
                out.append(d)
            return out

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
            orig_text = self.decrypt_case_field(cid, original["extracted_text"], _connection=c)
            metadata = json.loads(original["metadata_json"])
            metadata.setdefault("original_extracted_text", orig_text)
            metadata.setdefault("original_pages", metadata.get("pages", []))
            metadata.setdefault("corrections", []).append(
                {"previous_text": orig_text, "corrected_at": now()}
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
            enc_text = self.encrypt_case_field(cid, text, _connection=c)
            result = c.execute(
                "UPDATE attachments SET extracted_text=?, extraction_status='user_corrected', metadata_json=? WHERE id=? AND conversation_id=?",
                (enc_text, json.dumps(metadata), attachment_id, cid),
            )
            if result.rowcount != 1:
                raise KeyError("attachment_not_found")

    def create_draft(
        self, owner_id: str, cid: str, title: str, content: str, case_version: int, _connection=None
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        draft_id, timestamp = str(uuid.uuid4()), now()
        with nullcontext(_connection) if _connection is not None else self.connect() as c:
            enc_content = self.encrypt_case_field(cid, content, _connection=c)
            c.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, ?, 1, 'working', ?, ?, ?)",
                (draft_id, cid, title, enc_content, case_version, timestamp, timestamp),
            )
            row = dict(c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone())
            row["content"] = self.decrypt_case_field(cid, row["content"], _connection=c)
            return row

    def drafts(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM drafts WHERE conversation_id=? ORDER BY updated_at DESC", (cid,)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["content"] = self.decrypt_case_field(cid, d["content"], _connection=c)
                out.append(d)
            return out

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
            enc_content = self.encrypt_case_field(cid, content, _connection=c)
            c.execute(
                "UPDATE drafts SET content=?, version=version+1, status='working', case_version=?, updated_at=? WHERE id=?",
                (enc_content, case_version, now(), draft_id),
            )
            row = dict(c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone())
            row["content"] = self.decrypt_case_field(cid, row["content"], _connection=c)
            return row

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
            return self._decode_message(dict(row), _connection=c)

    # --- Active Resolution Workspace: Actions, Submission Steps, Quality Consent & Transfer ---

    def add_user_action(
        self,
        owner_id: str,
        cid: str,
        title: str,
        status: str = "completed",
        notes: str = "",
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        aid, ts = str(uuid.uuid4()), now()
        enc_notes = self.encrypt_case_field(cid, notes)
        with self.connect() as c:
            c.execute(
                "INSERT INTO user_action_tracker VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (aid, cid, title, status, enc_notes, occurred_at or ts, ts, ts),
            )
        return {
            "id": aid,
            "conversation_id": cid,
            "title": title,
            "status": status,
            "notes": notes,
            "occurred_at": occurred_at or ts,
            "created_at": ts,
            "updated_at": ts,
        }

    def update_user_action(
        self, owner_id: str, cid: str, action_id: str, status: str, notes: str | None = None
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        ts = now()
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM user_action_tracker WHERE id=? AND conversation_id=?",
                (action_id, cid),
            ).fetchone()
            if not row:
                raise KeyError("action_not_found")
            dec_notes = (
                notes
                if notes is not None
                else self.decrypt_case_field(cid, row["notes"], _connection=c)
            )
            enc_notes = self.encrypt_case_field(cid, dec_notes, _connection=c)
            c.execute(
                "UPDATE user_action_tracker SET status=?, notes=?, updated_at=? WHERE id=?",
                (status, enc_notes, ts, action_id),
            )
            updated = dict(
                c.execute("SELECT * FROM user_action_tracker WHERE id=?", (action_id,)).fetchone()
            )
            updated["notes"] = dec_notes
            return updated

    def list_user_actions(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM user_action_tracker WHERE conversation_id=? ORDER BY created_at DESC",
                (cid,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["notes"] = self.decrypt_case_field(cid, d.get("notes", ""), _connection=c)
                out.append(d)
            return out

    def record_submission_step(
        self,
        owner_id: str,
        cid: str,
        *,
        target_channel: str,
        step: str,
        draft_id: str | None = None,
        receipt_reference: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Record one of the 4 user-confirmed submission steps: previewed, consented, submitted_by_user, receipt_captured."""
        self.get_conversation(owner_id, cid)
        valid_steps = {"previewed", "consented", "submitted_by_user", "receipt_captured"}
        if step not in valid_steps:
            raise ValueError("Invalid submission step")
        sid, ts = str(uuid.uuid4()), now()
        enc_notes = self.encrypt_case_field(cid, notes)
        with self.connect() as c:
            c.execute(
                "INSERT INTO submission_audit_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, cid, draft_id, target_channel, step, receipt_reference, enc_notes, ts),
            )
        self.record_security_audit(
            "submission_step_recorded",
            owner_id=owner_id,
            conversation_id=cid,
            metadata={"step": step, "target_channel": target_channel},
        )
        return {
            "id": sid,
            "conversation_id": cid,
            "draft_id": draft_id,
            "target_channel": target_channel,
            "step": step,
            "receipt_reference": receipt_reference,
            "notes": notes,
            "created_at": ts,
        }

    def list_submission_steps(self, owner_id: str, cid: str) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM submission_audit_steps WHERE conversation_id=? ORDER BY created_at ASC",
                (cid,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["notes"] = self.decrypt_case_field(cid, d.get("notes", ""), _connection=c)
                out.append(d)
            return out

    def set_quality_review_consent(self, owner_id: str, cid: str, opted_in: bool) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        ts = now()
        with self.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO quality_review_consents VALUES (?, ?, ?)",
                (cid, 1 if opted_in else 0, ts),
            )
        self.record_security_audit(
            "quality_review_consent_changed",
            owner_id=owner_id,
            conversation_id=cid,
            metadata={"opted_in": opted_in},
        )
        return {"opted_in": opted_in, "updated_at": ts}

    def get_quality_review_consent(self, owner_id: str, cid: str) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            row = c.execute(
                "SELECT opted_in, updated_at FROM quality_review_consents WHERE conversation_id=?",
                (cid,),
            ).fetchone()
        if not row:
            return {"opted_in": False, "updated_at": None}
        return {"opted_in": bool(row["opted_in"]), "updated_at": row["updated_at"]}

    def restore_transferred_case(self, owner_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Import a decrypted guest case-transfer snapshot under a fresh conversation ID and DEK."""
        conv_src = snapshot.get("conversation") or {}
        language = conv_src.get("language") or "en"
        created = self.create_conversation(owner_id, language)
        cid = created["id"]
        title = (conv_src.get("title") or "Transferred case")[:80]
        self.rename_conversation(owner_id, cid, title)
        memory = CaseMemory.model_validate(snapshot.get("case_memory") or {})
        summary = str(snapshot.get("summary") or "")
        self.save_memory(cid, memory, summary, owner_id=owner_id)
        for msg in snapshot.get("messages") or []:
            self.add_message(
                cid,
                msg.get("role", "user"),
                msg.get("content", ""),
                None,
                msg.get("status", "complete"),
                msg.get("metadata") or {},
            )
        for draft in snapshot.get("drafts") or []:
            self.create_draft(
                owner_id,
                cid,
                draft.get("title", "Draft"),
                draft.get("content", ""),
                memory.version,
            )
        for act in snapshot.get("user_actions") or []:
            self.add_user_action(
                owner_id,
                cid,
                act.get("title", "Action"),
                act.get("status", "completed"),
                act.get("notes", ""),
                act.get("occurred_at"),
            )
        self.record_security_audit(
            "encrypted_case_transfer_imported", owner_id=owner_id, conversation_id=cid
        )
        return self.get_conversation(owner_id, cid)

    def create_practice_session(
        self,
        owner_id: str,
        cid: str,
        scenario_id: str,
        title: str,
        domain: str,
        opponent_role: str,
        setting: str,
        objective: str,
        opening_statement: str,
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        sid, ts = str(uuid.uuid4()), now()
        with self.connect() as c:
            # Objective and opening can carry the user's case summary: encrypt like turns.
            c.execute(
                "INSERT INTO practice_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                (
                    sid,
                    cid,
                    scenario_id,
                    title,
                    domain,
                    opponent_role,
                    setting,
                    self.encrypt_case_field(cid, objective, _connection=c),
                    self.encrypt_case_field(cid, opening_statement, _connection=c),
                    ts,
                    ts,
                ),
            )
        return {
            "id": sid,
            "conversation_id": cid,
            "scenario_id": scenario_id,
            "title": title,
            "domain": domain,
            "opponent_role": opponent_role,
            "setting": setting,
            "objective": objective,
            "opening_statement": opening_statement,
            "status": "active",
            "created_at": ts,
            "updated_at": ts,
            "turns": [],
        }

    def get_practice_session(
        self, owner_id: str, cid: str, session_id: str
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM practice_sessions WHERE id=? AND conversation_id=?",
                (session_id, cid),
            ).fetchone()
            if not row:
                raise KeyError("practice_session_not_found")
            res = self._practice_session_row(cid, row, c)
            turns_rows = c.execute(
                "SELECT * FROM practice_turns WHERE session_id=? ORDER BY turn_index ASC",
                (session_id,),
            ).fetchall()
            turns = []
            for tr in turns_rows:
                td = dict(tr)
                td["user_argument"] = self.decrypt_case_field(cid, td["user_argument"], _connection=c)
                td["opponent_reply"] = self.decrypt_case_field(cid, td["opponent_reply"], _connection=c)
                td["coach_feedback"] = json.loads(td.get("coach_feedback_json") or "{}")
                turns.append(td)
            res["turns"] = turns
            return res

    def _practice_session_row(self, cid: str, row, connection) -> dict[str, Any]:
        session = dict(row)
        for key in ("objective", "opening_statement"):
            session[key] = self.decrypt_case_field(cid, session[key], _connection=connection)
        return session

    def list_practice_sessions(
        self, owner_id: str, cid: str
    ) -> list[dict[str, Any]]:
        self.get_conversation(owner_id, cid)
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM practice_sessions WHERE conversation_id=? ORDER BY created_at DESC",
                (cid,),
            ).fetchall()
            out = []
            for r in rows:
                sd = self._practice_session_row(cid, r, c)
                count = c.execute(
                    "SELECT COUNT(*) as cnt FROM practice_turns WHERE session_id=?",
                    (sd["id"],),
                ).fetchone()["cnt"]
                sd["turn_count"] = count
                out.append(sd)
            return out

    def add_practice_turn(
        self,
        owner_id: str,
        cid: str,
        session_id: str,
        user_argument: str,
        opponent_reply: str,
        coach_feedback: dict[str, Any],
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        tid, ts = str(uuid.uuid4()), now()
        with self.connect() as c:
            session = c.execute(
                "SELECT id FROM practice_sessions WHERE id=? AND conversation_id=?",
                (session_id, cid),
            ).fetchone()
            if not session:
                raise KeyError("practice_session_not_found")
            idx = c.execute(
                "SELECT COALESCE(MAX(turn_index), 0) + 1 as next_idx FROM practice_turns WHERE session_id=?",
                (session_id,),
            ).fetchone()["next_idx"]
            enc_user = self.encrypt_case_field(cid, user_argument, _connection=c)
            enc_opponent = self.encrypt_case_field(cid, opponent_reply, _connection=c)
            c.execute(
                "INSERT INTO practice_turns VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tid, session_id, idx, enc_user, enc_opponent, json.dumps(coach_feedback), ts),
            )
            c.execute(
                "UPDATE practice_sessions SET updated_at=? WHERE id=?",
                (ts, session_id),
            )
        return {
            "id": tid,
            "session_id": session_id,
            "turn_index": idx,
            "user_argument": user_argument,
            "opponent_reply": opponent_reply,
            "coach_feedback": coach_feedback,
            "created_at": ts,
        }

    def update_practice_session_status(
        self, owner_id: str, cid: str, session_id: str, status: str
    ) -> dict[str, Any]:
        self.get_conversation(owner_id, cid)
        ts = now()
        with self.connect() as c:
            c.execute(
                "UPDATE practice_sessions SET status=?, updated_at=? WHERE id=? AND conversation_id=?",
                (status, ts, session_id, cid),
            )
        return self.get_practice_session(owner_id, cid, session_id)

