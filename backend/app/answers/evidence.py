"""A turn-local canonical evidence registry. Never mixes owners or invents support."""

import hashlib
import re

from app.routing.segments import segment_message

# In-text numbered citations: "[1](#cite-1)" links to entry 1 of the message's sources list.
CITATION_MARKER_RE = re.compile(r"[ \t]*\[\d{1,3}\]\(#cite-\d{1,3}\)")
LEGACY_CITATION_RE = re.compile(r"\[Source:[^\]]*\]")


def citation_marker(number: int) -> str:
    return f"[{number}](#cite-{number})"


def strip_citation_markers(text: str) -> str:
    """Remove numbered and legacy citation markers, e.g. before reusing an answer as model context."""
    return LEGACY_CITATION_RE.sub("", CITATION_MARKER_RE.sub("", text or "")).strip()


class EvidenceRegistry:
    def __init__(self, state, *, include_recent_user_turns: bool = False):
        self.entries = {}
        for passage in state.get("passages", []):
            identifier = passage["passage_id"]
            entry = {**passage, "evidence_id": identifier, "kind": "public_passage"}
            entry["text_hash"] = hashlib.sha256(entry["text"].encode()).hexdigest()
            entry["corpus_version"] = state.get("corpus_version")
            self.entries[identifier] = entry
        message_id = state.get("message_id", "current")
        self.entries[f"message:{message_id}"] = {
            "evidence_id": f"message:{message_id}",
            "kind": "user_report",
            "text": state["current_message"],
            "source_id": message_id,
            "case_version": state.get("memory", {}).get("version", 0),
        }
        if include_recent_user_turns:
            for turn in state.get("context", {}).get("recent_turns", []):
                tid = turn.get("id")
                if turn.get("role") == "user" and tid and tid != message_id:
                    self.entries.setdefault(
                        f"message:{tid}",
                        {
                            "evidence_id": f"message:{tid}",
                            "kind": "prior_user_message",
                            "text": turn.get("content", ""),
                            "source_id": tid,
                            "case_version": state.get("memory", {}).get("version", 0),
                        },
                    )
        for segment in segment_message(state["current_message"]):
            key = f"segment:{segment['id']}"
            self.entries[key] = {
                "evidence_id": key,
                "kind": "message_segment",
                "text": segment["text"],
                "source_id": message_id,
                "span": f"{segment['start']}:{segment['end']}",
            }
        for key, fact in state.get("memory", {}).get("facts", {}).items():
            self.entries[f"fact:{key}"] = {
                "evidence_id": f"fact:{key}",
                "kind": "case_fact",
                "text": fact["value"],
                "status": fact.get("status"),
                "provenance": fact.get("provenance", []),
                "case_version": state["memory"].get("version", 0),
            }
        for excerpt in state.get("context", {}).get("relevant_evidence", []):
            identifier = (
                f"document:{excerpt['id']}:{excerpt.get('page', 'span')}:{excerpt.get('start', 0)}"
            )
            self.entries[identifier] = {
                **excerpt,
                "evidence_id": identifier,
                "kind": "document_statement",
            }

    def public_ids(self):
        return {key for key, entry in self.entries.items() if entry["kind"] == "public_passage"}

    def citations(self, identifiers):
        # Display identity comes only from the registry, never from model wording.
        return " ".join(
            dict.fromkeys(
                f"[Source: {entry['title']} — {entry['locator']}]"
                for identifier in identifiers
                if (entry := self.entries.get(identifier)) and entry["kind"] == "public_passage"
            )
        )

    @staticmethod
    def strip_generated_citations(text):
        return re.sub(r"\[Source:[^\]]*\]", "", text).strip()

    def payload(self):
        return list(self.entries.values())
