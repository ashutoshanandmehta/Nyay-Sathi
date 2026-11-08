import io
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile
from PIL import Image

from app.security.abuse import inspect_extracted_text, inspect_upload_bytes
from app.services.pdf_backend import open_pdf, page_image_bytes

ALLOWED = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}
PROMPT_INJECTION = re.compile(
    r"(?:ignore (?:all|previous) instructions|system prompt|act as (?:the )?system|developer message)",
    re.I,
)


def detect_type(data: bytes, declared: str | None) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if declared == "text/plain":
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return None
    return None


def _ocr(image: Image.Image) -> tuple[str, str]:
    if not shutil.which("tesseract"):
        return "", "ocr_unavailable"
    try:
        import pytesseract

        languages = set(pytesseract.get_languages(config=""))
        selected = "+".join(lang for lang in ("eng", "hin") if lang in languages)
        if not selected:
            return "", "ocr_unavailable"
        text = pytesseract.image_to_string(image, lang=selected, timeout=25).strip()
        return text, "ocr_complete" if text else "unreadable"
    except Exception:
        return "", "ocr_failed"


def extract_document(
    data: bytes,
    mime: str,
    max_pages: int,
    pdf_engine: Literal["pymupdf", "pypdf"] = "pymupdf",
) -> tuple[str, str, dict[str, Any]]:
    metadata: dict[str, Any] = {"pages": [], "embedded_instructions_untrusted": False}
    if mime == "text/plain":
        text = data.decode("utf-8")
        status = "complete"
    elif mime in {"image/png", "image/jpeg"}:
        text, status = _ocr(Image.open(io.BytesIO(data)))
        metadata["pages"].append({"page": 1, "start": 0, "end": len(text), "method": "ocr"})
    else:
        doc = open_pdf(data, engine=pdf_engine)
        if doc.needs_pass:
            doc.close()
            raise ValueError("password_protected_pdf")
        if doc.page_count > max_pages:
            doc.close()
            raise ValueError("page_limit_exceeded")
        chunks: list[str] = []
        partial = False
        for index, page in enumerate(doc):
            extracted = page.get_text("text").strip()
            method = "pdf_text"
            ocr_status = None
            if len(extracted) < 20:
                img_bytes = page_image_bytes(page)
                if img_bytes is not None:
                    extracted, ocr_status = _ocr(Image.open(io.BytesIO(img_bytes)))
                    method = "ocr"
                    partial = partial or ocr_status != "ocr_complete"
                else:
                    ocr_status = "ocr_skipped_permissive_pdf_engine"
                    partial = True
            start = sum(len(x) + 1 for x in chunks)
            chunks.append(extracted)
            metadata["pages"].append(
                {
                    "page": index + 1,
                    "start": start,
                    "end": start + len(extracted),
                    "method": method,
                    "ocr_status": ocr_status,
                }
            )
        doc.close()
        text = "\n".join(chunks).strip()
        status = "partial" if partial and text else "unreadable" if not text else "complete"
    text_scan = inspect_extracted_text(text)
    if PROMPT_INJECTION.search(text) or text_scan["prompt_injection_detected"]:
        metadata["embedded_instructions_untrusted"] = True
    metadata["security_scan"] = text_scan
    metadata["pdf_engine"] = pdf_engine if mime == "application/pdf" else None
    return text, status, metadata


async def process_upload(
    file: UploadFile,
    upload_dir: Path,
    max_bytes: int,
    max_pages: int,
    *,
    pdf_engine: Literal["pymupdf", "pypdf"] = "pymupdf",
    encrypt_fn=None,
) -> dict[str, Any]:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file_too_large")
    byte_scan = inspect_upload_bytes(data, file.filename)
    mime = detect_type(data, file.content_type)
    if mime not in ALLOWED:
        raise ValueError("unsupported_file_type")
    attachment_id = str(uuid.uuid4())
    stored = upload_dir / f"{attachment_id}{ALLOWED[mime]}"
    stored_bytes = encrypt_fn(data) if encrypt_fn is not None else data
    stored.write_bytes(stored_bytes)
    try:
        import asyncio

        text, status, metadata = await asyncio.to_thread(
            extract_document, data, mime, max_pages, pdf_engine
        )
    except ValueError:
        stored.unlink(missing_ok=True)
        raise
    except Exception as exc:
        stored.unlink(missing_ok=True)
        raise ValueError("document_could_not_be_read") from exc
    metadata["byte_scan"] = byte_scan
    metadata["encrypted_at_rest"] = encrypt_fn is not None
    safe_name = Path(file.filename or f"upload{ALLOWED[mime]}").name[:150]
    return {
        "id": attachment_id,
        "filename": safe_name,
        "stored_path": str(stored),
        "mime_type": mime,
        "size": len(data),
        "extraction_status": status,
        "extracted_text": text,
        "metadata_json": json.dumps(metadata),
    }
