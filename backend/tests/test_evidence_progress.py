"""Deterministic synthetic tests; no model output is represented as live."""

import json

import fitz

from app.services.documents import extract_document
from app.services.evidence import EvidenceSearchService
from app.services.review_policy import ReviewPolicy

from .conftest import create_case


def test_search_finds_invoice_on_late_page_with_provenance():
    doc = fitz.open()
    for i in range(8):
        page = doc.new_page()
        page.insert_text(
            (60, 60),
            "Order colour: blue; received colour: red"
            if i == 7
            else "Terms and conditions of purchase " * 6,
        )
    text, status, metadata = extract_document(doc.tobytes(), "application/pdf", 50)
    doc.close()
    hits = EvidenceSearchService().search(
        "order colour blue red",
        [
            {
                "id": "invoice",
                "filename": "invoice.pdf",
                "extracted_text": text,
                "extraction_status": status,
                "metadata_json": json.dumps(metadata),
            }
        ],
    )
    assert hits[0]["page"] == 8
    assert text[hits[0]["span"]["start"] : hits[0]["span"]["end"]] == hits[0]["text"]
    assert hits[0]["chunk_id"]


def test_correction_rebuilds_spans_and_invalidates_draft(client):
    cid = create_case(client)
    attachment = client.post(
        f"/api/conversations/{cid}/attachments",
        files={"file": ("invoice.txt", b"Original invoice", "text/plain")},
    ).json()
    client.post(
        f"/api/conversations/{cid}/drafts", json={"title": "Request", "content": "Original draft"}
    )
    assert (
        client.patch(
            f"/api/conversations/{cid}/attachments/{attachment['id']}",
            json={"extracted_text": "Corrected amount 2300"},
        ).status_code
        == 200
    )
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["drafts"][0]["status"] == "stale"
    chunks = list(EvidenceSearchService().chunks(detail["attachments"][0]))
    assert chunks[0]["text"] == "Corrected amount 2300"


def test_foreign_case_attachment_is_rejected(client):
    cid, other = create_case(client), create_case(client)
    attachment = client.post(
        f"/api/conversations/{cid}/attachments",
        files={"file": ("invoice.txt", b"private", "text/plain")},
    ).json()
    response = client.post(
        f"/api/conversations/{other}/turns",
        json={
            "content": "Read invoice",
            "request_id": "foreign-request-id",
            "attachment_ids": [attachment["id"]],
        },
    )
    assert response.status_code == 404


def test_stream_has_real_stage_events_and_one_final_result(client):
    cid = create_case(client)
    response = client.post(
        f"/api/conversations/{cid}/turns/stream",
        json={"content": "My refund has not arrived", "request_id": "stream-test"},
    )
    assert response.status_code == 200
    assert '"status": "running"' in response.text
    assert '"duration_ms"' in response.text
    assert response.text.count("event: result") == 1
    assert response.text.index('"stage": "intake"') < response.text.index("event: result")


def test_revision_reserves_an_independent_review():
    assert not ReviewPolicy.may_revise(3, 4, 0)
    assert ReviewPolicy.may_revise(3, 5, 0)
    assert not ReviewPolicy.may_revise(3, 5, 1)
