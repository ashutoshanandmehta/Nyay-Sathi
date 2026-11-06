import json
import os
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.models import CaseMemory

STANDARD_LAWYER_QUESTIONS = [
    "Is this the appropriate forum?",
    "What facts or documents are still missing?",
    "Are there timing issues?",
    "What remedies are realistically available?",
    "What are the likely costs and stages?",
    "Is settlement worth exploring?",
    "What work will the lawyer's fee cover?",
]


def _lawyer_brief(
    memory: CaseMemory,
    summary: str,
    attachments: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    facts = memory.facts
    questions = list(dict.fromkeys(memory.questions_for_legal_review + STANDARD_LAWYER_QUESTIONS))
    evidence_by_id = {
        str(item.get("id")): {
            "document_id": item.get("id"),
            "document_name": item.get("filename"),
            "extraction_status": item.get("extraction_status"),
            "relevant_page_or_span": None,
            "may_support": [],
            "note": "No evidential conclusion is inferred from upload alone.",
        }
        for item in attachments
    }
    unlinked_evidence: list[dict[str, Any]] = []
    for item in memory.evidence:
        document_id = str(item.get("document_id") or "")
        if document_id and document_id in evidence_by_id:
            evidence_by_id[document_id].update(item)
        else:
            unlinked_evidence.append(item)
    evidence_index = list(evidence_by_id.values()) + unlinked_evidence
    return {
        "overview": {
            "summary": summary,
            "parties": memory.parties,
            "locations": memory.locations,
            "issue": facts.get("issue_type").value if facts.get("issue_type") else None,
            "amount": facts.get("amount").value if facts.get("amount") else None,
            "objective": memory.requested_remedy,
            "current_stage": facts.get("current_stage").value
            if facts.get("current_stage")
            else None,
        },
        "chronology": memory.events,
        "evidence_index": evidence_index,
        "disputed_facts_and_gaps": memory.contradictions
        + [{"description": item, "type": "unknown"} for item in memory.unknowns],
        "correspondence_history": memory.correspondence_history,
        "actions_completed": memory.actions_completed,
        "responses_received": memory.responses_received,
        "possible_legal_issues_for_review": memory.legal_issues_for_review,
        "urgent_matters": memory.urgent_matters,
        "questions_for_lawyer": questions,
        "sources": sources,
        "draft_status": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "version": item.get("version"),
                "status": item.get("status"),
                "case_version": item.get("case_version"),
            }
            for item in drafts
        ],
    }


def export_payload(
    conversation: dict[str, Any],
    memory: CaseMemory,
    summary: str,
    messages: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    for message in messages:
        for source in message.get("metadata", {}).get("sources", []):
            key = (str(source.get("source_id")), str(source.get("passage_id")))
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(source)
    lawyer_brief = _lawyer_brief(memory, summary, attachments, drafts, sources)
    return {
        "format_version": "1.0",
        "product": "Nyay Saathi",
        "disclaimer": "AI legal-information and preparation assistant; not a licensed advocate or legal representation.",
        "conversation": {
            k: conversation[k] for k in ("id", "title", "language", "created_at", "updated_at")
        },
        "case_version": memory.version,
        "summary": summary,
        "case_memory": memory.model_dump(mode="json"),
        "evidence": [
            {k: a.get(k) for k in ("id", "filename", "mime_type", "extraction_status")}
            for a in attachments
        ],
        "drafts": [
            {k: d.get(k) for k in ("id", "title", "content", "version", "status", "case_version")}
            for d in drafts
        ],
        "messages": [
            {k: m.get(k) for k in ("id", "role", "content", "created_at")} for m in messages
        ],
        "sources": sources,
        "lawyer_brief": lawyer_brief,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _unicode_font() -> str:
    candidates = [
        os.environ.get("NYAY_DEVANAGARI_FONT"),
        str(Path(__file__).parents[1] / "assets" / "NotoSansDevanagari-Regular.ttf"),
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont("NyayUnicode", candidate, shapable=True))
                return "NyayUnicode"
            except Exception:
                continue
    return "Helvetica"


def write_docx(path: Path, payload: dict[str, Any]) -> None:
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(0.75)
    section.left_margin = section.right_margin = Inches(0.85)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(10.5)
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        doc.styles[style_name].font.color.rgb = __import__("docx").shared.RGBColor(0, 0, 0)
    title_properties = doc.styles["Title"]._element.get_or_add_pPr()
    title_border = title_properties.find(qn("w:pBdr"))
    if title_border is not None:
        title_properties.remove(title_border)
    title = doc.add_paragraph(style="Title")
    title.add_run("Nyay Saathi Case Pack")
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph(
        f"Case: {payload['conversation']['title']}  |  Version: {payload['case_version']}"
    )
    doc.add_paragraph(
        "This pack organises information supplied by the user. It is not legal representation, a filing, or proof of the underlying allegations."
    )
    doc.add_heading("One-page overview", level=1)
    doc.add_paragraph(payload.get("summary") or "No summary is available yet.")
    memory = payload["case_memory"]
    overview = payload["lawyer_brief"]["overview"]
    overview_table = doc.add_table(rows=0, cols=2)
    overview_table.style = "Table Grid"
    for label, value in (
        ("Parties", overview.get("parties")),
        ("Locations", overview.get("locations")),
        ("Issue", overview.get("issue")),
        ("Amount", overview.get("amount")),
        ("Objective", overview.get("objective")),
        ("Current stage", overview.get("current_stage")),
    ):
        cells = overview_table.add_row().cells
        cells[0].text = label
        cells[1].text = str(value) if value else "Not confirmed yet."
    doc.add_heading("Requested remedy", level=1)
    doc.add_paragraph(memory.get("requested_remedy") or "Not confirmed yet.")
    doc.add_heading("Facts and provenance", level=1)
    facts = memory.get("facts", {})
    if facts:
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        headers = ["Fact", "Value", "Status", "Source"]
        for i, label in enumerate(headers):
            table.rows[0].cells[i].text = label
            _set_cell_shading(table.rows[0].cells[i], "D9EAF7")
        for key, fact in facts.items():
            cells = table.add_row().cells
            cells[0].text, cells[1].text, cells[2].text = key, str(fact["value"]), fact["status"]
            cells[3].text = ", ".join(p["source_id"] for p in fact.get("provenance", []))
    else:
        doc.add_paragraph("No structured facts recorded.")
    doc.add_heading("Timeline", level=1)
    for event in memory.get("events", []):
        doc.add_paragraph(str(event), style="List Bullet")
    if not memory.get("events"):
        doc.add_paragraph("No confirmed timeline entries yet.")
    doc.add_heading("Evidence index", level=1)
    for item in payload["lawyer_brief"]["evidence_index"]:
        doc.add_paragraph(
            f"☐ {item.get('document_name') or item.get('name') or item.get('document_id')} — "
            f"extraction: {item.get('extraction_status', 'not recorded')} — "
            f"may support: {', '.join(item.get('may_support', [])) or 'requires review'}",
            style="List Bullet",
        )
    if not payload["lawyer_brief"]["evidence_index"]:
        doc.add_paragraph("No evidence uploaded.")
    doc.add_heading("Open questions and contradictions", level=1)
    for item in memory.get("unknowns", []):
        doc.add_paragraph(item, style="List Bullet")
    for item in memory.get("contradictions", []):
        doc.add_paragraph(item.get("description", str(item)), style="List Bullet")
    if not memory.get("unknowns") and not memory.get("contradictions"):
        doc.add_paragraph("None recorded.")
    doc.add_heading("Correspondence and responses", level=1)
    correspondence = payload["lawyer_brief"]["correspondence_history"]
    responses = payload["lawyer_brief"]["responses_received"]
    for item in correspondence:
        doc.add_paragraph(str(item), style="List Bullet")
    for item in responses:
        doc.add_paragraph(f"Response: {item}", style="List Bullet")
    if not correspondence and not responses:
        doc.add_paragraph("None recorded.")
    doc.add_heading("Possible legal issues for qualified review", level=1)
    for item in payload["lawyer_brief"]["possible_legal_issues_for_review"]:
        doc.add_paragraph(item, style="List Bullet")
    if not payload["lawyer_brief"]["possible_legal_issues_for_review"]:
        doc.add_paragraph("No issue has been recorded for qualified legal review yet.")
    doc.add_heading("Urgent matters", level=1)
    for item in payload["lawyer_brief"]["urgent_matters"]:
        doc.add_paragraph(str(item), style="List Bullet")
    if not payload["lawyer_brief"]["urgent_matters"]:
        doc.add_paragraph("None recorded. This is not a deadline calculation.")
    doc.add_heading("Questions for the lawyer", level=1)
    for item in payload["lawyer_brief"]["questions_for_lawyer"]:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Drafts", level=1)
    for draft in payload.get("drafts", []):
        doc.add_heading(draft["title"], level=2)
        doc.add_paragraph(
            f"Status: {draft['status']} | Draft version: {draft['version']} | Case version: {draft['case_version']}"
        )
        doc.add_paragraph(draft["content"])
    if not payload.get("drafts"):
        doc.add_paragraph("No drafts created.")
    sources_heading = doc.add_heading("Sources", level=1)
    sources_heading.paragraph_format.keep_with_next = False
    for source in payload.get("sources", []):
        source_paragraph = doc.add_paragraph(
            f"{source.get('title')} - {source.get('locator')}\n{source.get('canonical_url')}"
        )
        source_paragraph.paragraph_format.keep_together = False
        source_paragraph.paragraph_format.keep_with_next = False
        for run in source_paragraph.runs:
            run.font.size = Pt(9)
    if not payload.get("sources"):
        doc.add_paragraph("No legal sources were linked to an answer in this case.")
    doc.save(path)


def write_pdf(path: Path, payload: dict[str, Any]) -> None:
    styles = getSampleStyleSheet()
    font_name = _unicode_font()
    for style_name in ("Title", "Heading1", "Heading2", "BodyText", "Normal", "Italic"):
        styles[style_name].fontName = font_name

    def paragraph(value: Any, style: str = "BodyText") -> Paragraph:
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    story = [
        paragraph("Nyay Saathi Case Brief", "Title"),
        Spacer(1, 5 * mm),
        paragraph(
            f"Case: {payload['conversation']['title']} | Version: {payload['case_version']}",
            "Normal",
        ),
        Spacer(1, 3 * mm),
        paragraph(
            "This is an AI-organised factual brief, not legal representation or proof of allegations.",
            "Italic",
        ),
        Spacer(1, 6 * mm),
        paragraph("One-page overview", "Heading1"),
        paragraph(payload.get("summary") or "No summary available."),
    ]
    facts = payload["case_memory"].get("facts", {})
    story += [Spacer(1, 4 * mm), paragraph("Requested remedy", "Heading1")]
    story.append(paragraph(payload["case_memory"].get("requested_remedy") or "Not confirmed yet."))
    story += [Spacer(1, 4 * mm), paragraph("Facts", "Heading1")]
    rows = [[paragraph("Fact"), paragraph("Value"), paragraph("Status")]] + [
        [paragraph(k), paragraph(v["value"]), paragraph(v["status"])] for k, v in facts.items()
    ]
    table = Table(rows, colWidths=[45 * mm, 85 * mm, 42 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), "#D9EAF7"),
                ("GRID", (0, 0), (-1, -1), 0.5, "#D9D9D9"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story += [Spacer(1, 5 * mm), paragraph("Evidence", "Heading1")]
    for item in payload.get("evidence", []):
        story.append(paragraph(f"• {item['filename']} - {item['extraction_status']}"))
    if not payload.get("evidence"):
        story.append(paragraph("No evidence uploaded."))
    story += [Spacer(1, 5 * mm), paragraph("Open questions and contradictions", "Heading1")]
    entries = payload["case_memory"].get("unknowns", []) + [
        x.get("description", str(x)) for x in payload["case_memory"].get("contradictions", [])
    ]
    for entry in entries or ["None recorded."]:
        story.append(paragraph(f"• {entry}"))
    story += [Spacer(1, 5 * mm), paragraph("Correspondence and responses", "Heading1")]
    correspondence = payload["lawyer_brief"]["correspondence_history"]
    responses = payload["lawyer_brief"]["responses_received"]
    for item in correspondence:
        story.append(paragraph(f"• {item}"))
    for item in responses:
        story.append(paragraph(f"• Response: {item}"))
    if not correspondence and not responses:
        story.append(paragraph("None recorded."))
    story += [
        Spacer(1, 5 * mm),
        paragraph("Possible legal issues for qualified review", "Heading1"),
    ]
    issues = payload["lawyer_brief"]["possible_legal_issues_for_review"]
    for item in issues or ["No issue has been recorded for qualified legal review yet."]:
        story.append(paragraph(f"• {item}"))
    story += [Spacer(1, 5 * mm), paragraph("Urgent matters", "Heading1")]
    urgent = payload["lawyer_brief"]["urgent_matters"]
    for item in urgent or ["None recorded. This is not a deadline calculation."]:
        story.append(paragraph(f"• {item}"))
    story += [Spacer(1, 5 * mm), paragraph("Questions for the lawyer", "Heading1")]
    for item in payload["lawyer_brief"]["questions_for_lawyer"]:
        story.append(paragraph(f"• {item}"))
    story += [Spacer(1, 5 * mm), paragraph("Drafts", "Heading1")]
    for draft in payload.get("drafts", []):
        story.append(paragraph(draft["title"], "Heading2"))
        story.append(
            paragraph(
                f"Status: {draft['status']} | Draft version: {draft['version']} | "
                f"Case version: {draft['case_version']}"
            )
        )
        story.append(paragraph(draft["content"]))
    if not payload.get("drafts"):
        story.append(paragraph("No drafts created."))
    story += [Spacer(1, 5 * mm), paragraph("Sources", "Heading1")]
    for source in payload.get("sources", []):
        story.append(
            paragraph(
                f"{source.get('title')} - {source.get('locator')} - {source.get('canonical_url')}"
            )
        )
    if not payload.get("sources"):
        story.append(paragraph("No legal sources were linked to an answer in this case."))
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Nyay Saathi Case Brief",
    )
    doc.build(story)
