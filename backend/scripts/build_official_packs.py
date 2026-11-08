"""Build official-text knowledge packs from downloaded official PDFs.

Standalone on purpose (stdlib + PyMuPDF only) so it can run in isolated mode over
downloaded files, which are untrusted input:

    cd backend && .venv/bin/python -I scripts/build_official_packs.py

Originals live in data/sources/originals/ (gitignored); fetch them from the URLs below.
Each passage is the exact section or paragraph text (whitespace normalised only), with
its official URL, the original file's SHA-256 and an honest review status. No model call
is made and nothing here is lawyer-reviewed.
"""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = ROOT / "data" / "sources" / "originals"
OUT = ROOT / "data" / "knowledge" / "official_law_packs_v1.json"

NOT_REVIEWED = "Official text extracted verbatim; not reviewed by a lawyer."
BIHAR_TERMS = [
    "bihar",
    "patna",
    "biharsharif",
    "gaya",
    "bhagalpur",
    "muzaffarpur",
    "darbhanga",
    "purnia",
    "arrah",
    "begusarai",
    "katihar",
    "munger",
    "chapra",
    "sasaram",
    "hajipur",
    "nalanda",
    "siwan",
    "motihari",
    "बिहार",
    "पटना",
]
ARREST = ["arrest", "arrested", "giraftari", "गिरफ्तारी", "police", "thana", "jail", "custody"]
BAIL = ["bail", "jamanat", "जमानत", "release", "jail", "custody", "hirasat", "हिरासत"]
LIQUOR = ["liquor", "alcohol", "sharab", "daru", "शराब", "prohibition", "sharabbandi", "excise"]
VEHICLE = ["vehicle", "car", "gaadi", "seized", "seizure", "confiscation", "release"]
WAGES = ["salary", "wages", "unpaid", "tankhwah", "vetan", "वेतन", "employer", "dues"]

SOURCES = [
    {
        "source_id": "bnss-2023",
        "file": "bnss-2023-ncrb.pdf",
        "url": "https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/BNSS2023.pdf",
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "publisher": "National Crime Records Bureau, Ministry of Home Affairs",
        "layout": "heading_above",
        "arrangement_pages": (2, 19),
        "body_pages": (46, 262),
        "domain": "criminal",
        "jurisdiction": "India",
        "effective_date": "2024-07-01",
        "limitations": "From the NCRB compilation of the BNSS (in force from 1 July 2024). "
        "Check later amendments and state notifications.",
        "tags": ["bnss", "criminal procedure", "police"],
        "sections": {
            "35": ARREST + ["without warrant"],
            "36": ARREST + ["arrest memo", "procedure"],
            "38": ARREST + ["advocate", "lawyer", "vakil", "interrogation"],
            "47": ARREST + BAIL + ["grounds", "bailable"],
            "48": ARREST + ["relative", "friend", "family", "informed", "where held"],
            "57": ARREST + ["magistrate"],
            "58": ARREST + ["twenty-four hours", "24 hours", "magistrate", "detention"],
            "144": ["maintenance", "wife", "children", "parents", "guzara", "kharcha"],
            "173": ["fir", "first information report", "complaint", "police", "zero fir"],
            "187": BAIL + ["remand", "police custody", "judicial custody", "investigation"],
            "341": ["legal aid", "free lawyer", "state expense", "accused", "vakil"],
            "478": BAIL + ["bailable offence"],
            "479": BAIL + ["undertrial", "maximum period"],
            "480": BAIL + ["non-bailable offence"],
            "482": BAIL + ["anticipatory bail", "apprehending arrest"],
            "483": BAIL + ["high court", "court of session", "sessions court"],
        },
    },
    {
        "source_id": "lsa-act-1987",
        "file": "lsa-act-1987-nalsa.pdf",
        "url": "https://cdnbbsr.s3waas.gov.in/s32e45f93088c7db59767efef516b306aa/uploads/2025/04/202504081796627129.pdf",
        "title": "Legal Services Authorities Act, 1987",
        "publisher": "National Legal Services Authority (NALSA)",
        "layout": "inline",
        "body_pages": (1, 19),
        "domain": "legal_aid",
        "jurisdiction": "India",
        "effective_date": "1995-11-09",
        "limitations": "Income limits in section 12(h) are raised by state rules; ask the "
        "State or District Legal Services Authority for the current limit.",
        "tags": [
            "legal aid",
            "free legal aid",
            "free lawyer",
            "dlsa",
            "nalsa",
            "legal services",
            "mufat vakil",
            "मुफ्त कानूनी सहायता",
        ],
        "sections": {
            "12": [
                "custody",
                "jail",
                "woman",
                "child",
                "scheduled caste",
                "workman",
                "income",
                "eligibility",
            ],
            "13": ["entitlement", "affidavit", "income", "prima facie"],
        },
    },
    {
        "source_id": "bihar-prohibition-excise-act-2016",
        "file": "bihar-prohibition-excise-act-2016-gazette.pdf",
        "url": "https://betastate.bihar.gov.in/file_2/FileUpload/2024/Aug/30-Aug-2024/27/Publication/3b1a1656-f2b6-4236-bf03-4f82b8c88e4a.pdf",
        "title": "Bihar Prohibition and Excise Act, 2016 (as published in 2016)",
        "publisher": "Government of Bihar (Bihar Gazette, Extraordinary)",
        "layout": "inline",
        "body_pages": (26, 49),
        "english_pages_with_hindi_headers": True,
        "domain": "criminal",
        "jurisdiction": "Bihar",
        "state_terms": BIHAR_TERMS,
        "effective_date": "2016-10-02",
        "limitations": "Original text as published in the Bihar Gazette on 2 October 2016. The "
        "Act was amended in 2018 and 2022 (including penalties, bail, confiscation and release "
        "of vehicles); this text does not include those amendments. Do not state a penalty "
        "from it as current law without the amended text.",
        "tags": LIQUOR + ["bihar"],
        "sections": {
            "13": ["prohibited", "possession", "transport", "consumption"],
            "30": ["penalty", "transport", "possession", "punishment"] + VEHICLE,
            "32": ["presumption", "possession", "burden"],
            "50": ARREST + ["vexatious", "illegal arrest", "officer", "penalty"],
            "74": ARREST + ["without warrant", "vehicle", "detain"],
            "80": ARREST + ["production", "magistrate", "special court"],
        },
    },
    {
        "source_id": "patna-hc-kalam-ansari-2024",
        "file": "patna-hc-kalam-ansari-2024.pdf",
        "url": "https://patnahighcourt.gov.in/viewjudgment/NiMxMTE4OCMyMDI0IzEjTg==-ja8st4y4P--am1--k=",
        "title": "Kalam Ansari v. State of Bihar, Patna High Court, Cr. Misc. No. 11188 of 2024 "
        "(22 May 2024)",
        "publisher": "Patna High Court",
        "layout": "judgment",
        "domain": "criminal",
        "jurisdiction": "Bihar",
        "state_terms": BIHAR_TERMS,
        "effective_date": "2024-05-22",
        "limitations": "Single-judge judgment quoting sections 56, 60 and 57B of the Bihar "
        "Prohibition and Excise Act, 2016 and Rule 12A of the 2021 Rules as they stood on 22 May "
        "2024. Check later amendments and rulings.",
        "tags": LIQUOR + VEHICLE + ["bihar", "collector", "penalty", "insurance value"],
        "source_hierarchy_tier": 2,
        "paragraphs": {
            "8": ["confiscation", "section 56"],
            "9": ["section 57b", "release on penalty"],
            "10": ["rule 12a", "penalty", "insured value", "form iv", "owner"],
            "11": ["court jurisdiction", "section 60"],
            "12": ["application", "release"],
            "14": ["compensation", "illegal seizure", "article 300a"],
        },
    },
    {
        "source_id": "code-on-wages-2019",
        "file": "code-on-wages-2019-labour.pdf",
        "url": "https://www.labour.gov.in/static/uploads/2025/06/c328da14bbb15fc4ad571dc33e7a4ab3.pdf",
        "title": "Code on Wages, 2019",
        "publisher": "Ministry of Labour and Employment (Gazette of India)",
        "layout": "gazette_margin",
        "domain": "employment",
        "jurisdiction": "India",
        "effective_date": "2025-11-21",
        "limitations": "Gazette text as enacted on 8 August 2019. PIB announced that the four "
        "Labour Codes took effect on 21 November 2025; state rules and the notified authorities "
        "vary by state.",
        "tags": WAGES + ["code on wages", "labour"],
        "sections": {
            "17": [
                "time limit",
                "payment",
                "resigned",
                "dismissed",
                "two working days",
                "full and final",
            ],
            "18": ["deductions", "cut", "fine"],
            "45": ["claims", "authority", "unpaid", "complaint", "labour commissioner"],
        },
    },
]


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tidy(text):
    """Whitespace-only normalisation that keeps clause structure readable."""
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1-", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n(?!\(\w{1,4}\)|Provided|Explanation|Illustration)", " ", text)
    return re.sub(r" {2,}", " ", text).strip()


def pages_text(pdf, first, last):
    return "\n".join(pdf[i].get_text() for i in range(first - 1, min(last, pdf.page_count)))


def arrangement(pdf, first, last):
    text = re.sub(r"P a g e\s*\|\s*\d+", " ", pages_text(pdf, first, last))
    flat = re.sub(r"\s+", " ", text)
    found = {}
    for m in re.finditer(
        r"(?<![\w(])(\d{1,3}[A-Z]?)\.\s+(.+?)(?=\s+\d{1,3}[A-Z]?\.\s+[A-Z]|$)", flat
    ):
        head = re.sub(r"\s+(?:CHAPTER\s+[IVXLC]+|[A-Z][A-Z ,.'’—-]{6,}).*$", "", m.group(2)).strip()
        found.setdefault(m.group(1), head.rstrip("."))
    return found


def heading_above_sections(src, pdf):
    heads = arrangement(pdf, *src["arrangement_pages"])
    body = re.sub(r"P a g e\s*\|\s*\d+", " ", pages_text(pdf, *src["body_pages"]))
    starts = {}
    for m in re.finditer(r"(?m)^\s*(\d{1,3}[A-Z]?)\.\s+(?=\(1\)|[A-Z])", body):
        num = m.group(1)
        head_words = set(re.findall(r"[a-z]{3,}", heads.get(num, "").casefold()))
        before = set(re.findall(r"[a-z]{3,}", body[max(0, m.start() - 260) : m.start()].casefold()))
        score = len(head_words & before) / max(1, len(head_words))
        if score >= 0.6 and (num not in starts or score > starts[num][1]):
            starts[num] = (m.start(), score)
    out = {}
    for num in src["sections"]:
        if num not in starts:
            raise SystemExit(f"{src['source_id']}: section {num} not found")
        begin = starts[num][0]
        later = sorted(pos for pos, _ in starts.values() if pos > begin)
        end = later[0] if later else len(body)
        chunk = body[begin:end]
        nxt = next((n for n, (p, _) in starts.items() if p == end), None)
        if nxt:  # drop the following section's heading lines from the tail
            first_words = " ".join(heads[nxt].split()[:3]).casefold()
            flat = re.sub(r"\s+", " ", chunk)
            cut = flat.casefold().rfind(first_words)
            if cut > 0:
                chunk = flat[:cut]
        out[num] = (heads[num], tidy(chunk))
    return out


FOOTNOTE_RE = re.compile(
    r"(?m)^\s*\d+\.\s+(?:The words?\b|Subs\.|Ins\.|Omitted\b|Added\b|Rep\.|Inserted\b|Substituted\b).*$"
)


def inline_sections(src, pdf):
    raw = pages_text(pdf, *src["body_pages"])
    raw = FOOTNOTE_RE.sub("", raw)
    raw = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", raw)
    if src.get("english_pages_with_hindi_headers"):
        # Bilingual Gazette: page headers are Devanagari fragments; the Act text is English.
        raw = re.sub(r"(?m)^.*[ऀ-ॿ].*$", "", raw)
    raw = re.sub(r"(?<![\w\]])\d{1,2}\[", "[", raw)
    # A heading may wrap onto a second line before its dash.
    pattern = re.compile(
        r"(?m)^\s*(\d{1,3}[A-Z]?)\.\s*([A-Z][^\n]{1,200}?(?:\n[^\n]{1,120}?)?)\s*[.,]?\s*[-–—]{1,2}"
    )
    starts = [
        (m.group(1), m.start(), m.group(2).strip().rstrip(".")) for m in pattern.finditer(raw)
    ]
    out = {}
    for num in src["sections"]:
        matches = [i for i, s in enumerate(starts) if s[0] == num]
        if not matches:
            raise SystemExit(f"{src['source_id']}: section {num} not found")
        i = matches[0]
        end = starts[i + 1][1] if i + 1 < len(starts) else len(raw)
        chunk = re.sub(r"(?m)^\s*CHAPTER\s+[IVXLC]+\s*$\n?.*$", "", raw[starts[i][1] : end])
        out[num] = (re.sub(r"\s+", " ", starts[i][2]), tidy(chunk))
    return out


def gazette_margin_sections(src, pdf):
    """Gazette layout: body in the central column, section headings in the side margins."""
    blocks, margins = [], []
    for pno, page in enumerate(pdf):
        for x0, y0, x1, _, text, *_ in page.get_text("blocks"):
            if "GAZETTE OF INDIA" in text:
                continue
            if x1 < 112 or x0 > 480:
                if not re.fullmatch(r"\s*\d+ of \d{4}\.\s*", text):
                    margins.append((pno, y0, re.sub(r"\s+", " ", text).strip().rstrip(".")))
            else:
                blocks.append((pno, y0, text))
    out = {}
    for num in src["sections"]:
        idx = next((i for i, (_, _, t) in enumerate(blocks) if re.match(rf"\s*{num}\.\s", t)), None)
        if idx is None:
            raise SystemExit(f"{src['source_id']}: section {num} not found")
        nxt = str(int(num) + 1)
        end = next(
            (j for j in range(idx + 1, len(blocks)) if re.match(rf"\s*{nxt}\.\s", blocks[j][2])),
            len(blocks),
        )
        chunk = re.sub(
            r"(?m)^\s*CHAPTER\s+[IVXLC]+\s*$\n?.*$", "", "\n".join(b[2] for b in blocks[idx:end])
        )
        pno, y0, _ = blocks[idx]
        near = [m for m in margins if m[0] == pno and abs(m[1] - y0) < 60]
        heading = min(near, key=lambda m: abs(m[1] - y0))[2] if near else f"Section {num}"
        out[num] = (heading, tidy(chunk))
    return out


def judgment_paragraphs(src, pdf):
    raw = "\n".join(page.get_text() for page in pdf)
    raw = re.sub(r"(?m)^\s*Patna High Court .*$|^\s*\d+/\d+\s*$", "", raw)
    starts = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^\s*(\d{1,2})\.\s", raw)]
    out = {}
    for num in src["paragraphs"]:
        i = next((k for k, s in enumerate(starts) if s[0] == num), None)
        if i is None:
            raise SystemExit(f"{src['source_id']}: paragraph {num} not found")
        end = next((p for n, p in starts[i + 1 :] if int(n) == int(num) + 1), len(raw))
        out[num] = (f"Para {num}", tidy(raw[starts[i][1] : end]))
    return out


LAYOUTS = {
    "heading_above": heading_above_sections,
    "inline": inline_sections,
    "gazette_margin": gazette_margin_sections,
    "judgment": judgment_paragraphs,
}


def build(originals=ORIGINALS):
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    sources, passages = [], []
    for src in SOURCES:
        path = originals / src["file"]
        pdf = fitz.open(path)
        units = LAYOUTS[src["layout"]](src, pdf)
        sources.append(
            {
                "source_id": src["source_id"],
                "title": src["title"],
                "publisher": src["publisher"],
                "canonical_url": src["url"],
                "original_file": src["file"],
                "original_sha256": sha256_file(path),
                "retrieved_at": retrieved_at,
            }
        )
        judgment = src["layout"] == "judgment"
        keywords = src.get("paragraphs") or src["sections"]
        for num, (heading, text) in units.items():
            locator = heading if judgment else f"Section {num}: {heading}"
            passages.append(
                {
                    "passage_id": f"pack-{src['source_id']}-{'para' if judgment else 's'}{num.lower()}",
                    "source_id": src["source_id"],
                    "title": src["title"],
                    "locator": locator,
                    "text": text,
                    "canonical_url": src["url"],
                    "retrieved_at": retrieved_at,
                    "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "origin": "official_pack",
                    "source_type": "indian_official",
                    "verification_status": "official_text_not_lawyer_reviewed",
                    "limitations": f"{src['limitations']} {NOT_REVIEWED}",
                    "jurisdiction": src["jurisdiction"],
                    "state_terms": src.get("state_terms", []),
                    "domain": src["domain"],
                    "effective_date": src["effective_date"],
                    "publication_date": src["effective_date"] if judgment else None,
                    "source_hierarchy_tier": src.get("source_hierarchy_tier", 2),
                    "keywords": sorted(set(src["tags"] + keywords[num])),
                }
            )
    return {
        "version": "official-law-packs-v1",
        "built_at": retrieved_at,
        "review_status": "official_text_not_lawyer_reviewed",
        "sources": sources,
        "passages": passages,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    pack = build()
    args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n")
    print(
        f"Wrote {len(pack['passages'])} passages from {len(pack['sources'])} sources to {args.out}"
    )


if __name__ == "__main__":
    main()
