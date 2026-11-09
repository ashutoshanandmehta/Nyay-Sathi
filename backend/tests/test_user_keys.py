"""Each user's own OpenAI key, sealed with a secret only their browser holds.

Offline: fake OpenAI clients, no network. Checks that the key works only with the browser's
unlock secret, never mixes between users, never outlives its request, and never appears in a
response, log or the database file.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
from contextvars import copy_context
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AuthenticationError

from app.security.user_key import (
    UNLOCK_HEADER,
    current_user_key,
    open_key,
    parse_unlock,
    seal_key,
    using_user_key,
)

KEY_A = "sk-proj-userA0000000000000000000000aaaa"
KEY_B = "sk-proj-userB0000000000000000000000bbbb"


def new_unlock() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


class Recorder:
    """Fake OpenAI client factory: records which key each client was built with."""

    def __init__(self, reject=()):
        self.keys, self.reject = [], set(reject)

    def __call__(self, **kwargs):
        recorder, api_key = self, kwargs["api_key"]
        recorder.keys.append(api_key)

        def models_list():
            if api_key in recorder.reject:
                response = httpx.Response(401, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
                raise AuthenticationError(f"Incorrect API key provided: {api_key}", response=response, body=None)
            return []

        secrets = SimpleNamespace(create=lambda **_: SimpleNamespace(value="ek_x", expires_at=1, session={}))
        client = SimpleNamespace(models=SimpleNamespace(list=models_list), realtime=SimpleNamespace(client_secrets=secrets))
        client.__enter__ = lambda *a: client
        return _Ctx(client)


class _Ctx:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fakes(isolated_app):
    checks, voice = Recorder(reject={"sk-proj-rejected000000000000000000zzzz"}), Recorder()
    isolated_app.state.user_key_client_factory = checks
    isolated_app.state.voice_client_factory = voice
    yield checks, voice
    del isolated_app.state.user_key_client_factory
    del isolated_app.state.voice_client_factory


def device(isolated_app) -> TestClient:
    client = TestClient(isolated_app)
    client.get("/api/bootstrap")
    client.headers.update({"X-CSRF-Token": client.cookies.get("nyay_csrf")})
    return client


def save(client, api_key, unlock):
    return client.put("/api/me/openai-key", json={"api_key": api_key}, headers={UNLOCK_HEADER: unlock})


# --- sealing -------------------------------------------------------------------------------------


def test_a_sealed_key_opens_only_with_its_secret_and_its_owner():
    unlock = parse_unlock(new_unlock())
    sealed = seal_key(KEY_A, unlock, "owner-1")
    assert KEY_A not in sealed
    assert open_key(sealed, unlock, "owner-1") == KEY_A
    assert open_key(sealed, parse_unlock(new_unlock()), "owner-1") is None  # another browser
    assert open_key(sealed, unlock, "owner-2") is None  # row copied to another owner


@pytest.mark.parametrize("value", [None, "", "short", "a" * 80, base64.urlsafe_b64encode(os.urandom(16)).decode()])
def test_malformed_unlock_secrets_are_ignored(value):
    assert parse_unlock(value) is None


# --- saving --------------------------------------------------------------------------------------


def test_saving_needs_the_browser_secret_and_a_key_openai_accepts(isolated_app, fakes):
    client = device(isolated_app)
    assert client.put("/api/me/openai-key", json={"api_key": KEY_A}).status_code == 400  # no secret
    assert save(client, "not-a-key-at-all-0000000000", new_unlock()).status_code == 400
    rejected = save(client, "sk-proj-rejected000000000000000000zzzz", new_unlock())
    assert rejected.status_code == 400
    assert "zzzz" not in rejected.text  # provider error text never echoed
    assert client.get("/api/me/openai-key").json()["stored"] is False


def test_the_database_holds_only_ciphertext_and_the_last_four(isolated_app, fakes):
    client, unlock = device(isolated_app), new_unlock()
    saved = save(client, KEY_A, unlock)
    assert saved.status_code == 200
    assert saved.json() == {"stored": True, "unlocked": True, "hint": "aaaa", "server_key": False}
    assert KEY_A.encode() not in isolated_app.state.settings.database_path.read_bytes()
    assert KEY_A not in saved.text


def test_the_key_is_usable_only_while_this_browser_sends_its_secret(isolated_app, fakes):
    _, voice = fakes
    client, unlock = device(isolated_app), new_unlock()
    save(client, KEY_A, unlock)

    status = client.get("/api/me/openai-key", headers={UNLOCK_HEADER: unlock}).json()
    assert status["unlocked"] is True and status["hint"] == "aaaa"
    assert client.get("/api/bootstrap", headers={UNLOCK_HEADER: unlock}).json()["ai_configured"] is True
    assert client.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock}).status_code == 200
    assert voice.keys == [KEY_A]

    # Same device without the secret, or with another browser's secret: no key at all.
    assert client.get("/api/bootstrap").json()["ai_configured"] is False
    assert client.get("/api/audio/live-session", headers={UNLOCK_HEADER: new_unlock()}).status_code == 503
    assert client.get("/api/me/openai-key").json() == {"stored": True, "unlocked": False, "hint": "aaaa", "server_key": False}


def test_two_users_never_share_a_key(isolated_app, fakes):
    _, voice = fakes
    a, b = device(isolated_app), device(isolated_app)
    unlock_a, unlock_b = new_unlock(), new_unlock()
    save(a, KEY_A, unlock_a)
    save(b, KEY_B, unlock_b)

    a.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock_a})
    b.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock_b})
    # B presenting A's secret opens nothing: B's key needs B's secret, A's key is sealed to A.
    assert b.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock_a}).status_code == 503
    assert voice.keys == [KEY_A, KEY_B]


def test_a_user_key_wins_over_the_server_key_and_the_server_key_is_the_fallback(isolated_app, fakes):
    _, voice = fakes
    isolated_app.state.settings = isolated_app.state.settings.model_copy(update={"openai_api_key": "sk-server-key-000000000000"})
    with_key, without = device(isolated_app), device(isolated_app)
    unlock = new_unlock()
    save(with_key, KEY_A, unlock)
    with_key.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock})
    without.get("/api/audio/live-session")
    assert voice.keys == [KEY_A, "sk-server-key-000000000000"]


def test_removing_the_key_stops_it_working(isolated_app, fakes):
    client, unlock = device(isolated_app), new_unlock()
    save(client, KEY_A, unlock)
    assert client.delete("/api/me/openai-key").json()["stored"] is False
    assert client.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock}).status_code == 503


def test_key_checks_are_rate_limited_per_device(isolated_app, fakes):
    client = device(isolated_app)
    codes = [save(client, "sk-proj-rejected000000000000000000zzzz", new_unlock()).status_code for _ in range(6)]
    assert codes == [400] * 5 + [429]


def test_the_key_never_reaches_the_logs(isolated_app, fakes, caplog):
    client, unlock = device(isolated_app), new_unlock()
    with caplog.at_level(logging.DEBUG):
        save(client, KEY_A, unlock)
        save(client, "sk-proj-rejected000000000000000000zzzz", new_unlock())
        client.get("/api/audio/live-session", headers={UNLOCK_HEADER: unlock})
    assert KEY_A not in caplog.text and "zzzz" not in caplog.text and unlock not in caplog.text


# --- scope ---------------------------------------------------------------------------------------


def test_work_started_by_a_request_keeps_its_key_and_nothing_else_sees_it():
    seen = {}

    async def turn():
        await asyncio.sleep(0)
        seen["task"] = current_user_key()

    async def main():
        with using_user_key(KEY_A):
            task = asyncio.create_task(turn())  # how a streamed turn runs
            ctx = copy_context()  # how research hands work to its thread pool
        await task
        thread = threading.Thread(target=lambda: seen.__setitem__("thread", ctx.run(current_user_key)))
        thread.start()
        thread.join()
        seen["after"] = current_user_key()

    asyncio.run(main())
    assert seen == {"task": KEY_A, "thread": KEY_A, "after": None}
