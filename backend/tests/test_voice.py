"""Live voice: the ephemeral Realtime secret endpoint (fake SDK client, no network)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.api.voice import KEYWORDS, transcription_session
from app.config import Settings

SECRET = "ek_fixture_secret_value"


class FakeSecrets:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(value=SECRET, expires_at=1_900_000_000, session={})


@pytest.fixture
def voice(client, isolated_app):
    secrets = FakeSecrets()

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.realtime = SimpleNamespace(client_secrets=secrets)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    isolated_app.state.voice_client_factory = Client
    isolated_app.state.settings = isolated_app.state.settings.model_copy(
        update={"openai_api_key": "fixture-not-real"}
    )
    yield client, secrets
    del isolated_app.state.voice_client_factory


def test_secret_is_minted_for_a_transcription_only_session(voice, caplog):
    client, secrets = voice
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/audio/live-session")
    assert response.status_code == 200
    assert response.json() == {
        "client_secret": SECRET,
        "expires_at": 1_900_000_000,
        "model": "gpt-realtime-whisper",
        "max_seconds": 180,
    }
    sent = secrets.calls[0]
    assert sent["expires_after"] == {"anchor": "created_at", "seconds": 120}
    session = sent["session"]
    assert session["type"] == "transcription"
    audio = session["audio"]["input"]
    assert audio["transcription"] == {"model": "gpt-realtime-whisper", "delay": "minimal"}
    assert audio["turn_detection"]["silence_duration_ms"] == 300
    assert SECRET not in caplog.text


def test_live_transcribe_model_gets_language_and_keyword_hints():
    settings = Settings(openai_live_transcription_model="gpt-live-transcribe")
    transcription = transcription_session(settings)["audio"]["input"]["transcription"]
    assert transcription == {
        "model": "gpt-live-transcribe",
        "languages": ["en", "hi"],
        "keywords": KEYWORDS,
    }


def test_minting_counts_against_usage_limits(voice, isolated_app, monkeypatch):
    client, _ = voice
    recorded = []
    monkeypatch.setattr(
        isolated_app.state.abuse, "record_turn_usage", lambda *a: recorded.append(a)
    )
    client.get("/api/audio/live-session")
    assert len(recorded) == 1 and recorded[0][1] == 1

    monkeypatch.setattr(
        isolated_app.state.abuse,
        "check_circuit_breaker",
        lambda *a, **k: (False, "device_model_call_circuit_open"),
    )
    assert client.get("/api/audio/live-session").status_code == 503


def test_no_key_and_provider_errors_are_reported(voice, isolated_app):
    client, secrets = voice
    secrets.error = RuntimeError("upstream down")
    assert client.get("/api/audio/live-session").status_code == 502

    isolated_app.state.settings = isolated_app.state.settings.model_copy(
        update={"openai_api_key": None}
    )
    assert client.get("/api/audio/live-session").status_code == 503
