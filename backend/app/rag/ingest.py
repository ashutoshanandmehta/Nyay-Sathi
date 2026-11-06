"""Reproducible allowlisted ingestion of official consumer-law sources."""

import argparse
import hashlib
import html
import ipaddress
import json
import re
import socket
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.rag.source_policy import allowed_url
from app.services.pdf_backend import open_pdf

ROOT = Path(__file__).parents[3]
REGISTER = ROOT / "data" / "manifests" / "source-register.json"
OUT = ROOT / "data" / "sources" / "ingested_passages.json"
ORIGINALS = ROOT / "data" / "sources" / "originals"
MAX_BYTES = 25 * 1024 * 1024


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag in {"p", "h1", "h2", "h3", "li", "br"} and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def validate_url(url: str, url_policy=None) -> None:
    parsed = urlparse(url)
    if not (url_policy or allowed_url)(url):
        raise ValueError(f"URL is not on the HTTPS allowlist: {url}")
    for answer in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(answer[4][0])
        if any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
            )
        ):
            raise ValueError(f"Host resolved to a disallowed network address: {parsed.hostname}")


def fetch(
    url: str, *, timeout: float = 45, max_bytes: int = MAX_BYTES, url_policy=None
) -> tuple[bytes, str]:
    current = url
    deadline = time.monotonic() + timeout
    with httpx.Client(
        timeout=httpx.Timeout(timeout, connect=min(8, timeout)),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "NyaySaathiSourceIngest/0.1"},
    ) as client:
        for _ in range(4):
            if url_policy is None:
                validate_url(current)
            else:
                validate_url(current, url_policy)
            host = urlparse(current).hostname
            # Pin the validated public address while preserving TLS certificate/SNI verification.
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            address = addresses[0][4][0]
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("Disallowed destination")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Source fetch budget exhausted")
            target = httpx.URL(current).copy_with(host=address)
            with client.stream(
                "GET",
                target,
                headers={"Host": host},
                extensions={"sni_hostname": host},
                timeout=remaining,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RuntimeError("Redirect had no Location header")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length > max_bytes:
                    raise ValueError("Source exceeds download limit")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise TimeoutError("Source fetch budget exhausted")
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Source exceeds download limit")
                    chunks.append(chunk)
                return b"".join(chunks), current
        raise RuntimeError("Too many redirects")


def chunk_text(source: dict, raw: bytes, content_type: str, max_pdf_pages=None) -> list[dict]:
    pages: list[tuple[str, str]] = []
    if content_type == "pdf":
        with open_pdf(raw) as document:
            count = min(document.page_count, max_pdf_pages or document.page_count)
            pages = [
                (f"Page {index + 1}", document[index].get_text("text")) for index in range(count)
            ]
    else:
        parser = TextExtractor()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = html.unescape(" ".join(parser.parts))
        pages = [("Official webpage", text)]
    chunks: list[dict] = []
    for locator, text in pages:
        cleaned = re.sub(r"[ \t]+", " ", text)
        blocks = [
            x.strip() for x in re.split(r"\n{2,}|(?=\n\d+\.\s)", cleaned) if len(x.strip()) > 80
        ]
        for index, block in enumerate(blocks):
            for start in range(0, len(block), 2200):
                piece = block[start : start + 2600].strip()
                if len(piece) < 80:
                    continue
                digest = hashlib.sha256(piece.encode()).hexdigest()[:12]
                chunks.append(
                    {
                        "passage_id": f"{source['source_id']}-{locator.lower().replace(' ', '-')}-{index}-{digest}",
                        "source_id": source["source_id"],
                        "title": source["title"],
                        "locator": locator,
                        "text": piece,
                        "canonical_url": source["canonical_url"],
                        "retrieved_at": source["retrieved_at"],
                        "limitations": source["known_limitations"],
                        "source_type": source["source_type"],
                        "jurisdiction": source["jurisdiction"],
                        "publication_date": source.get("publication_date"),
                        "effective_date": source.get("effective_date"),
                        "version_information": source.get("version_information"),
                    }
                )
    return chunks


def run() -> dict:
    sources = json.loads(REGISTER.read_text())
    ORIGINALS.mkdir(parents=True, exist_ok=True)
    passages, results = [], []
    for source in sources:
        if source.get("ingest_enabled", True) is False:
            results.append(
                {
                    "source_id": source["source_id"],
                    "status": "skipped",
                    "reason": "Source register/discovery page is not itself a claim-supporting passage corpus.",
                }
            )
            continue
        try:
            last_error = None
            for _attempt in range(2):
                try:
                    raw, final_url = fetch(source["canonical_url"])
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
            else:
                raise last_error or RuntimeError("Source download failed")
            is_pdf = raw.startswith(b"%PDF-")
            suffix = ".pdf" if is_pdf else ".html"
            (ORIGINALS / f"{source['source_id']}{suffix}").write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            source["content_hash"] = f"sha256:{digest}"
            source["canonical_url"] = final_url
            parsed = chunk_text(source, raw, "pdf" if is_pdf else "html")
            passages.extend(parsed)
            results.append(
                {
                    "source_id": source["source_id"],
                    "status": "ok",
                    "bytes": len(raw),
                    "passages": len(parsed),
                    "content_hash": source["content_hash"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "source_id": source["source_id"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    REGISTER.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n")
    OUT.write_text(json.dumps(passages, ensure_ascii=False, indent=2) + "\n")
    return {"sources": results, "passage_count": len(passages), "output": str(OUT)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    args = parser.parse_args()
    report = run()
    print(json.dumps(report, indent=2) if args.json else report)
