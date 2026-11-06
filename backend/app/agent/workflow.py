"""Actual runner definition for the reused system-information drawer."""


def workflow_description(settings):
    nodes = [
        (
            "checks",
            "Access and request checks",
            "Owner, CSRF, attachments, idempotency and durable turn receipt.",
        ),
        (
            "safety",
            "Immediate safety guidance",
            "Approved protective guidance can arrive before research; no unchecked legal claims.",
        ),
        (
            "context",
            "Relevant context",
            "Original question, scoped private evidence, dispute stage and current date.",
        ),
        (
            "primary",
            "Primary reasoning agent",
            "Understands the issue, chooses research and prepares a structured answer in one logical session.",
        ),
        (
            "research",
            "Selective legal research",
            "Concurrent focused queries and safe downloads; ranked passages with provenance and limits.",
        ),
        (
            "verify",
            "Claim checks and adaptive review",
            "Mechanical checks always; independent semantic review for original consequential advice and case patches.",
        ),
        (
            "repair",
            "One targeted repair",
            "Only affected content; changed consequential claims are reviewed again within the shared allowance.",
        ),
        (
            "persist",
            "Commit and deliver",
            "Authorized versioned case updates, draft artifacts, answer and replay-safe receipt.",
        ),
    ]
    return {
        "name": "Nyay Saathi primary-agent workflow",
        "version": "primary-agent-v2.0",
        "nodes": [{"id": i, "label": label, "detail": detail} for i, label, detail in nodes],
        "edges": [
            {"from": "checks", "to": "safety", "condition": "immediate danger detected"},
            {"from": "checks", "to": "context", "condition": "authorized"},
            {"from": "context", "to": "primary", "condition": "scoped context ready"},
            {"from": "primary", "to": "research", "condition": "material evidence gap and budget"},
            {"from": "research", "to": "primary", "condition": "evidence or honest limitations"},
            {"from": "primary", "to": "verify", "condition": "draft ready"},
            {
                "from": "verify",
                "to": "repair",
                "condition": "specific defects and two requests remain",
            },
            {"from": "repair", "to": "verify", "condition": "changed claims require fresh review"},
            {
                "from": "verify",
                "to": "persist",
                "condition": "publish supported content; qualify unresolved parts",
            },
        ],
        "decisions": [
            {
                "if": "Independent research questions",
                "then": "Search concurrently within a shared allowance.",
            },
            {
                "if": "General educational question",
                "then": "Answer without populating personal case memory.",
            },
            {
                "if": "Search or review unavailable",
                "then": "Preserve safe useful content and state the specific limitation.",
            },
        ],
        "limits": {
            "model_calls_per_turn": settings.agent_max_requests,
            "retrieval_expansions": settings.agent_max_batches,
            "revision_attempts": 1,
        },
    }
