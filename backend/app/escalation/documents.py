"""The lawyer bundle as a PDF or Word case note, laid out in the same order as the panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.exports import (
    BORDER_LIGHT,
    CALLOUT_BG,
    CARD_BG,
    PRIMARY_COLOR,
    ROW_ALT,
    ROW_WHITE,
    SECONDARY_COLOR,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    NyayNumberedCanvas,
    _unicode_font,
)

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
    font = _unicode_font()
    body_font = font

    title_style = ParagraphStyle(
        "BundleTitle",
        fontName=body_font,
        fontSize=18,
        leading=22,
        textColor=PRIMARY_COLOR,
        spaceAfter=1,
    )
    subtitle_style = ParagraphStyle(
        "BundleSubtitle",
        fontName=body_font,
        fontSize=8.5,
        leading=11,
        textColor=TEXT_MUTED,
    )
    badge_style = ParagraphStyle(
        "BundleBadge",
        fontName=body_font,
        fontSize=7.5,
        leading=10,
        textColor=TEXT_MUTED,
        alignment=2,
    )
    sec_head_style = ParagraphStyle(
        "BundleSectionHead",
        fontName=body_font,
        fontSize=11,
        leading=14,
        textColor=PRIMARY_COLOR,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "BundleBody",
        fontName=body_font,
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK,
        spaceAfter=2,
    )
    disclaimer_style = ParagraphStyle(
        "BundleDisclaimer",
        fontName=body_font,
        fontSize=7.5,
        leading=10.5,
        textColor=TEXT_MUTED,
    )
    bullet_style = ParagraphStyle(
        "BundleBullet",
        fontName=body_font,
        fontSize=8.5,
        leading=11.5,
        textColor=TEXT_DARK,
        leftIndent=10,
        firstLineIndent=-6,
        spaceAfter=2,
    )
    th_style = ParagraphStyle(
        "BundleTH",
        fontName=body_font,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    td_style = ParagraphStyle(
        "BundleTD",
        fontName=body_font,
        fontSize=8,
        leading=10.5,
        textColor=TEXT_DARK,
    )

    def para(text: Any, style=body_style, allow_markup: bool = False) -> Paragraph:
        raw = str(text if text is not None else "")
        clean = raw.replace("\n", "<br/>") if allow_markup else escape(raw).replace("\n", "<br/>")
        return Paragraph(clean, style)

    case_title = bundle.get("case_title") or "Case Brief"
    date_str = str(bundle.get("generated_at", ""))[:10] or "Current"

    header_left = [
        para("Nyay Saathi — Case Note for Counsel", title_style),
        para("Factual brief prepared for advocate review and consultation", subtitle_style),
    ]
    header_right = [
        para("<b>COUNSEL BRIEF | PRIVILEGED</b>", badge_style, allow_markup=True),
        para(f"Case: {case_title[:30]}", badge_style),
        para(f"Date Prepared: {date_str}", badge_style),
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

    notice_box = Table(
        [[para(f"<b>NOTICE FOR COUNSEL:</b> {NOTICE}", disclaimer_style, allow_markup=True)]],
        colWidths=[178 * mm],
    )
    notice_box.setStyle(
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

    story = [
        header_table,
        Spacer(1, 3 * mm),
        notice_box,
        Spacer(1, 2 * mm),
    ]

    if bundle.get("executive_summary"):
        story += [
            para("Executive Summary", sec_head_style),
            para(bundle["executive_summary"], body_style),
        ]

    if bundle.get("chronology"):
        rows = [
            [para("Date", th_style), para("Event Description", th_style)]
        ] + [
            [para(f"<b>{escape(e['date'])}</b>", td_style, allow_markup=True), para(escape(e["summary"]), td_style, allow_markup=True)]
            for e in bundle["chronology"]
        ]
        table = Table(rows, colWidths=[32 * mm, 146 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SECONDARY_COLOR),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    *[
                        ("BACKGROUND", (0, r), (-1, r), ROW_ALT if r % 2 == 1 else ROW_WHITE)
                        for r in range(1, len(rows))
                    ],
                ]
            )
        )
        story += [para("Chronology of Stated Events", sec_head_style), table]

    for title, items in sections(bundle):
        story += [para(title, sec_head_style)]
        for item in items:
            story += [para(f"• {escape(item)}", bullet_style, allow_markup=True)]

    if bundle.get("autonomy_notice"):
        auto_box = Table(
            [[para(f"<b>AUTONOMY & COMPLIANCE:</b> {bundle['autonomy_notice']}", disclaimer_style, allow_markup=True)]],
            colWidths=[178 * mm],
        )
        auto_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story += [Spacer(1, 4 * mm), auto_box]

    def make_canvas(title: str):
        class BundleCanvas(NyayNumberedCanvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.doc_case_title = title

        return BundleCanvas

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Case note for counsel",
    )
    doc.build(story, canvasmaker=make_canvas(case_title))


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
