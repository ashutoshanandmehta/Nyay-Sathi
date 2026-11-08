"""Local render adapters for clean user-edited correspondence, with no network access."""

import re
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.exports import NyayNumberedCanvas, _unicode_font


def plain_line(line):
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", line)


class CorrespondenceExporter:
    def docx(self, path, title, content):
        doc = Document()
        section = doc.sections[0]
        section.page_width, section.page_height = Inches(8.5), Inches(11)
        section.top_margin = section.bottom_margin = Inches(0.75)
        section.left_margin = section.right_margin = Inches(0.85)
        normal = doc.styles["Normal"]
        normal.font.name = "Arial"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(8)
        normal.paragraph_format.line_spacing = 1.15
        for name in ["Title", "Heading 1", "Heading 2", "Heading 3"]:
            doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        doc.add_paragraph(
            re.sub(r"[^\w\s]", " ", title).strip() or "Prepared correspondence", style="Title"
        )
        for line in content.splitlines():
            cleaned = plain_line(line)
            if cleaned.startswith("#"):
                doc.add_paragraph(cleaned.lstrip("# ").strip(), style="Heading 2")
            else:
                doc.add_paragraph(cleaned)
        doc.core_properties.author = ""
        doc.core_properties.title = title
        doc.save(path)

    def pdf(self, path, title, content):
        font = _unicode_font()
        body = ParagraphStyle(
            "Correspondence",
            fontName=font,
            fontSize=10,
            leading=14.5,
            textColor=colors.HexColor("#1c2421"),
            spaceAfter=6,
        )
        heading = ParagraphStyle(
            "CorrespondenceTitle",
            parent=body,
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1b4332"),
            spaceAfter=4,
        )
        subheading = ParagraphStyle(
            "CorrespondenceSubhead",
            parent=body,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#2d6a4f"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )
        bullet = ParagraphStyle(
            "CorrespondenceBullet",
            parent=body,
            leftIndent=12,
            firstLineIndent=-8,
            spaceAfter=3,
        )

        header_table = Table(
            [[Paragraph(escape(title or "Prepared Correspondence"), heading)]],
            colWidths=[178 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#1b4332")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story = [header_table, Spacer(1, 3 * mm)]

        for line in content.splitlines():
            cleaned = plain_line(line).strip()
            if not cleaned:
                story.append(Spacer(1, 3 * mm))
            elif cleaned.startswith("#"):
                story.append(Paragraph(escape(cleaned.lstrip("# ").strip()), subheading))
            elif cleaned.startswith(("- ", "* ", "• ")):
                bullet_text = cleaned.lstrip("-*• ")
                story.append(Paragraph(f"• {escape(bullet_text)}", bullet))
            else:
                story.append(Paragraph(escape(cleaned), body))

        def make_canvas(doc_title: str):
            class CorrespondenceCanvas(NyayNumberedCanvas):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.doc_case_title = doc_title

            return CorrespondenceCanvas

        SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=title or "Prepared Correspondence",
        ).build(story, canvasmaker=make_canvas(title or "Prepared Correspondence"))
