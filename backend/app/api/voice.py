"""Live voice input: a short-lived Realtime client secret for browser-to-OpenAI WebRTC.

Audio goes straight from the browser to OpenAI (lowest latency, nothing relayed through
this server). The real API key never leaves the server: the browser gets an ephemeral
secret scoped to a transcription-only session. Minting is not billed; usage limits are
still checked here, and the browser only connects after a deliberate press-and-hold.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAI

from app.api.routes import _check_model_circuit, live_settings
from app.security.ownership import OwnerContext, owner_context

router = APIRouter(prefix="/api/audio")
logger = logging.getLogger(__name__)

SECRET_SECONDS = 120
# Words the legal conversations hinge on; supported as hints by gpt(-live)-transcribe.
KEYWORDS = [
    "FIR",
    "bail",
    "BNSS",
    "DLSA",
    "legal aid",
    "consumer commission",
    "refund",
    "landlord",
    "security deposit",
    "salary",
    "Labour Commissioner",
    "grievance officer",
    "advocate",
    "thana",
    "Bihar",
    "Patna",
]


def transcription_session(settings) -> dict[str, Any]:
    """Transcription-only session tuned for latency: short VAD pauses, fastest delay."""
    model = settings.openai_live_transcription_model
    transcription: dict[str, Any] = {"model": model}
    if model == "gpt-realtime-whisper":
        transcription["delay"] = settings.live_transcription_delay
    if model in {"gpt-transcribe", "gpt-live-transcribe"}:
        transcription.update(languages=["en", "hi"], keywords=KEYWORDS)
    return {
        "type": "transcription",
        "audio": {
            "input": {
                "noise_reduction": {"type": "near_field"},
                "transcription": transcription,
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": 300,
                    "prefix_padding_ms": 200,
                },
            }
        },
    }


@router.get("/live-session")
def live_session(
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    cfg = live_settings(request)
    if not cfg.ai_configured:
        raise HTTPException(status_code=503, detail="OpenAI configuration required for voice")
    _check_model_circuit(request, owner, None, cfg)
    # Tests inject a fake client here; production uses the SDK.
    factory = getattr(request.app.state, "voice_client_factory", None) or OpenAI
    try:
        with factory(api_key=cfg.openai_api_key, timeout=15, max_retries=1) as client:
            secret = client.realtime.client_secrets.create(
                expires_after={"anchor": "created_at", "seconds": SECRET_SECONDS},
                session=transcription_session(cfg),
            )
    except Exception as exc:
        logger.warning("Live transcription secret failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Live transcription is unavailable") from None
    abuse = getattr(request.app.state, "abuse", None)
    if abuse is not None:
        abuse.record_turn_usage(owner.owner_id, 1)
    return {
        "client_secret": secret.value,
        "expires_at": secret.expires_at,
        "model": cfg.openai_live_transcription_model,
        "max_seconds": cfg.voice_max_seconds,
    }
