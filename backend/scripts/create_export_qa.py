from pathlib import Path

from app.schemas.models import CaseFact, CaseMemory, FactStatus, Provenance
from app.services.exports import export_payload, write_docx, write_pdf

root = Path(__file__).parents[2]
out = root / "output" / "qa"
out.mkdir(parents=True, exist_ok=True)
memory = CaseMemory(
    version=4,
    domain="consumer",
    facts={
        "amount": CaseFact(
            key="amount",
            value="₹8,000",
            status=FactStatus.CONFIRMED,
            provenance=[Provenance(source_type="message", source_id="synthetic-message-2")],
        ),
        "issue_type": CaseFact(key="issue_type", value="defective_goods"),
        "seller": CaseFact(key="seller", value="उदाहरण विक्रेता"),
    },
    contradictions=[{"description": "राशि पहले ₹18,000 बताई गई थी और फिर ₹8,000 सही की गई।"}],
    unknowns=["डिलीवरी की सही तारीख"],
    requested_remedy="पूरा रिफंड",
)
conversation = {
    "id": "synthetic-qa-case",
    "title": "खराब फोन का रिफंड",
    "language": "hi",
    "created_at": "2026-11-05T00:00:00Z",
    "updated_at": "2026-11-05T00:05:00Z",
}
payload = export_payload(
    conversation,
    memory,
    "उपयोगकर्ता ने खराब फोन के लिए ₹8,000 का रिफंड माँगा है। राशि में किया गया सुधार दर्ज है।",
    [
        {
            "id": "synthetic-answer",
            "role": "assistant",
            "content": "Synthetic QA only",
            "created_at": "2026-11-05T00:04:00Z",
            "metadata": {
                "sources": [
                    {
                        "source_id": "nch-about",
                        "passage_id": "nch-prelitigation",
                        "title": "National Consumer Helpline About",
                        "locator": "About portal",
                        "canonical_url": "https://consumerhelpline.gov.in/public/index.php/about",
                    }
                ]
            },
        }
    ],
    [
        {
            "id": "synthetic-evidence",
            "filename": "रसीद.pdf",
            "mime_type": "application/pdf",
            "extraction_status": "complete",
        }
    ],
    [
        {
            "id": "synthetic-draft",
            "title": "विक्रेता को ईमेल",
            "content": "कृपया ₹8,000 का रिफंड दें।",
            "version": 2,
            "status": "working",
            "case_version": 4,
        }
    ],
)
write_docx(out / "nyay-saathi-case-pack-qa.docx", payload)
write_pdf(out / "nyay-saathi-case-pack-qa.pdf", payload)
print(out)
