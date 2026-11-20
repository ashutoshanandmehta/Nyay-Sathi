#!/usr/bin/env python3
"""Rebuild the versioned legal corpus with one pinned OpenAI embedding configuration.

The script never prints the API key or passage text. It writes all generated artifacts only
after every response has passed model, index, dimension, finiteness, and norm validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "legal_corpus" / "v1"
MODEL = "text-embedding-3-small"
DIMENSIONS = 384
VERSION = "openai:text-embedding-3-small:dimensions=384:v1"
MAX_REQUESTS = 8
MAX_INPUT_CHARS = 600_000


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def embed(inputs: list[str], key: str, request_counter: list[int]) -> tuple[list[list[float]], int]:
    request_counter[0] += 1
    if request_counter[0] > MAX_REQUESTS:
        raise RuntimeError("embedding request cap exceeded")
    payload = json.dumps({
        "input": inputs, "model": MODEL, "dimensions": DIMENSIONS, "encoding_format": "float",
    }).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings", data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"embedding API failed with HTTP {exc.code}") from exc
    if body.get("model") != MODEL or len(body.get("data", [])) != len(inputs):
        raise RuntimeError("embedding response model or count mismatch")
    vectors: list[list[float]] = []
    for expected_index, item in enumerate(sorted(body["data"], key=lambda row: row.get("index", -1))):
        vector = item.get("embedding")
        if item.get("index") != expected_index or not isinstance(vector, list) or len(vector) != DIMENSIONS:
            raise RuntimeError("embedding response index or dimension mismatch")
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
            raise RuntimeError("embedding response contains a non-finite value")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if norm < 0.99 or norm > 1.01:
            raise RuntimeError("embedding response is not normalized")
        vectors.append([round(float(value) / norm, 8) for value in vector])
    return vectors, int(body.get("usage", {}).get("total_tokens", 0))


def sql_str(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_text_array(values: list[str]) -> str:
    return "array[" + ", ".join(sql_str(value) for value in values) + "]::text[]"


def sql_float_array(values: list[float]) -> str:
    return "array[" + ",".join(f"{value:.8f}" for value in values) + "]::double precision[]"


def seed_sql(manifest: dict[str, Any], sources: list[dict[str, Any]], documents: list[dict[str, Any]],
             passages: list[dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    lines = [
        f"-- Auto-generated versioned legal corpus seed ({manifest['corpus_version']})",
        f"-- Embedding model: {MODEL} ({VERSION}), dims={DIMENSIONS}", "begin;",
        "-- Bootstrap only. Never replace an existing editorial registry.",
        "lock table public.nyay_legal_sources in share row exclusive mode;",
        "do $$ begin if exists(select 1 from public.nyay_legal_sources) then raise exception 'Legal corpus bootstrap refused: source registry is not empty'; end if; end $$;",
    ]
    for s in sources:
        vals = [s[k] for k in ("source_id", "title", "authority", "canonical_url", "domain", "region", "source_type", "trust_tier", "latest_content_hash", "latest_version", "known_limitations")]
        lines.append("insert into public.nyay_legal_sources (source_id,title,authority,canonical_url,domain,region,source_type,trust_tier,latest_content_hash,latest_version,known_limitations) values (" + ",".join(sql_str(v) for v in vals) + ") on conflict (source_id) do update set latest_content_hash=excluded.latest_content_hash,latest_version=excluded.latest_version,updated_at=now();")
    for d in documents:
        vals = [d[k] for k in ("document_id", "source_id", "version", "title", "official_url", "authority", "region", "source_language", "publication_date", "effective_from", "effective_until")]
        tail = [str(d["date_independent"]).lower(), sql_str(d["content_hash"]), sql_str(d["raw_storage_path"]), sql_str(d["review_state"]), str(d["is_active"]).lower(), sql_str(d["acquired_at"]), sql_text_array(d["limitations"])]
        lines.append("insert into public.nyay_legal_documents (document_id,source_id,version,title,official_url,authority,region,source_language,publication_date,effective_from,effective_until,date_independent,content_hash,raw_storage_path,review_state,is_active,acquired_at,limitations) values (" + ",".join([*(sql_str(v) for v in vals), *tail]) + ") on conflict (document_id) do update set content_hash=excluded.content_hash,review_state=excluded.review_state,is_active=excluded.is_active;")
    for p in passages:
        vals = [p[k] for k in ("passageId", "documentId", "sourceId", "version", "title", "locator", "text", "officialUrl", "authority", "region", "domain", "sourceLanguage", "validFrom", "validUntil")]
        tail = [str(p["dateIndependent"]).lower(), sql_str(p["acquiredAt"]), sql_str(p["reviewState"]), str(p["isActive"]).lower(), sql_text_array(p["limitations"]), sql_text_array(p["relatedPassageIds"]), sql_text_array(p["keywords"]), sql_str(p["contentHash"]), sql_float_array(p["embedding"]), sql_str(MODEL), sql_str(VERSION), str(DIMENSIONS)]
        lines.append("insert into public.nyay_legal_passages (passage_id,document_id,source_id,version,title,locator,text,official_url,authority,region,domain,source_language,valid_from,valid_until,date_independent,acquired_at,review_state,is_active,limitations,related_passage_ids,keywords,content_hash,embedding_f32,embedding_model,embedding_version,embedding_dimensions) values (" + ",".join([*(sql_str(v) for v in vals), *tail]) + ") on conflict (passage_id) do update set text=excluded.text,embedding_f32=excluded.embedding_f32,embedding_model=excluded.embedding_model,embedding_version=excluded.embedding_version,embedding_dimensions=excluded.embedding_dimensions,review_state=excluded.review_state,is_active=excluded.is_active;")
    for rel in relations:
        vals = [rel[k] for k in ("id", "from_passage_id", "to_passage_id", "relation_type", "cutoff_date", "notes")]
        lines.append("insert into public.nyay_legal_passage_relations (id,from_passage_id,to_passage_id,relation_type,cutoff_date,notes) values (" + ",".join(sql_str(v) for v in vals) + ") on conflict (id) do update set notes=excluded.notes;")
    lines.append("commit;")
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp = Path(handle.name)
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write regenerated corpus artifacts")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    key = os.environ.get("OPENAI_EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_EMBEDDING_API_KEY or OPENAI_API_KEY is required")
    passages = json.loads((CORPUS / "passages.json").read_text())
    inputs = [f"{p['title']} | {p['locator']}\n{p['text']}" for p in passages]
    if sum(map(len, inputs)) > MAX_INPUT_CHARS:
        raise RuntimeError("corpus character cap exceeded")
    counter = [0]
    fingerprint = hashlib.sha256(json.dumps({"model": MODEL, "dimensions": DIMENSIONS, "inputs": inputs}, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    cache_path = ROOT / "runtime" / "openai-legal-embedding-checkpoint.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if cache.get("fingerprint") == fingerprint:
        vectors = cache.get("vectors", [])
        total_tokens = int(cache.get("input_tokens", 0))
    else:
        vectors, total_tokens = [], 0
    if len(vectors) > len(inputs) or (len(vectors) != len(inputs) and len(vectors) % 16 != 0):
        raise RuntimeError("invalid embedding checkpoint")
    for start in range(len(vectors), len(inputs), 16):
        batch, tokens = embed(inputs[start:start + 16], key, counter)
        vectors.extend(batch)
        total_tokens += tokens
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(cache_path, json.dumps({"fingerprint": fingerprint, "vectors": vectors, "input_tokens": total_tokens}))
    if len(passages) != len(vectors):
        raise RuntimeError("passage/vector count mismatch")
    for passage, vector in zip(passages, vectors):
        passage.update(embedding=vector, embeddingModel=MODEL, embeddingVersion=VERSION, embeddingDimensions=DIMENSIONS)
    manifest = json.loads((CORPUS / "corpus_manifest.json").read_text())
    corpus_version = "2026-11-20.openai-384.v1"
    built_at = manifest.get("built_at") if manifest.get("corpus_version") == corpus_version else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest.update(corpus_version=corpus_version, built_at=built_at, embedding_model=MODEL, embedding_version=VERSION, embedding_dimensions=DIMENSIONS)
    fixture_path = ROOT / "frontend/src/fixtures/openai-legal-query-embeddings.json"
    if fixture_path.exists():
        fixture = json.loads(fixture_path.read_text())["exact_section_cpa_s35_companions"]
        manifest["embedding_canary"] = {"input": fixture["query"], "embedding": fixture["embedding"]}
    sources = json.loads((CORPUS / "sources.json").read_text())
    documents = json.loads((CORPUS / "documents.json").read_text())
    relations = json.loads((CORPUS / "relations.json").read_text())
    bundle = {"manifest": manifest, "passages": passages, "relations": relations}
    if args.apply:
        atomic_write(CORPUS / "passages.json", json.dumps(passages, indent=2, ensure_ascii=False) + "\n")
        atomic_write(CORPUS / "corpus_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        atomic_write(CORPUS / "seed_legal_corpus.sql", seed_sql(manifest, sources, documents, passages, relations))
        ts = "// Auto-generated by supabase/operations/reembed-legal-corpus-openai.py — do not edit.\n// Official texts and provenance are unchanged; embeddings use the manifest configuration.\n\nexport const LEGAL_CORPUS_BUNDLE = " + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + " as const\n"
        atomic_write(ROOT / "supabase/functions/nyay-api/legal-corpus-data.ts", ts)
    print(json.dumps({"model": MODEL, "version": VERSION, "dimensions": DIMENSIONS, "passages": len(passages), "requests": counter[0], "input_tokens": total_tokens, "applied": args.apply}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
