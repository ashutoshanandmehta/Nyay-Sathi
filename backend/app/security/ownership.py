import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status

from app.config import Settings, get_settings
from app.db import Database

OWNER_COOKIE = "nyay_owner"
CSRF_COOKIE = "nyay_csrf"


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class OwnerContext:
    owner_id: str
    new_owner_token: str | None = None
    new_csrf_token: str | None = None


def owner_context(
    request: Request, owner_cookie: str | None = Cookie(default=None, alias=OWNER_COOKIE)
) -> OwnerContext:
    db: Database = request.app.state.db
    if owner_cookie:
        owner_id = db.owner_for_hash(token_hash(owner_cookie))
        if owner_id:
            return OwnerContext(owner_id)
    raw = secrets.token_urlsafe(32)
    return OwnerContext(db.create_owner(token_hash(raw)), raw, secrets.token_urlsafe(24))


def set_owner_cookies(
    response: Response, owner: OwnerContext, settings: Settings = Depends(get_settings)
) -> None:
    if owner.new_owner_token:
        common = dict(secure=settings.cookie_secure, samesite="lax", path="/", max_age=31_536_000)
        response.set_cookie(OWNER_COOKIE, owner.new_owner_token, httponly=True, **common)
        response.set_cookie(CSRF_COOKIE, owner.new_csrf_token, httponly=False, **common)


def csrf_guard(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
) -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if (
            not csrf_cookie
            or not x_csrf_token
            or not hmac.compare_digest(csrf_cookie, x_csrf_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed"
            )


OwnerDep = Depends(owner_context)
CsrfDep = Depends(csrf_guard)
