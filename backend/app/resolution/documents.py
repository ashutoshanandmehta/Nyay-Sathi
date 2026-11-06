"""Local render adapters for clean user-edited correspondence, with no network access."""

import re
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.exports import _unicode_font


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
            "Correspondence", fontName=font, fontSize=11, leading=16, spaceAfter=8
        )
        heading = ParagraphStyle(
            "CorrespondenceTitle", parent=body, fontSize=16, leading=22, spaceAfter=18
        )
        story = [Paragraph(escape(title), heading)]
        for line in content.splitlines():
            story.append(
                Paragraph(escape(plain_line(line)), body) if line.strip() else Spacer(1, 8)
            )
        SimpleDocTemplate(
            str(path), pagesize=letter, leftMargin=60, rightMargin=60, topMargin=54, bottomMargin=54
        ).build(story)
