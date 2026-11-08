"""DevSpace: own key, models and .env settings, written to a temporary .env only."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.api.devspace import API_KEY, EDITABLE, write_env

FULL_KEY = "sk-proj-fixture0000000000000000tnIA"
ENV_TEXT = """# Nyay Saathi local settings
OPENAI_API_KEY=sk-old-fixture-key-0000000000

# Models
OPENAI_CHAT_MODEL=gpt-6-luna
AGENT_MAX_REQUESTS=14
"""


@pytest.fixture
def devspace(client, isolated_app, tmp_path, monkeypatch):
    """A client whose DevSpace writes to a temporary .env; environment restored afterwards."""
    env = tmp_path / ".env"
    env.write_text(ENV_TEXT)
    isolated_app.state.env_path = env
    monkeypatch.setenv(API_KEY, "")
    for name in EDITABLE:
        monkeypatch.delenv(name, raising=False)
    yield client, env
    del isolated_app.state.env_path


def test_get_masks_the_key_and_describes_fields(devspace, isolated_app):
    client, _ = devspace
    isolated_app.state.settings = isolated_app.state.settings.model_copy(
        update={"openai_api_key": FULL_KEY}
    )
    response = client.get("/api/system/devspace")
    assert response.status_code == 200
    assert FULL_KEY not in response.text
    data = response.json()
    assert data["api_key"] == {"configured": True, "masked": "sk-proj…tnIA"}

    fields = {f["name"]: f for g in data["groups"] for f in g["fields"]}
    assert set(fields) == EDITABLE
    assert fields["AGENT_MAX_REQUESTS"] | {"value": None} == {
        "name": "AGENT_MAX_REQUESTS",
        "value": None,
        "restart_required": False,
        "type": "integer",
        "min": 1,
        "max": 24,
    }
    assert fields["COOKIE_SECURE"]["type"] == "boolean"
    assert fields["ASSISTANT_ENGINE"]["options"] == ["primary_agent", "legacy"]
    assert fields["APP_ORIGIN"]["restart_required"] is True
    chat = fields["OPENAI_CHAT_MODEL"]
    assert chat["type"] == "model" and chat["value"] in chat["options"]
    assert fields["PRACTICE_REASONING_EFFORT"]["options"][0] == ""

    primary = (Path(__file__).parents[1] / "app" / "prompts" / "primary.md").read_text()
    assert data["prompts"]["primary"] == primary
    assert "You design a realistic character" in data["prompts"]["roleplay_persona"]
    assert '"Authorization: Bearer $OPENAI_API_KEY"' in data["curl"]["responses_api"]
    assert "/turns/stream" in data["curl"]["turn_stream"]
    assert "/roleplay/chat/stream" in data["curl"]["roleplay_chat"]


def test_save_updates_lines_in_place_and_reloads_the_runtime(devspace, isolated_app):
    client, env = devspace
    old_graph = isolated_app.state.assistant_graph
    response = client.post(
        "/api/system/devspace",
        json={
            "updates": {
                "OPENAI_CHAT_MODEL": "gpt-4o",
                "AGENT_MAX_ROUNDS": "6",
                API_KEY: "sk-proj…tnIA",  # the masked value: keep the saved key
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "saved": ["OPENAI_CHAT_MODEL", "AGENT_MAX_ROUNDS"],
        "restart_required": [],
        "configured": False,
    }
    lines = env.read_text().splitlines()
    assert lines[:5] == [
        "# Nyay Saathi local settings",
        "OPENAI_API_KEY=sk-old-fixture-key-0000000000",
        "",
        "# Models",
        "OPENAI_CHAT_MODEL=gpt-4o",
    ]
    assert lines[-1] == "AGENT_MAX_ROUNDS=6"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600

    state = isolated_app.state
    assert state.settings.openai_chat_model == "gpt-4o" and state.settings.agent_max_rounds == 6
    assert state.assistant_graph is not old_graph
    assert state.assistant_graph.settings.openai_chat_model == "gpt-4o"
    assert os.environ["OPENAI_CHAT_MODEL"] == "gpt-4o"


def test_a_new_key_is_saved_and_can_be_removed(devspace, isolated_app):
    client, env = devspace
    saved = client.post("/api/system/devspace", json={"updates": {API_KEY: f"  {FULL_KEY} "}})
    assert saved.json()["configured"] is True and FULL_KEY not in saved.text
    assert f"OPENAI_API_KEY={FULL_KEY}" in env.read_text().splitlines()
    assert isolated_app.state.settings.openai_api_key == FULL_KEY

    cleared = client.post("/api/system/devspace", json={"clear_api_key": True})
    assert cleared.json() == {"saved": [API_KEY], "restart_required": [], "configured": False}
    assert "OPENAI_API_KEY" not in env.read_text()
    assert os.environ[API_KEY] == ""


def test_invalid_values_are_rejected_and_nothing_is_written(devspace):
    client, env = devspace
    response = client.post("/api/system/devspace", json={"updates": {"AGENT_MAX_REQUESTS": 99}})
    assert response.status_code == 422
    assert "AGENT_MAX_REQUESTS" in response.json()["detail"]["errors"]
    assert env.read_text() == ENV_TEXT


def test_settings_outside_devspace_cannot_be_changed(devspace):
    client, env = devspace
    response = client.post("/api/system/devspace", json={"updates": {"DATABASE_PATH": "/tmp/x"}})
    assert response.status_code == 400
    assert env.read_text() == ENV_TEXT


def test_saving_needs_the_csrf_token(devspace):
    client, env = devspace
    response = client.post(
        "/api/system/devspace",
        json={"updates": {"OPENAI_CHAT_MODEL": "gpt-4o"}},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403 and env.read_text() == ENV_TEXT


def test_devspace_can_be_switched_off(devspace, isolated_app):
    client, env = devspace
    isolated_app.state.settings = isolated_app.state.settings.model_copy(
        update={"devspace_enabled": False}
    )
    assert client.get("/api/system/devspace").status_code == 404
    assert client.post("/api/system/devspace", json={"updates": {}}).status_code == 404
    assert client.get("/api/bootstrap").json()["devspace_enabled"] is False
    assert env.read_text() == ENV_TEXT


def test_write_env_replaces_duplicates_and_quotes_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("export A=1\nB=2\nA=3\n")
    write_env(env, {"A": "9", "B": None, "C": '"two words"'})
    assert env.read_text() == 'A=9\nC="two words"\n'
