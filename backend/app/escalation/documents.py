"""The lawyer bundle as a PDF or Word case note, laid out in the same order as the panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches, Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.exports import _unicode_font

NOTICE = (
    "Prepared by Nyay Saathi from the client's own account and the sources listed. "
    "It is not legal advice, and the facts have not been verified."
)


def sections(bundle: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """(heading, items) pairs shared by both formats; empty sections are left out."""
    sources = [
        ", ".join(x for x in (s.get("title"), s.get("locator"), s.get("canonical_url")) if x)
        for s in bundle["source_backed_analysis"]["verified_sources"]
    ]
    pairs = [
        ("Reasons for review", bundle["escalation_reasons"]),
        ("Facts stated by the client", bundle["stated_facts"]),
        ("Questions for counsel", bundle["questions_for_counsel"]),
        ("Facts to be established", bundle["facts_to_establish"]),
        ("Not yet verified by Nyay Saathi", bundle["not_confirmed"]),
        ("Evidence files", [e["filename"] for e in bundle["evidence_index"]]),
        ("Drafts", [f"{d['title']} (version {d['version']})" for d in bundle["generated_drafts"]]),
        ("Sources relied on", sources),
    ]
    return [(title, items) for title, items in pairs if items]


def write_bundle_pdf(path: Path, bundle: dict[str, Any]) -> None:
    styles = getSampleStyleSheet()
    font = _unicode_font()
    for name in ("Title", "Heading2", "BodyText", "Normal", "Italic"):
        styles[name].fontName = font

    def para(text: Any, style: str = "BodyText") -> Paragraph:
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])

    story = [
        para("Case note for counsel", "Title"),
        para(f"{bundle['case_title']}, prepared {bundle['generated_at'][:10]}", "Normal"),
        Spacer(1, 3 * mm),
        para(NOTICE, "Italic"),
    ]
    if bundle["executive_summary"]:
        story += [Spacer(1, 4 * mm), para("Summary", "Heading2"), para(bundle["executive_summary"])]
    if bundle["chronology"]:
        rows = [[para("Date"), para("Event")]] + [
            [para(e["date"]), para(e["summary"])] for e in bundle["chronology"]
        ]
        table = Table(rows, colWidths=[32 * mm, 140 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), "#E8EFEC"),
                    ("GRID", (0, 0), (-1, -1), 0.5, "#D9D9D9"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story += [Spacer(1, 4 * mm), para("Chronology", "Heading2"), table]
    for title, items in sections(bundle):
        story += [Spacer(1, 4 * mm), para(title, "Heading2")]
        story += [para(f"• {item}") for item in items]
    story += [Spacer(1, 6 * mm), para(bundle["autonomy_notice"], "Italic")]
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title="Case note for counsel",
    ).build(story)


def write_bundle_docx(path: Path, bundle: dict[str, Any]) -> None:
    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Inches(0.85)
    doc.styles["Normal"].font.name, doc.styles["Normal"].font.size = "Arial", Pt(10.5)
    doc.add_heading("Case note for counsel", level=0)
    doc.add_paragraph(f"{bundle['case_title']}, prepared {bundle['generated_at'][:10]}")
    doc.add_paragraph(NOTICE).runs[0].italic = True
    if bundle["executive_summary"]:
        doc.add_heading("Summary", level=2)
        doc.add_paragraph(bundle["executive_summary"])
    if bundle["chronology"]:
        doc.add_heading("Chronology", level=2)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Date", "Event"
        for event in bundle["chronology"]:
            row = table.add_row().cells
            row[0].text, row[1].text = event["date"], event["summary"]
    for title, items in sections(bundle):
        doc.add_heading(title, level=2)
        for item in items:
            doc.add_paragraph(item, style="List Bullet")
    doc.add_paragraph(bundle["autonomy_notice"]).runs[0].italic = True
    doc.save(str(path))
