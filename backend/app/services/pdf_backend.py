"""PDF engine boundary supporting both PyMuPDF (OCR rasterization) and permissive BSD pypdf."""

from __future__ import annotations

import io
from typing import Literal


class _PypdfPageAdapter:
    def __init__(self, page):
        self._page = page

    def get_text(self, mode: str = "text") -> str:
        del mode
        return self._page.extract_text() or ""


class _PypdfDocumentAdapter:
    def __init__(self, data: bytes):
        from pypdf import PdfReader

        self._reader = PdfReader(io.BytesIO(data))
        self.needs_pass = bool(self._reader.is_encrypted)
        self.page_count = 0 if self.needs_pass else len(self._reader.pages)

    def __iter__(self):
        for page in self._reader.pages:
            yield _PypdfPageAdapter(page)

    def close(self) -> None:
        return None


def open_pdf(data: bytes, engine: Literal["pymupdf", "pypdf"] = "pymupdf"):
    if engine == "pypdf":
        return _PypdfDocumentAdapter(data)
    import fitz

    return fitz.open(stream=data, filetype="pdf")


def page_image_bytes(page) -> bytes | None:
    if isinstance(page, _PypdfPageAdapter):
        # pypdf is pure-Python text extraction without AGPL rasterizer; OCR fallback skipped cleanly.
        return None
    import fitz

    return page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
