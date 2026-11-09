"""Each user's own OpenAI key: save (checked with OpenAI first), see its last 4 characters, remove.

The key is sealed with the browser's unlock secret (``X-Nyay-Key-Unlock``), so this server can
use it only while that browser is making a request. See app/security/user_key.py.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
)
from pydantic import BaseModel, Field

from app.api.routes import db, live_settings
from app.security.ownership import OwnerContext, csrf_guard, owner_context, set_owner_cookies
from app.security.user_key import (
    UNLOCK_HEADER,
    current_user_key,
    key_hint,
    parse_unlock,
    seal_key,
)

router = APIRouter(prefix="/api/me")
logger = logging.getLogger(__name__)

# Key checks per device: enough for typos, not for probing keys.
CHECKS_PER_WINDOW, CHECK_WINDOW_SECONDS = 5, 600
_checks: dict[str, deque] = defaultdict(deque)


class KeyBody(BaseModel):
    api_key: str = Field(min_length=20, max_length=300)


def _status(request: Request, owner_id: str) -> dict:
    stored = db(request).sealed_api_key(owner_id)
    return {
        "stored": bool(stored),
        # Opened for this request means the browser still holds the matching unlock secret.
        "unlocked": bool(stored and current_user_key()),
        "hint": stored["key_hint"] if stored else None,
        "server_key": bool(live_settings(request).openai_api_key),
    }


def _allow_check(owner_id: str) -> bool:
    now = time.monotonic()
    window = _checks[owner_id]
    while window and window[0] < now - CHECK_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= CHECKS_PER_WINDOW:
        return False
    window.append(now)
    return True


@router.get("/openai-key")
def get_key(
    request: Request, response: Response, owner: Annotated[OwnerContext, Depends(owner_context)]
):
    set_owner_cookies(response, owner, live_settings(request))
    return _status(request, owner.owner_id)


@router.put("/openai-key", dependencies=[Depends(csrf_guard)])
def save_key(
    body: KeyBody,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
    unlock_header: Annotated[str | None, Header(alias=UNLOCK_HEADER)] = None,
):
    unlock = parse_unlock(unlock_header)
    if not unlock:
        raise HTTPException(status_code=400, detail="This browser could not create a key lock. Reload and try again.")
    api_key = body.api_key.strip()
    if not api_key.startswith("sk-") or any(c.isspace() for c in api_key):
        raise HTTPException(status_code=400, detail="That doesn't look like an OpenAI API key (it starts with sk-).")
    if not _allow_check(owner.owner_id):
        raise HTTPException(status_code=429, detail="Too many key checks. Wait a few minutes and try again.")
    # Listing models is free; it proves the key works before it is stored. Tests inject a fake.
    factory = getattr(request.app.state, "user_key_client_factory", None) or OpenAI
    try:
        with factory(api_key=api_key, timeout=10, max_retries=0) as client:
            client.models.list()
    except (AuthenticationError, PermissionDeniedError):
        raise HTTPException(status_code=400, detail="OpenAI didn't accept this key. Check it and try again.") from None
    except (APIConnectionError, APITimeoutError):
        raise HTTPException(status_code=502, detail="Couldn't reach OpenAI to check the key. Try again.") from None
    except Exception as exc:
        # Never echo provider text: it can quote part of the key.
        logger.warning("User key check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Couldn't check the key with OpenAI. Try again.") from None
    db(request).save_sealed_api_key(owner.owner_id, seal_key(api_key, unlock, owner.owner_id), key_hint(api_key))
    return {"stored": True, "unlocked": True, "hint": key_hint(api_key), "server_key": bool(live_settings(request).openai_api_key)}


@router.delete("/openai-key", dependencies=[Depends(csrf_guard)])
def delete_key(request: Request, owner: Annotated[OwnerContext, Depends(owner_context)]):
    db(request).delete_sealed_api_key(owner.owner_id)
    return {"stored": False, "unlocked": False, "hint": None, "server_key": bool(live_settings(request).openai_api_key)}
