"""Private evidence search. Callers supply only authorised case attachments."""

import hashlib
import json
import re


class EvidenceSearchService:
    def chunks(self, document):
        text = document.get("extracted_text", "")
        metadata = document.get("metadata", {})
        if not metadata:
            metadata = json.loads(document.get("metadata_json") or "{}")
        pages = metadata.get("pages") or [{"page": 1, "start": 0, "end": len(text)}]
        for page in pages:
            for start in range(page["start"], page["end"], 1100):
                end = min(start + 1400, page["end"])
                excerpt = text[start:end]
                yield {
                    "id": document["id"],
                    "filename": document["filename"],
                    "chunk_id": hashlib.sha256(
                        f"{document['id']}:{start}:{excerpt}".encode()
                    ).hexdigest()[:24],
                    "page": page["page"],
                    "extraction_method": page.get("method", "unknown"),
                    "locator_note": page.get("locator_note"),
                    "span": {"start": start, "end": end},
                    "text": excerpt,
                    "status": document.get("extraction_status"),
                    "trust": "documentary statement, not independent proof",
                }

    def search(self, query, documents, limit=6):
        terms = set(re.findall(r"[\w\u0900-\u097f]+", query.casefold()))
        chunks = [chunk for document in documents for chunk in self.chunks(document)]
        chunks.sort(
            key=lambda c: sum(1 for t in terms if len(t) > 2 and t in c["text"].casefold()),
            reverse=True,
        )
        selected = chunks[:limit]
        for document in documents:
            if not document.get("extracted_text", "").strip():
                selected.append(
                    {
                        "id": document["id"],
                        "filename": document["filename"],
                        "text": "",
                        "status": document.get("extraction_status", "unreadable"),
                    }
                )
        return selected
