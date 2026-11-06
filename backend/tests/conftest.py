import os
import socket
from pathlib import Path

# Tests must never inherit the developer's real key from .env: importing app.main
# constructs module-level Settings/HybridRetriever, which would otherwise open the
# paid embedding client. Set before any app import.
os.environ["OPENAI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.graph.workflow import AssistantGraph  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.retrieval import HybridRetriever  # noqa: E402
from app.routing.interpretation import OfflineInterpreter  # noqa: E402

_real_connect = socket.socket.connect


def _offline_connect(sock, address):
    """Allow local IPC/loopback only; any outbound connection fails the test."""
    if sock.family == getattr(socket, "AF_UNIX", None):
        return _real_connect(sock, address)
    host = address[0] if isinstance(address, tuple) else address
    if host in {"127.0.0.1", "::1", "localhost"}:
        return _real_connect(sock, address)
    raise AssertionError(f"Outbound network is forbidden in offline tests: {host}")


@pytest.fixture(autouse=True)
def _forbid_outbound_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _offline_connect)
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture
def isolated_app(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "app.sqlite3",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        chroma_path=tmp_path / "chroma",
        upload_path=tmp_path / "uploads",
        export_path=tmp_path / "exports",
        openai_api_key=None,
    )
    settings.ensure_dirs()
    graph = AssistantGraph(settings, HybridRetriever(settings), interpreter=OfflineInterpreter())
    app.state.settings = settings
    app.state.db = Database(settings.database_path)
    app.state.retriever = graph.retriever
    app.state.assistant_graph = graph
    app.state.requests.clear()
    yield app
    graph.connection.close()


@pytest.fixture
def client(isolated_app):
    with TestClient(isolated_app) as value:
        response = value.get("/api/bootstrap")
        assert response.status_code == 200
        value.headers.update({"X-CSRF-Token": value.cookies.get("nyay_csrf")})
        yield value


def create_case(client: TestClient, language: str = "en") -> str:
    response = client.post("/api/conversations", json={"language": language})
    assert response.status_code == 200
    return response.json()["id"]
