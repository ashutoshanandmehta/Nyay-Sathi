"""DevSpace: the person running this copy sets their own key, models and .env settings.

Nyay Saathi is bring-your-own-key: each copy belongs to whoever runs it. The saved API key
is never sent back in full, values are never logged, and ``DEVSPACE_ENABLED=false`` turns
all of this off for anyone hosting a shared copy.
"""

from __future__ import annotations

import json
import os
import re
import types
import typing
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app.config import ROOT, Settings, get_settings
from app.practice.engine import (
    PERSONA_INSTRUCTIONS,
    ROLEPLAY_INSTRUCTIONS,
    SETUP_INSTRUCTIONS,
)
from app.runtime import build_runtime
from app.security.ownership import OwnerContext, csrf_guard, owner_context

router = APIRouter(prefix="/api/system")
PROMPTS = Path(__file__).parents[1] / "prompts"
API_KEY = "OPENAI_API_KEY"

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Models",
        (
            "OPENAI_CHAT_MODEL",
            "OPENAI_REVIEW_MODEL",
            "OPENAI_EMBEDDING_MODEL",
            "OPENAI_TRANSCRIPTION_MODEL",
            "OPENAI_TTS_MODEL",
            "OPENAI_WEB_SEARCH_MODEL",
            "OPENAI_ROLEPLAY_MODEL",
            "AGENT_REASONING_EFFORT",
            "PRACTICE_REASONING_EFFORT",
        ),
    ),
    (
        "Runtime & security",
        (
            "APP_ORIGIN",
            "COOKIE_SECURE",
            "REQUESTS_PER_MINUTE",
            "ASSISTANT_ENGINE",
            "VECTOR_INDEX_ENABLED",
        ),
    ),
    (
        "Agent caps",
        (
            "AGENT_MAX_REQUESTS",
            "AGENT_MAX_ROUNDS",
            "AGENT_DEADLINE_SECONDS",
            "AGENT_RESEARCH_SECONDS",
            "AGENT_MAX_BATCHES",
            "AGENT_MAX_QUERIES",
            "AGENT_MAX_DOCUMENTS",
            "AGENT_MAX_PASSAGES",
            "AGENT_MAX_TOKENS",
            "AGENT_MAX_OUTPUT_TOKENS",
            "MAX_MODEL_CALLS_PER_TURN",
            "AGENT_MAX_REPAIRS",
            "AGENT_REPAIR_RESERVE",
            "AGENT_PASSAGES_PER_SOURCE",
            "AGENT_SEARCH_SHARE",
        ),
    ),
    (
        "Web research",
        (
            "WEB_RESEARCH_ENABLED",
            "WEB_MAX_QUERIES",
            "WEB_MAX_DOCUMENTS",
            "WEB_RESEARCH_TIMEOUT_SECONDS",
            "WEB_MAX_DOWNLOAD_BYTES",
            "WEB_MAX_PDF_PAGES",
            "WEB_CACHE_TTL_SECONDS",
        ),
    ),
    (
        "Evaluation caps",
        ("LIVE_EVAL_MAX_CASES", "LIVE_EVAL_MAX_MODEL_CALLS", "LIVE_EVAL_MAX_COST_USD"),
    ),
)
EDITABLE = {name for _, names in GROUPS for name in names}
# The CORS middleware reads this once at startup.
RESTART_REQUIRED = {"APP_ORIGIN"}

# Presets for the model pickers; the current value is always included and any name can be typed.
MODEL_OPTIONS = {
    "OPENAI_CHAT_MODEL": ["gpt-6-luna", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4-turbo"],
    "OPENAI_REVIEW_MODEL": ["gpt-6.1-sol", "gpt-4o", "gpt-4o-mini", "gpt-4.1"],
    "OPENAI_EMBEDDING_MODEL": [
        "text-embedding-3-small",
        "text-embedding-3-large",
        "text-embedding-ada-002",
    ],
    "OPENAI_TRANSCRIPTION_MODEL": ["gpt-transcribe", "whisper-1"],
    "OPENAI_TTS_MODEL": ["gpt-realtime-2.1-mini", "tts-1", "tts-1-hd"],
    "OPENAI_WEB_SEARCH_MODEL": ["gpt-6.1-sol", "gpt-6-astra", "gpt-4o"],
    # Empty means "same as the chat model".
    "OPENAI_ROLEPLAY_MODEL": ["", "gpt-6-luna", "gpt-4o", "gpt-4o-mini", "gpt-4.1"],
}
# Empty means "provider default".
EFFORT_OPTIONS = ["", "minimal", "low", "medium", "high"]

ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


class DevspaceUpdate(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)
    clear_api_key: bool = False


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _require_enabled(request: Request) -> Settings:
    settings = _settings(request)
    if not settings.devspace_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    return settings


def _env_path(request: Request) -> Path:
    return getattr(request.app.state, "env_path", None) or ROOT / ".env"


def mask_key(key: str | None) -> str:
    if not key:
        return ""
    return f"{key[:7]}…{key[-4:]}" if len(key) > 14 else "••••"


def _field(name: str):
    return Settings.model_fields[name.lower()]


def _describe(name: str, settings: Settings) -> dict[str, Any]:
    info = _field(name)
    annotation = info.annotation
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    if typing.get_origin(annotation) in (typing.Union, types.UnionType) and len(args) == 1:
        annotation = args[0]
    field: dict[str, Any] = {
        "name": name,
        "value": getattr(settings, name.lower()),
        "restart_required": name in RESTART_REQUIRED,
    }
    if name in MODEL_OPTIONS:
        current = field["value"] or ""
        options = MODEL_OPTIONS[name]
        field.update(type="model", options=options + ([current] if current not in options else []))
    elif name.endswith("_REASONING_EFFORT"):
        field.update(type="choice", options=EFFORT_OPTIONS)
    elif typing.get_origin(annotation) is typing.Literal:
        field.update(type="choice", options=list(typing.get_args(annotation)))
    elif annotation is bool:
        field["type"] = "boolean"
    elif annotation in (int, float):
        field["type"] = "integer" if annotation is int else "number"
        for meta in info.metadata:
            for key, bound in (("ge", "min"), ("gt", "min"), ("le", "max"), ("lt", "max")):
                if getattr(meta, key, None) is not None:
                    field[bound] = getattr(meta, key)
    else:
        field["type"] = "text"
    return field


def _curl(request: Request, settings: Settings, primary: str) -> dict[str, str]:
    base = str(request.base_url).rstrip("/")
    session = (
        "  -H 'Content-Type: application/json' \\\n"
        "  -H 'X-CSRF-Token: <NYAY_CSRF>' \\\n"
        "  -b 'nyay_owner=<NYAY_OWNER>; nyay_csrf=<NYAY_CSRF>' \\\n"
    )
    turn_body = {
        "content": "My landlord has kept my security deposit. What can I do?",
        "language": "en",
        "request_id": "<NEW_UUID>",
        "attachment_ids": [],
    }
    responses_body = {
        "model": settings.openai_chat_model,
        "instructions": primary,
        "input": [
            {"role": "user", "content": "My landlord has kept my security deposit. What can I do?"}
        ],
        "store": False,
    }
    return {
        "turn_stream": (
            "# Cookies and CSRF token: copy them from your browser's storage for this site.\n"
            f"curl -N -X POST '{base}/api/conversations/<CONVERSATION_ID>/turns/stream' \\\n"
            f"{session}  -d '{json.dumps(turn_body)}'"
        ),
        "responses_api": (
            "# The app's own call also sends a strict JSON schema and tools; this is the plain version.\n"
            "curl https://api.openai.com/v1/responses \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            '  -H "Authorization: Bearer $OPENAI_API_KEY" \\\n'
            "  -d @- <<'JSON'\n"
            f"{json.dumps(responses_body, ensure_ascii=False, indent=2)}\nJSON"
        ),
        "roleplay_chat": (
            f"curl -N -X POST '{base}/api/conversations/<CONVERSATION_ID>/roleplay/chat/stream"
            "?session_id=<SESSION_ID>' \\\n"
            f"{session}  -d '{json.dumps({'message': 'Where is he being held?', 'language': 'en'})}'"
        ),
    }


@router.get("/devspace")
def get_devspace(request: Request, _: Annotated[OwnerContext, Depends(owner_context)]):
    settings = _require_enabled(request)
    primary = (PROMPTS / "primary.md").read_text()
    return {
        "api_key": {
            "configured": settings.ai_configured,
            "masked": mask_key(settings.openai_api_key),
        },
        "groups": [
            {"title": title, "fields": [_describe(name, settings) for name in names]}
            for title, names in GROUPS
        ],
        "prompts": {
            "primary": primary,
            "review": (PROMPTS / "primary-review.md").read_text(),
            "roleplay_setup": SETUP_INSTRUCTIONS,
            "roleplay_persona": PERSONA_INSTRUCTIONS,
            "roleplay_reply": ROLEPLAY_INSTRUCTIONS,
        },
        "curl": _curl(request, settings, primary),
    }


def _format_env(value: Any) -> str:
    text = _plain(value)
    if re.search(r"[\s#'\"\\$`]", text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def write_env(path: Path, values: dict[str, str | None]) -> None:
    """Set (or, for None, remove) keys in a .env file, keeping comments and order."""
    lines = path.read_text().splitlines() if path.exists() else []
    out, seen = [], set()
    for line in lines:
        match = ENV_LINE_RE.match(line)
        if match and match.group(1) in values:
            name = match.group(1)
            # Every occurrence is replaced: in dotenv the last duplicate wins.
            if values[name] is not None and name not in seen:
                out.append(f"{name}={values[name]}")
            seen.add(name)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen and v is not None]
    tmp = path.with_name(path.name + ".devspace.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write("\n".join(out) + "\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


@router.post("/devspace", dependencies=[Depends(csrf_guard)])
def save_devspace(
    body: DevspaceUpdate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    current = _require_enabled(request)
    unknown = sorted(set(body.updates) - EDITABLE - {API_KEY})
    if unknown:
        raise HTTPException(status_code=400, detail={"unknown_settings": unknown})

    overrides: dict[str, Any] = {}
    for name, value in body.updates.items():
        if name == API_KEY:
            key = str(value or "").strip()
            # A masked or empty value is the key already saved; keep it.
            if key and "•" not in key and "…" not in key:
                overrides[API_KEY] = key
        else:
            overrides[name] = value
    if body.clear_api_key:
        overrides[API_KEY] = None

    # Validate without re-reading the environment, so the running copy's other values stay.
    try:
        candidate = Settings.model_validate(
            {**current.model_dump(), **{k.lower(): v for k, v in overrides.items()}}
        )
    except ValidationError as exc:
        errors = {
            str(e["loc"][0]).upper(): e["msg"] for e in exc.errors(include_url=False) if e["loc"]
        }
        raise HTTPException(status_code=422, detail={"errors": errors}) from None

    changed = [
        name
        for name in overrides
        if getattr(candidate, name.lower()) != getattr(current, name.lower())
    ]
    if changed:
        env_values = {
            name: None
            if name == API_KEY and body.clear_api_key
            else _format_env(getattr(candidate, name.lower()))
            for name in changed
        }
        write_env(_env_path(request), env_values)
        # Environment variables outrank .env, so set them too for later get_settings() calls.
        for name in changed:
            os.environ[name] = _plain(getattr(candidate, name.lower()))
        get_settings.cache_clear()
        candidate.ensure_dirs()
        state = request.app.state
        state.settings = candidate
        state.retriever, state.assistant_graph = build_runtime(candidate)
        for cache in ("practice_index", "roleplay_setups"):
            if hasattr(state, cache):
                delattr(state, cache)
        state.db.record_security_audit(
            "devspace_settings_updated", owner_id=owner.owner_id, metadata={"fields": changed}
        )
    return {
        "saved": changed,
        "restart_required": [name for name in changed if name in RESTART_REQUIRED],
        "configured": candidate.ai_configured,
    }
