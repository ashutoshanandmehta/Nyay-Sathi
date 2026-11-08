import hashlib
import json
import logging
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.runner import PrimaryAgent
from app.api.routes import router
from app.config import get_settings
from app.db import Database
from app.graph.workflow import AssistantGraph
from app.knowledge.editorial import (
    EditorialDecision,
    EditorialProposal,
    EditorialRegistry,
    LanguagePackRegistry,
)
from app.knowledge.propositions import LegalKnowledgeFactory
from app.platform.adapters import generate_trace_id, platform_readiness_report
from app.rag.retrieval import HybridRetriever
from app.security.abuse import AbuseController
from app.security.ownership import OWNER_COOKIE, csrf_guard
from app.services.knowledge import SharedKnowledgeService


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        for marker in (
            "sk-",
            "OPENAI_API_KEY",
            "nyay_owner=",
            "enc:v1:",
            '"current_message":',
            '"extracted_text":',
        ):
            if marker in text:
                record.msg, record.args = "[sensitive log content redacted]", ()
                break
        return True


logging.getLogger().addFilter(RedactingFilter())
settings = get_settings()
app = FastAPI(title="Nyay Saathi API", version="0.2.0", docs_url="/api/docs", redoc_url=None)
app.state.settings = settings
app.state.db = Database(settings.database_path)
app.state.retriever = HybridRetriever(settings)
app.state.assistant_graph = (
    PrimaryAgent(settings, app.state.retriever)
    if settings.assistant_engine == "primary_agent"
    else AssistantGraph(settings, app.state.retriever)
)
app.state.shared_knowledge = SharedKnowledgeService()
app.state.knowledge_factory = LegalKnowledgeFactory()
app.state.requests = defaultdict(deque)
app.state.abuse = AbuseController()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Trace-Id", "traceparent"],
    expose_headers=["X-Trace-Id"],
)


@app.middleware("http")
async def security_and_limits(request: Request, call_next):
    trace_id = generate_trace_id(
        request.headers.get("traceparent") or request.headers.get("X-Trace-Id")
    )
    request.state.trace_id = trace_id

    if not app.state.requests:
        app.state.abuse.clear()

    now_mono = time.monotonic()
    ip_key = request.client.host if request.client else "unknown"
    bucket = app.state.requests[ip_key]
    while bucket and bucket[0] < now_mono - 60:
        bucket.popleft()
    if len(bucket) >= app.state.settings.requests_per_minute:
        return JSONResponse(
            {"detail": "Request limit exceeded"},
            status_code=429,
            headers={"X-Trace-Id": trace_id},
        )
    bucket.append(now_mono)

    raw_cookie = request.cookies.get(OWNER_COOKIE)
    device_key = (
        hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()[:16] if raw_cookie else None
    )
    is_turn = request.method == "POST" and (
        request.url.path.endswith("/turns") or request.url.path.endswith("/turns/stream")
    )
    allowed, limit_reason = app.state.abuse.check_http_rate(
        ip_key=f"sub:{ip_key}",
        device_key=device_key,
        is_turn_request=is_turn,
        settings=app.state.settings,
    )
    if not allowed:
        app.state.db.record_security_audit(
            "rate_limit_blocked", metadata={"reason": limit_reason}
        )
        return JSONResponse(
            {"detail": "Request limit exceeded", "code": limit_reason},
            status_code=429,
            headers={"X-Trace-Id": trace_id},
        )

    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ai_configured": app.state.settings.ai_configured,
        "engine_version": getattr(app.state.assistant_graph, "engine_version", "legacy-graph"),
        "corpus_version": app.state.retriever.corpus_version,
    }


@app.get("/api/system/platform-readiness")
def platform_readiness():
    return platform_readiness_report(
        app.state.settings,
        app.state.knowledge_factory.summary(),
        app.state.abuse.snapshot(),
    )


@app.get("/api/system/language-packs")
def language_packs():
    return {"packs": LanguagePackRegistry.list_packs()}


@app.get("/api/system/editorial")
def list_editorial_queue(status: str | None = None):
    reg = EditorialRegistry(app.state.db)
    return {
        "certified_factory": app.state.knowledge_factory.summary(),
        "queue": reg.list_items(status=status),
    }


@app.post("/api/system/editorial", dependencies=[Depends(csrf_guard)])
def submit_editorial_proposal(body: EditorialProposal):
    reg = EditorialRegistry(app.state.db)
    return reg.submit(body)


@app.post("/api/system/editorial/{item_id}/decide", dependencies=[Depends(csrf_guard)])
def decide_editorial_proposal(item_id: str, body: EditorialDecision):
    reg = EditorialRegistry(app.state.db)
    try:
        return reg.decide(item_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/system/knowledge-base")
def knowledge_base():
    retriever = app.state.retriever
    register_path = Path(__file__).parents[2] / "data" / "manifests" / "source-register.json"
    register = json.loads(register_path.read_text()) if register_path.exists() else []
    lexical_counts = Counter(p["source_id"] for p in retriever.passages)
    vector_ids: set[str] = set()
    if retriever.collection is not None:
        try:
            vector_ids = set(retriever.collection.get(include=[])["ids"])
        except Exception:
            vector_ids = set()
    passage_by_id = {p["passage_id"]: p for p in retriever.passages}
    vector_counts = Counter(
        passage_by_id[passage_id]["source_id"]
        for passage_id in vector_ids
        if passage_id in passage_by_id
    )
    structured = app.state.shared_knowledge.public_payload()
    layers = app.state.shared_knowledge.layer_summary()
    for layer in layers:
        if layer["id"] == "applicable_law":
            layer["count"] = len(register)
    return {
        "corpus_version": retriever.corpus_version,
        "collection_name": "official_consumer_law_v1",
        "total_passages": len(retriever.passages),
        "certified_knowledge_factory": app.state.knowledge_factory.summary(),
        "vector_index_enabled": retriever.collection is not None,
        "vector_passages": len(vector_ids),
        "retrieval_pipeline": [
            "Editor-certified proposition pack (OpenSearch hybrid index)",
            "Public evidence cache & SHA-256 passage verification",
            "Issue relevance, authority hierarchy & applicability reranking",
        ]
        if isinstance(app.state.assistant_graph, PrimaryAgent)
        else [
            "BM25 lexical search",
            f"OpenAI {app.state.settings.openai_embedding_model} embeddings in persistent Chroma",
            "Reciprocal rank fusion",
        ],
        "knowledge_id": structured["knowledge_id"],
        "knowledge_version": structured["version"],
        "last_checked": structured["last_checked"],
        "review_status": structured["status"],
        "scope": structured["scope"],
        "separation_rule": structured["separation_rule"],
        "layers": layers,
        "intake_playbooks": structured["intake_playbooks"],
        "evidence_playbooks": structured["evidence_playbooks"],
        "procedures": structured["procedures"],
        "templates": structured["templates"],
        "selected_judgments": structured["selected_judgments"],
        "lawyer_preparation": structured["lawyer_preparation"],
        "referrals": structured["referrals"],
        "storage_map": structured["storage_map"],
        "sources": [
            {
                **source,
                "passage_count": lexical_counts[source["source_id"]],
                "vector_passage_count": vector_counts[source["source_id"]],
                "locators": sorted(
                    {
                        p["locator"]
                        for p in retriever.passages
                        if p["source_id"] == source["source_id"]
                    }
                ),
            }
            for source in register
        ],
    }


@app.get("/api/system/agent-workflow")
def agent_workflow():
    if isinstance(app.state.assistant_graph, PrimaryAgent):
        from app.agent.workflow import workflow_description

        return workflow_description(app.state.settings)
    return {
        "name": "Nyay Saathi turn workflow",
        "version": "graph-v7-verified-answer-units",
        "nodes": [
            {
                "id": "checks",
                "label": "Access and turn checks",
                "detail": "Owner cookie, CSRF, case ownership, idempotency, and one active turn per case.",
            },
            {
                "id": "context",
                "label": "Bounded context builder",
                "detail": "Always loads current IST date, pending questions, private case workspace, provenance, contradictions, rolling summary, recent turns, and case-scoped evidence.",
            },
            {
                "id": "triage",
                "label": "Independent request interpretation",
                "detail": "Read-only versioned interpretation of tasks, relationships, entities and risk before intake. Task flags propose, never authorize, case writes.",
            },
            {
                "id": "intake",
                "label": "Structured intake",
                "detail": "Selects a versioned intake/evidence playbook, then extracts typed facts, provenance, corrections, completed actions, intent, and at most two unanswered questions.",
            },
            {
                "id": "research",
                "label": "Hybrid legal research",
                "detail": "Rewrites the query, searches approved official passages with BM25 and vectors, then fuses rankings.",
            },
            {
                "id": "assess_information",
                "label": "Assess information gaps",
                "detail": "Checks whether local passages support the requests; distinguishes missing personal facts from missing public procedure and plans privacy-safe topic/angle queries.",
            },
            {
                "id": "web_research",
                "label": "Bounded official web research",
                "detail": "Builds public queries from approved vocabulary, safely fetches at most three documents, preserves snapshots, and submits relevant passages for answer review.",
            },
            {
                "id": "plan_resolution",
                "label": "Plan recipient and preparation",
                "detail": "Uses reported submissions, responses, commitments and outcomes; evaluates conditional routes, eligibility gaps, fee basis and preparation effort, then selects a channel-specific draft contract. No external action is performed.",
            },
            {
                "id": "execute_tasks",
                "label": "Policy-controlled task workflows",
                "detail": "Prioritizes safety, routes general and legal tasks independently, runs bounded public research, records actual tool outcomes and preserves case isolation.",
            },
            {
                "id": "respond",
                "label": "Task-scoped candidate units",
                "detail": "One batched generation proposes independently identified claims and draft artifacts per task. Evidence uses canonical IDs; model statuses grant no publication permission.",
            },
            {
                "id": "review",
                "label": "Independent feedback",
                "detail": "One independent batched review checks claim meaning and proposed case changes separately.",
            },
            {
                "id": "revise",
                "label": "Bounded revision",
                "detail": "If review fails, one revision applies the findings, followed by a fresh independent review before the hard safety gate.",
            },
            {
                "id": "rereview",
                "label": "Review revised answer",
                "detail": "Independently rechecks the revised answer against the current message, private evidence, memory, and approved legal passages.",
            },
            {
                "id": "verify",
                "label": "Hard safety gate",
                "detail": "Validates claim identity, task applicability, evidence provenance, tool records, legal eligibility, dates and dependencies.",
            },
            {
                "id": "persist",
                "label": "Persist and display",
                "detail": "Saves answer, sources, memory version, token usage, and graph checkpoint.",
            },
            {
                "id": "withhold",
                "label": "Withhold unsupported law",
                "detail": "Withholds only unsupported claims and their dependencies.",
            },
        ],
        "edges": [
            {"from": "checks", "to": "context", "condition": "authorised and not concurrently running"},
            {"from": "context", "to": "triage", "condition": "always"},
            {"from": "triage", "to": "intake", "condition": "always; urgent reason remains in state"},
            {"from": "intake", "to": "research", "condition": "needs_retrieval = true"},
            {"from": "intake", "to": "plan_resolution", "condition": "needs_retrieval = false"},
            {"from": "research", "to": "assess_information", "condition": "retrieval complete or honest empty result"},
            {"from": "assess_information", "to": "plan_resolution", "condition": "sufficient, missing personal fact, disabled, unsupported, or budget exhausted"},
            {"from": "assess_information", "to": "web_research", "condition": "public information gap with permitted query intents"},
            {"from": "web_research", "to": "plan_resolution", "condition": "fetched passages or honest research limitation"},
            {"from": "plan_resolution", "to": "execute_tasks", "condition": "preparation plan and conditional draft contract ready"},
            {"from": "execute_tasks", "to": "respond", "condition": "all tasks have execution results or honest limitations"},
            {"from": "respond", "to": "review", "condition": "candidate response produced"},
            {"from": "review", "to": "verify", "condition": "claims reviewed; no repair needed or available"},
            {"from": "review", "to": "revise", "condition": "review fails and one revision remains within budget"},
            {"from": "revise", "to": "rereview", "condition": "feedback applied"},
            {"from": "rereview", "to": "verify", "condition": "independent review of revised answer complete"},
            {"from": "verify", "to": "persist", "condition": "publish independently approved claims; record supported/partial/deferred task outcomes"},
            {"from": "verify", "to": "withhold", "condition": "affected claim lacks support, applicability, valid provenance or independent review"},
            {"from": "withhold", "to": "persist", "condition": "safe limitation response"},
        ],
        "decisions": [
            {"if": "Greeting or ordinary factual intake", "then": "Skip legal retrieval and answer conversationally."},
            {"if": "Consumer-law options or material legal conclusion", "then": "Require approved-source retrieval before answering."},
            {"if": "Verification still fails", "then": "Withhold unsupported portions rather than displaying them."},
            {"if": "A request is retried", "then": "Reuse its request ID; a successful turn is returned once and a failed turn can safely rerun."},
        ],
        "limits": {
            "model_calls_per_turn": app.state.settings.max_model_calls_per_turn,
            "retrieval_expansions": 1,
            "revision_attempts": 1,
            "web_queries": app.state.settings.web_max_queries,
            "web_documents": app.state.settings.web_max_documents,
            "web_research_seconds": app.state.settings.web_research_timeout_seconds,
        },
    }


app.include_router(router)
