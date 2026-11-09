"""A user's own OpenAI key, usable only while their browser supplies its unlock secret.

The browser makes a random 32-byte unlock secret and keeps it; the server stores only the key
sealed with that secret (plus its last 4 characters for display). Each request carries the secret
in the ``X-Nyay-Key-Unlock`` header; the middleware opens the key in memory for that request and
nothing else. Without the browser's secret the stored value can't be opened, not even with
KMS_MASTER_KEY, so the database and its backups hold no usable keys.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from http.cookies import CookieError, SimpleCookie

from app.security.privacy import aead_decrypt, aead_encrypt

UNLOCK_HEADER = "X-Nyay-Key-Unlock"
_REQUEST_KEY: ContextVar[str | None] = ContextVar("nyay_user_openai_key", default=None)


def current_user_key() -> str | None:
    """The requesting user's opened key; tasks and copied contexts started by the request see it."""
    return _REQUEST_KEY.get()


@contextmanager
def using_user_key(api_key: str | None) -> Iterator[None]:
    token = _REQUEST_KEY.set(api_key)
    try:
        yield
    finally:
        _REQUEST_KEY.reset(token)


def parse_unlock(value: str | None) -> bytes | None:
    """The 32-byte secret from its base64url header form, or None when absent or malformed."""
    if not value or len(value) > 64:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == 32 else None


def _sealing_key(unlock: bytes) -> bytes:
    return hashlib.sha256(b"nyay-user-openai-key-v1|" + unlock).digest()


def _bound_to(owner_id: str) -> bytes:
    # A sealed key copied to another owner's row fails to open.
    return f"owner-api-key|{owner_id}".encode()


def seal_key(api_key: str, unlock: bytes, owner_id: str) -> str:
    return aead_encrypt(_sealing_key(unlock), api_key.encode("utf-8"), _bound_to(owner_id))


def open_key(sealed: str, unlock: bytes, owner_id: str) -> str | None:
    try:
        return aead_decrypt(_sealing_key(unlock), sealed, _bound_to(owner_id)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def key_hint(api_key: str) -> str:
    return api_key.strip()[-4:]


class UserKeyMiddleware:
    """Opens the requesting device's key for the length of the request (pure ASGI, so the value
    reaches the endpoint, its streamed body and any task it starts)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        api_key = self._open_for(scope) if scope["type"] == "http" else None
        if not api_key:
            await self.app(scope, receive, send)
            return
        with using_user_key(api_key):
            await self.app(scope, receive, send)

    @staticmethod
    def _open_for(scope) -> str | None:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        unlock = parse_unlock(headers.get(UNLOCK_HEADER.lower()))
        if not unlock:
            return None
        from app.security.ownership import OWNER_COOKIE, existing_owner_id

        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("cookie", ""))
        except CookieError:
            return None
        morsel = cookies.get(OWNER_COOKIE)
        state = scope["app"].state
        owner_id = existing_owner_id(state.db, state.settings, morsel.value if morsel else None)
        sealed = state.db.sealed_api_key(owner_id) if owner_id else None
        return open_key(sealed["sealed_key"], unlock, owner_id) if sealed else None
