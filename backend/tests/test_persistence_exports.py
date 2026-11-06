import json

from docx import Document
from pypdf import PdfReader

from app.db import Database
from app.schemas.models import CaseFact, CaseMemory
from app.services.exports import export_payload, write_docx, write_json, write_pdf


def test_database_resume_after_reopen(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    first = Database(path)
    owner = first.create_owner("hash")
    cid = first.create_conversation(owner, "en")["id"]
    first.add_message(cid, "user", "Continue tomorrow", "resume-request")
    second = Database(path)
    assert second.messages(owner, cid)[0]["content"] == "Continue tomorrow"


def test_exports_include_case_version_facts_evidence_and_draft_status(tmp_path):
    memory = CaseMemory(
        version=3,
        facts={"amount": CaseFact(key="amount", value="8000")},
        contradictions=[{"description": "Earlier amount was 18000"}],
        unknowns=["Delivery date"],
        parties=[{"name": "Shop Example", "role": "seller"}],
        requested_remedy="Refund",
        events=[{"date": "2026-10-02", "event": "Refund requested", "source_id": "m1"}],
        questions_for_legal_review=["Does the forum have territorial jurisdiction?"],
        legal_issues_for_review=["Consumer status and appropriate forum"],
    )
    conv = {
        "id": "c1",
        "title": "Defective phone",
        "language": "en",
        "created_at": "now",
        "updated_at": "now",
    }
    attachments = [
        {
            "id": "a1",
            "filename": "invoice.pdf",
            "mime_type": "application/pdf",
            "extraction_status": "complete",
        }
    ]
    drafts = [
        {
            "id": "d1",
            "title": "Seller email",
            "content": "Please refund ₹8,000",
            "version": 2,
            "status": "stale",
            "case_version": 2,
        }
    ]
    payload = export_payload(conv, memory, "Phone dispute", [], attachments, drafts)
    json_path, docx_path, pdf_path = (
        tmp_path / "case.json",
        tmp_path / "case.docx",
        tmp_path / "case.pdf",
    )
    write_json(json_path, payload)
    write_docx(docx_path, payload)
    write_pdf(pdf_path, payload)
    assert json.loads(json_path.read_text())["case_version"] == 3
    exported = json.loads(json_path.read_text())
    assert exported["lawyer_brief"]["overview"]["objective"] == "Refund"
    assert "Is this the appropriate forum?" in exported["lawyer_brief"]["questions_for_lawyer"]
    assert exported["lawyer_brief"]["evidence_index"][0]["note"].startswith("No evidential")
    doc = Document(docx_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Nyay Saathi Case Pack" in text and "Seller email" in text
    assert "Questions for the lawyer" in text
    assert "Possible legal issues for qualified review" in text
    reader = PdfReader(pdf_path)
    assert len(reader.pages) >= 1
    assert "Nyay Saathi Case Brief" in (reader.pages[0].extract_text() or "")
