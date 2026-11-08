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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
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
                registerFontFamily(
                    "NyayUnicode",
                    normal="NyayUnicode",
                    bold="NyayUnicode",
                    italic="NyayUnicode",
                    boldItalic="NyayUnicode",
                )
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


PRIMARY_COLOR = colors.HexColor("#1b4332")
SECONDARY_COLOR = colors.HexColor("#2d6a4f")
CALLOUT_BG = colors.HexColor("#f4f8f6")
CARD_BG = colors.HexColor("#fcfdfc")
BORDER_LIGHT = colors.HexColor("#d5ded9")
TEXT_DARK = colors.HexColor("#1c2421")
TEXT_MUTED = colors.HexColor("#52615b")
TEXT_LIGHT = colors.HexColor("#7a8a84")
ROW_ALT = colors.HexColor("#f8faf9")
ROW_WHITE = colors.HexColor("#ffffff")


class NyayNumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        w, h = A4
        # Running header on page 2 and later
        if self._pageNumber > 1:
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            title = getattr(self, "doc_case_title", "Nyay Saathi Case Brief")
            if len(title) > 65:
                title = title[:62] + "..."
            self.drawString(16 * mm, h - 11.5 * mm, f"Nyay Saathi Case Brief  |  {title}")
            self.drawRightString(w - 16 * mm, h - 11.5 * mm, "CONFIDENTIAL & PRIVILEGED")
            self.setStrokeColor(BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(16 * mm, h - 13.5 * mm, w - 16 * mm, h - 13.5 * mm)

        # Running footer on every page
        self.setStrokeColor(BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(16 * mm, 13 * mm, w - 16 * mm, 13 * mm)

        self.setFont("Helvetica", 7.2)
        self.setFillColor(TEXT_LIGHT)
        self.drawString(
            16 * mm,
            8.8 * mm,
            "Nyay Saathi AI Legal Information Companion  |  Factual intake brief; not legal representation or filing.",
        )
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(TEXT_DARK)
        self.drawRightString(w - 16 * mm, 8.8 * mm, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _format_fact_label(key: str) -> str:
    known = {
        "amount": "Disputed Amount",
        "product": "Product / Service",
        "seller": "Opposite Party / Merchant",
        "purchase_date": "Purchase / Order Date",
        "delivery_date": "Delivery Date",
        "defect_description": "Defect / Issue Stated",
        "issue_type": "Nature of Dispute",
        "current_stage": "Procedural Stage",
    }
    return known.get(key, key.replace("_", " ").title())


def _format_fact_status(status: str) -> str:
    known = {
        "user_confirmed": "Client Confirmed",
        "document_statement": "Document Verified",
        "user_allegation": "Client Stated",
        "assistant_inference": "System Inferred",
        "unknown": "Pending Verification",
    }
    return known.get(status, status.replace("_", " ").title())


def _format_event_entry(e: Any) -> tuple[str, str, str]:
    if isinstance(e, dict):
        date = str(e.get("date") or "—")
        summary = str(e.get("event") or e.get("summary") or e.get("description") or "—")
        source = str(e.get("source_id") or "Intake")
        return date, summary, source
    return "—", str(e), "Intake"


def _format_comm_entry(item: Any, default_label: str = "Communication") -> str:
    if isinstance(item, dict):
        date = item.get("date")
        text = (
            item.get("summary")
            or item.get("description")
            or item.get("content")
            or item.get("text")
            or str(item)
        )
        party = item.get("recipient") or item.get("sender") or item.get("party")
        prefix_parts = []
        if date:
            prefix_parts.append(str(date))
        if party:
            prefix_parts.append(str(party))
        prefix = f"[{' | '.join(prefix_parts)}] " if prefix_parts else ""
        return f"{prefix}{text}"
    return f"{default_label}: {item}"


def _format_urgent_entry(item: Any) -> str:
    if isinstance(item, dict):
        deadline = item.get("deadline") or item.get("date")
        desc = item.get("description") or item.get("summary") or item.get("matter") or str(item)
        prefix = f"[Deadline: {deadline}] " if deadline else "[Urgent] "
        return f"{prefix}{desc}"
    return str(item)


def _format_contradiction_entry(item: Any) -> str:
    if isinstance(item, dict):
        desc = item.get("description") or item.get("detail") or str(item)
        src = item.get("source") or item.get("sources")
        if src:
            return f"{desc} (Source: {src})"
        return desc
    return str(item)


def write_pdf(path: Path, payload: dict[str, Any]) -> None:
    font_name = _unicode_font()
    body_font = font_name

    title_style = ParagraphStyle(
        "BrandTitle",
        fontName=body_font,
        fontSize=18,
        leading=22,
        textColor=PRIMARY_COLOR,
        spaceAfter=1,
    )
    subtitle_style = ParagraphStyle(
        "BrandSubtitle",
        fontName=body_font,
        fontSize=8.5,
        leading=11,
        textColor=TEXT_MUTED,
    )
    badge_style = ParagraphStyle(
        "HeaderBadge",
        fontName=body_font,
        fontSize=7.5,
        leading=10,
        textColor=TEXT_MUTED,
        alignment=2,
    )
    sec_head_style = ParagraphStyle(
        "SectionHead",
        fontName=body_font,
        fontSize=11,
        leading=14,
        textColor=PRIMARY_COLOR,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    sub_head_style = ParagraphStyle(
        "SubHead",
        fontName=body_font,
        fontSize=9.5,
        leading=12,
        textColor=SECONDARY_COLOR,
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "Body",
        fontName=body_font,
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK,
        spaceAfter=2,
    )
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        fontName=body_font,
        fontSize=7.5,
        leading=10.5,
        textColor=TEXT_MUTED,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        fontName=body_font,
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK,
        leftIndent=10,
        firstLineIndent=-6,
        spaceAfter=2,
    )
    th_style = ParagraphStyle(
        "TH",
        fontName=body_font,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    td_style = ParagraphStyle(
        "TD",
        fontName=body_font,
        fontSize=8,
        leading=10.5,
        textColor=TEXT_DARK,
    )
    td_bold_style = ParagraphStyle(
        "TDBold",
        fontName=body_font,
        fontSize=8,
        leading=10.5,
        textColor=TEXT_DARK,
    )
    td_muted_style = ParagraphStyle(
        "TDMuted",
        fontName=body_font,
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_MUTED,
    )

    def p(text: Any, style=body_style, allow_markup: bool = False) -> Paragraph:
        raw = str(text if text is not None else "")
        clean = raw.replace("\n", "<br/>") if allow_markup else escape(raw).replace("\n", "<br/>")
        return Paragraph(clean, style)

    conv = payload.get("conversation", {})
    case_title = conv.get("title") or "Nyay Saathi Case Brief"
    case_version = payload.get("case_version", 1)
    case_id = conv.get("id") or "unassigned"
    created_date = conv.get("created_at", "")[:10] or "Current"
    language = str(conv.get("language", "en")).upper()
    memory = payload.get("case_memory", {})
    lawyer_brief = payload.get("lawyer_brief", {})
    overview = lawyer_brief.get("overview", {})

    story = []

    # 1. Header banner
    header_left = [
        p("Nyay Saathi Case Brief", title_style),
        p("AI Consumer Law Information Dossier & Fact Brief", subtitle_style),
    ]
    header_right = [
        p("<b>CASE BRIEF | CONFIDENTIAL</b>", badge_style, allow_markup=True),
        p(f"Ref ID: {case_id[:20]}", badge_style),
        p(f"Dossier Version: v{case_version}  |  Lang: {language}", badge_style),
        p(f"Date: {created_date}", badge_style),
    ]
    header_table = Table([[header_left, header_right]], colWidths=[105 * mm, 73 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, PRIMARY_COLOR),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 3 * mm))

    # 2. Case Identity Card
    parties_raw = overview.get("parties") or memory.get("parties", [])
    parties_str = (
        ", ".join(
            f"{p_item.get('name', 'Party')} ({p_item.get('role', 'party')})"
            if isinstance(p_item, dict)
            else str(p_item)
            for p_item in parties_raw
        )
        or "Not recorded"
    )
    locations_raw = overview.get("locations") or memory.get("locations", [])
    locations_str = (
        ", ".join(
            f"{l.get('city', '')}, {l.get('state', '')}".strip(", ")
            if isinstance(l, dict)
            else str(l)
            for l in locations_raw
        )
        or "Not specified"
    )
    remedy_str = (
        memory.get("requested_remedy") or overview.get("objective") or "Not confirmed yet."
    )
    amount_str = (
        overview.get("amount")
        or memory.get("facts", {}).get("amount", {}).get("value")
        or "Not specified"
    )

    meta_rows = [
        [p("<b>Case Title</b>", td_bold_style, allow_markup=True), p(case_title, td_style)],
        [p("<b>Parties</b>", td_bold_style, allow_markup=True), p(parties_str, td_style)],
        [
            p("<b>Jurisdiction / City</b>", td_bold_style, allow_markup=True),
            p(locations_str, td_style),
        ],
        [p("<b>Claimed Amount</b>", td_bold_style, allow_markup=True), p(amount_str, td_style)],
        [
            p("<b>Requested Remedy</b>", td_bold_style, allow_markup=True),
            p(remedy_str, td_style),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[40 * mm, 138 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), CALLOUT_BG),
                ("BACKGROUND", (1, 0), (1, -1), CARD_BG),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 2.5 * mm))

    # 3. Disclaimer Box
    disclaimer_text = (
        "<b>LEGAL NOTICE & STATUTORY DISCLAIMER:</b> "
        "This dossier is an AI-organised factual case brief prepared by Nyay Saathi from client-stated "
        "information and indexed consumer law sources. It is intended solely for client empowerment, structured "
        "factual preparation, and evaluation by qualified legal counsel. It does not constitute formal legal "
        "representation, legal advice, a power of attorney, or a formal court pleading under the Advocates Act, 1961."
    )
    disc_table = Table(
        [[p(disclaimer_text, disclaimer_style, allow_markup=True)]], colWidths=[178 * mm]
    )
    disc_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, PRIMARY_COLOR),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(disc_table)
    story.append(Spacer(1, 2 * mm))

    # 4. Executive Summary
    summary_text = (
        payload.get("summary")
        or overview.get("summary")
        or "No executive summary available yet."
    )
    story.append(p("1. Executive Summary", sec_head_style))
    story.append(p(summary_text, body_style))

    # 5. Stated & Documented Facts
    story.append(p("2. Facts and Verification Register", sec_head_style))
    facts = memory.get("facts", {})
    if facts:
        fact_rows = [
            [
                p("Fact / Parameter", th_style),
                p("Recorded Value", th_style),
                p("Verification Status", th_style),
                p("Source", th_style),
            ]
        ]
        for key, val in facts.items():
            if isinstance(val, dict):
                v_text = str(val.get("value", ""))
                s_text = _format_fact_status(str(val.get("status", "unknown")))
                prov_list = val.get("provenance", [])
                p_text = (
                    ", ".join(
                        pr.get("source_id", "") for pr in prov_list if isinstance(pr, dict)
                    )
                    or "Intake"
                )
            else:
                v_text = str(val)
                s_text = "Client Stated"
                p_text = "Intake"
            fact_rows.append(
                [
                    p(f"<b>{_format_fact_label(key)}</b>", td_style, allow_markup=True),
                    p(v_text, td_style),
                    p(
                        s_text,
                        td_bold_style
                        if "Confirmed" in s_text or "Verified" in s_text
                        else td_style,
                    ),
                    p(p_text, td_muted_style),
                ]
            )
        fact_table = Table(
            fact_rows, colWidths=[42 * mm, 74 * mm, 36 * mm, 26 * mm], repeatRows=1
        )
        fact_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    *[
                        (
                            "BACKGROUND",
                            (0, r),
                            (-1, r),
                            ROW_ALT if r % 2 == 1 else ROW_WHITE,
                        )
                        for r in range(1, len(fact_rows))
                    ],
                ]
            )
        )
        story.append(fact_table)
    else:
        story.append(p("No structured factual parameters recorded yet.", td_muted_style))

    # 6. Chronology / Timeline
    story.append(p("3. Chronological Sequence of Events", sec_head_style))
    events = memory.get("events", []) or lawyer_brief.get("chronology", [])
    if events:
        ev_rows = [
            [
                p("Date", th_style),
                p("Event / Action Description", th_style),
                p("Source", th_style),
            ]
        ]
        for ev in events:
            date, desc, src = _format_event_entry(ev)
            ev_rows.append(
                [
                    p(f"<b>{date}</b>", td_style, allow_markup=True),
                    p(desc, td_style),
                    p(src, td_muted_style),
                ]
            )
        ev_table = Table(ev_rows, colWidths=[28 * mm, 124 * mm, 26 * mm], repeatRows=1)
        ev_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SECONDARY_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    *[
                        (
                            "BACKGROUND",
                            (0, r),
                            (-1, r),
                            ROW_ALT if r % 2 == 1 else ROW_WHITE,
                        )
                        for r in range(1, len(ev_rows))
                    ],
                ]
            )
        )
        story.append(ev_table)
    else:
        story.append(p("No confirmed timeline entries recorded.", td_muted_style))

    # 7. Evidence Register
    story.append(p("4. Documentary Evidence Register", sec_head_style))
    evidence_items = lawyer_brief.get("evidence_index") or payload.get("evidence", [])
    if evidence_items:
        ev_rows = [
            [
                p("Document Name", th_style),
                p("Extraction", th_style),
                p("Supporting Claims & Evidentiary Note", th_style),
            ]
        ]
        for item in evidence_items:
            name = (
                item.get("document_name")
                or item.get("filename")
                or str(item.get("id", "Evidence file"))
            )
            status = item.get("extraction_status", "uploaded")
            supports = ", ".join(item.get("may_support", []))
            note = item.get(
                "note", "Uploaded document awaiting qualified advocate review."
            )
            combined_note = (
                f"<b>Supports:</b> {escape(supports)}<br/>{escape(note)}"
                if supports
                else escape(note)
            )
            ev_rows.append(
                [
                    p(f"<b>{escape(name)}</b>", td_style, allow_markup=True),
                    p(status, td_muted_style),
                    p(combined_note, td_style, allow_markup=True),
                ]
            )
        ev_table = Table(ev_rows, colWidths=[55 * mm, 30 * mm, 93 * mm], repeatRows=1)
        ev_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SECONDARY_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    *[
                        (
                            "BACKGROUND",
                            (0, r),
                            (-1, r),
                            ROW_ALT if r % 2 == 1 else ROW_WHITE,
                        )
                        for r in range(1, len(ev_rows))
                    ],
                ]
            )
        )
        story.append(ev_table)
    else:
        story.append(p("No evidence files uploaded for this case.", td_muted_style))

    # 8. Contradictions & Information Gaps
    story.append(p("5. Contradictions & Pending Information Gaps", sec_head_style))
    contradictions = memory.get("contradictions", [])
    unknowns = memory.get("unknowns", [])
    if contradictions or unknowns:
        for c in contradictions:
            story.append(
                p(
                    f"• <b>[Discrepancy / Contradiction]</b> {escape(_format_contradiction_entry(c))}",
                    bullet_style,
                    allow_markup=True,
                )
            )
        for u in unknowns:
            story.append(
                p(
                    f"• <b>[Missing Information]</b> {escape(str(u))}",
                    bullet_style,
                    allow_markup=True,
                )
            )
    else:
        story.append(
            p(
                "None recorded. No material discrepancies or critical gaps identified.",
                td_muted_style,
            )
        )

    # 9. Prior Communications & Counterparty Responses
    story.append(p("6. Communications and Responses", sec_head_style))
    correspondence = lawyer_brief.get("correspondence_history") or memory.get(
        "correspondence_history", []
    )
    responses = lawyer_brief.get("responses_received") or memory.get(
        "responses_received", []
    )
    if correspondence or responses:
        for item in correspondence:
            story.append(
                p(
                    f"• <b>[Outgoing]</b> {escape(_format_comm_entry(item, 'Sent'))}",
                    bullet_style,
                    allow_markup=True,
                )
            )
        for item in responses:
            story.append(
                p(
                    f"• <b>[Counterparty Response]</b> {escape(_format_comm_entry(item, 'Received'))}",
                    bullet_style,
                    allow_markup=True,
                )
            )
    else:
        story.append(
            p("No prior correspondence or responses recorded.", td_muted_style)
        )

    # 10. Legal Review Issues & Urgent Matters
    story.append(p("7. Matters for Qualified Advocate Review", sec_head_style))
    urgent = lawyer_brief.get("urgent_matters") or memory.get("urgent_matters", [])
    if urgent:
        for u in urgent:
            story.append(
                p(
                    f"• <b>[URGENT TIMING]</b> {escape(_format_urgent_entry(u))}",
                    bullet_style,
                    allow_markup=True,
                )
            )

    issues = lawyer_brief.get("possible_legal_issues_for_review") or memory.get(
        "legal_issues_for_review", []
    )
    for issue in issues or [
        "No specific statutory issue recorded for qualified legal review yet."
    ]:
        story.append(
            p(
                f"• <b>[Legal Issue]</b> {escape(str(issue))}",
                bullet_style,
                allow_markup=True,
            )
        )

    story.append(p("Questions for Counsel", sub_head_style))
    for q in lawyer_brief.get("questions_for_lawyer", []):
        story.append(p(f"• {escape(str(q))}", bullet_style, allow_markup=True))

    # 11. Prepared Drafts
    story.append(p("8. Prepared Drafts and Notices", sec_head_style))
    drafts = payload.get("drafts", [])
    if drafts:
        for d in drafts:
            d_title = d.get("title", "Draft")
            d_status = str(d.get("status", "draft")).upper()
            d_ver = d.get("version", 1)
            d_case_ver = d.get("case_version", 1)
            d_content = d.get("content", "")
            d_box = [
                p(
                    f"<b>{escape(d_title)}</b>  |  Status: <b>{escape(d_status)}</b>  |  Draft v{d_ver} (Case v{d_case_ver})",
                    td_bold_style,
                    allow_markup=True,
                ),
                Spacer(1, 1.5 * mm),
                p(d_content, body_style),
            ]
            d_table = Table([[d_box]], colWidths=[178 * mm])
            d_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
                        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                        ("LINEBEFORE", (0, 0), (0, -1), 2, SECONDARY_COLOR),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(d_table)
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(p("No legal drafts created for this case yet.", td_muted_style))

    # 12. Sources Relied Upon
    story.append(p("9. Statutory Authorities and Official Portals", sec_head_style))
    sources = payload.get("sources", [])
    if sources:
        for s in sources:
            title = s.get("title") or "Statutory Source"
            loc = s.get("locator") or ""
            url = s.get("canonical_url") or ""
            meta_line = f"{title} | {loc}" if loc else title
            url_part = f"<br/>&nbsp;&nbsp;&nbsp;&nbsp;<font color='#52615b'>{escape(url)}</font>" if url else ""
            story.append(
                p(
                    f"• <b>{escape(meta_line)}</b>{url_part}",
                    bullet_style,
                    allow_markup=True,
                )
            )
    else:
        story.append(
            p("No legal sources were linked to an answer in this case.", td_muted_style)
        )

    def make_canvas(title: str):
        class CanvasWithMeta(NyayNumberedCanvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.doc_case_title = title

        return CanvasWithMeta

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Nyay Saathi Case Brief",
    )
    doc.build(story, canvasmaker=make_canvas(case_title))
