"""Pluggable production infrastructure registry for national-scale deployment."""

from __future__ import annotations

import secrets
from typing import Any

TEMPORAL_WORKFLOW_QUEUES = [
    {
        "queue": "nyay-ocr-ingestion",
        "workflow": "AttachmentOcrAndIsolationWorkflow",
        "purpose": "Isolated PDF/image OCR, malware scanning, and page-span indexing.",
    },
    {
        "queue": "nyay-knowledge-factory",
        "workflow": "LegalSourceAcquisitionAndHashWorkflow",
        "purpose": "Official source snapshotting, passage SHA-256 hashing, and amendment checks.",
    },
    {
        "queue": "nyay-retention-lifecycle",
        "workflow": "GuestInactivityPurgeAndReminderWorkflow",
        "purpose": "1-year inactivity expiry sweeps and physical purge after DEK destruction.",
    },
    {
        "queue": "nyay-editorial-review",
        "workflow": "LegalPropositionCertificationWorkflow",
        "purpose": "Licensed-advocate review queue for proposition-to-source certification.",
    },
    {
        "queue": "nyay-human-escalation",
        "workflow": "LawyerEscalationBundleDispatchWorkflow",
        "purpose": "User-consented lawyer/legal-aid handoff bundle packaging and receipt tracking.",
    },
]

SLO_TARGETS = {
    "monthly_availability_target": "99.95%",
    "safety_guidance_p95_ms": 500,
    "ordinary_response_p95_seconds": 20,
    "researched_response_p95_seconds": 40,
    "rpo_minutes": 5,
    "rto_minutes": 30,
}


def generate_trace_id(incoming: str | None = None) -> str:
    """Extract W3C traceparent trace-id or generate a fresh 128-bit OpenTelemetry trace ID."""
    if incoming:
        parts = incoming.strip().split("-")
        if len(parts) == 4 and len(parts[1]) == 32:
            return parts[1]
        if 16 <= len(incoming.strip()) <= 64 and incoming.strip().isalnum():
            return incoming.strip()
    return secrets.token_hex(16)


def platform_readiness_report(settings, knowledge_summary: dict[str, Any], abuse_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Describe active vs. configured national-scale infrastructure components without secrets."""
    return {
        "architecture": "stateless-fastapi-copilot-v2",
        "regions": {
            "primary": settings.primary_region,
            "disaster_recovery": settings.dr_region,
        },
        "slo_targets": SLO_TARGETS,
        "subsystems": {
            "transactional_db": {
                "target": "PostgreSQL Multi-AZ",
                "mode": "postgresql_cluster" if settings.postgresql_dsn else "sqlite_wal_local",
                "configured": bool(settings.postgresql_dsn),
            },
            "ephemeral_state_and_locks": {
                "target": "Redis Cluster",
                "mode": "redis_cluster" if settings.redis_url else "in_process_sliding_window",
                "configured": bool(settings.redis_url),
            },
            "object_storage": {
                "target": "Encrypted Object Storage (India region)",
                "mode": "cloud_object_storage" if settings.object_storage_bucket else "envelope_encrypted_filesystem",
                "configured": bool(settings.object_storage_bucket),
            },
            "legal_search": {
                "target": "OpenSearch Hybrid Legal Index",
                "mode": "opensearch_cluster" if settings.opensearch_url else "opensearch_local_hybrid",
                "index": settings.opensearch_index,
                "configured": bool(settings.opensearch_url),
                "knowledge": knowledge_summary,
            },
            "workflow_orchestration": {
                "target": "Temporal Cluster",
                "mode": "temporal_remote" if settings.temporal_target else "durable_sqlite_executor",
                "configured": bool(settings.temporal_target),
                "task_queues": TEMPORAL_WORKFLOW_QUEUES,
            },
            "encryption_and_kms": {
                "target": "KMS Envelope Encryption (KEK -> per-case DEK)",
                "key_id": settings.kms_key_id,
                "envelope_encryption_enabled": settings.envelope_encryption_enabled,
            },
            "observability": {
                "target": "OpenTelemetry Traces & Redacted Operational Metrics",
                "otlp_configured": bool(settings.otlp_endpoint),
                "prompt_and_document_logging": "strictly_prohibited",
            },
        },
        "pdf_licensing_boundary": {
            "active_engine": settings.pdf_engine,
            "permissive_option_available": True,
            "supported_engines": ["pymupdf", "pypdf"],
        },
        "circuit_breakers": abuse_snapshot,
    }
