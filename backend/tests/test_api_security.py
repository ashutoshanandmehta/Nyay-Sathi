from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from .conftest import create_case


def send(client, cid, text, request_id):
    return client.post(
        f"/api/conversations/{cid}/turns",
        json={"content": text, "request_id": request_id, "language": "en", "attachment_ids": []},
    )


def test_first_visitor_can_create_chat_without_login(client):
    cid = create_case(client)
    assert cid
    assert client.get("/api/conversations").json()[0]["id"] == cid


def test_csrf_required(isolated_app):
    other = TestClient(isolated_app)
    other.get("/api/bootstrap")
    assert other.post("/api/conversations", json={"language": "en"}).status_code == 403


def test_different_owner_cannot_access_known_uuid(client, isolated_app):
    cid = create_case(client)
    stranger = TestClient(isolated_app)
    stranger.get("/api/bootstrap")
    assert stranger.get(f"/api/conversations/{cid}").status_code == 404
    assert all(x["id"] != cid for x in stranger.get("/api/conversations").json())


def test_independent_chats_keep_memory_isolated(client):
    first, second = create_case(client), create_case(client)
    assert send(client, first, "Defective phone cost ₹18,000", "request-first").status_code == 200
    assert send(client, second, "Refund of ₹500 is late", "request-second").status_code == 200
    a = client.get(f"/api/conversations/{first}").json()["case_memory"]
    b = client.get(f"/api/conversations/{second}").json()["case_memory"]
    assert a["facts"]["amount"]["value"] == "18000"
    assert b["facts"]["amount"]["value"] == "500"


def test_idempotent_retry_does_not_duplicate_messages(client):
    cid = create_case(client)
    one = send(client, cid, "My refund of ₹900 is late", "same-request")
    two = send(client, cid, "My refund of ₹900 is late", "same-request")
    assert one.status_code == two.status_code == 200
    messages = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert len([m for m in messages if m.get("request_id") == "same-request"]) == 2


def test_failed_turn_retries_same_request_without_duplicate_user(client, isolated_app, monkeypatch):
    cid = create_case(client)
    original = isolated_app.state.assistant_graph.invoke

    def fail_once(*_args, **_kwargs):
        raise RuntimeError("synthetic turn failure")

    monkeypatch.setattr(isolated_app.state.assistant_graph, "invoke", fail_once)
    assert send(client, cid, "My refund is late", "retry-failed-request").status_code == 503
    monkeypatch.setattr(isolated_app.state.assistant_graph, "invoke", original)
    assert send(client, cid, "My refund is late", "retry-failed-request").status_code == 200
    messages = client.get(f"/api/conversations/{cid}").json()["messages"]
    retried = [m for m in messages if m.get("request_id") == "retry-failed-request"]
    assert len(retried) == 2
    assert {m["status"] for m in retried} == {"complete"}


def test_correction_updates_value_history_and_stales_draft(client):
    cid = create_case(client)
    send(client, cid, "Defective phone cost ₹18,000", "correction-one")
    draft = client.post(
        f"/api/conversations/{cid}/drafts", json={"title": "Email", "content": "Refund ₹18,000"}
    )
    assert draft.status_code == 200
    send(client, cid, "Actually, it was ₹8,000", "correction-two")
    detail = client.get(f"/api/conversations/{cid}").json()
    fact = detail["case_memory"]["facts"]["amount"]
    assert fact["value"] == "8000"
    assert fact["previous_values"][0]["value"] == "18000"
    assert detail["drafts"][0]["status"] == "stale"


def test_language_change_preserves_case_memory(client):
    cid = create_case(client)
    send(client, cid, "Defective item cost ₹2,200", "lang-one")
    response = client.post(
        f"/api/conversations/{cid}/turns",
        json={"content": "हिंदी में समझाइए", "request_id": "lang-two", "language": "hi"},
    )
    assert response.status_code == 200
    assert (
        client.get(f"/api/conversations/{cid}").json()["case_memory"]["facts"]["amount"]["value"]
        == "2200"
    )


def test_delete_removes_case_and_checkpoint(client, isolated_app):
    cid = create_case(client)
    send(client, cid, "My refund is late", "delete-request")
    owner_id = isolated_app.state.db.owner_for_hash(
        __import__("hashlib").sha256(client.cookies.get("nyay_owner").encode()).hexdigest()
    )
    thread_id = f"{owner_id}:{cid}"
    assert (
        isolated_app.state.assistant_graph.checkpointer.get(
            {"configurable": {"thread_id": thread_id}}
        )
        is not None
    )
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404
    assert (
        isolated_app.state.assistant_graph.checkpointer.get(
            {"configurable": {"thread_id": thread_id}}
        )
        is None
    )


def test_concurrent_turn_returns_conflict_or_completes_without_corruption(client):
    cid = create_case(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: send(client, cid, *args),
                [("Refund ₹100", "parallel-one"), ("Defective product ₹200", "parallel-two")],
            )
        )
    assert {r.status_code for r in results} <= {200, 409}
    messages = client.get(f"/api/conversations/{cid}").json()["messages"]
    assert len({m["id"] for m in messages}) == len(messages)
