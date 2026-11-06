"""PDF engine boundary. Retains V1 extraction/OCR behavior without choosing distribution terms.

PyMuPDF is dual AGPL/commercial licensed. See docs/v2-reuse-and-licenses.md
before distributing this application. Replacing this adapter requires extraction/OCR regression QA.
"""

import fitz


def open_pdf(data):
    return fitz.open(stream=data, filetype="pdf")


def page_image_bytes(page):
    return page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
