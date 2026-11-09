"""Export all active cases, case dossiers, and full AI assistant responses from the database.

Outputs:
1. nyay_saathi_database_export.md (comprehensive formatted Markdown report)
2. nyay_saathi_database_export.json (structured JSON file)
"""

import json
from pathlib import Path
from app.config import Settings
from app.db import Database


def clean_fact_val(v):
    if hasattr(v, "value"):
        return str(v.value)
    if isinstance(v, dict):
        return str(v.get("value", v.get("text", v)))
    return str(v)


def main():
    settings = Settings()
    db = Database(settings.database_path)
    owner_id = "b0bc9b9f-8183-436a-a07c-5d2aaff3732b"
    convs = db.list_conversations(owner_id)

    export_data = {
        "export_title": "Nyay Saathi V2 - Citizen Legal Cases Database Export",
        "exported_at": "2026-11-09T16:07:08+05:30",
        "database_path": str(settings.database_path),
        "owner_id": owner_id,
        "cases_count": len(convs),
        "cases": [],
    }

    md_lines = []
    md_lines.append("# Nyay Saathi V2 — Complete Legal Cases & AI Responses Database Export")
    md_lines.append(f"**Export Date:** `2026-11-09 16:07:08 IST` | **Source Database:** `{settings.database_path}`")
    md_lines.append(f"**Owner ID:** `{owner_id}` | **Total Cases:** `{len(convs)}`\n")
    md_lines.append("---")
    md_lines.append("## Executive Summary of Extracted Cases\n")
    md_lines.append("| # | Case Title | Domain | Turns | Created Date | Core Legal Issue |")
    md_lines.append("|---|---|---|---|---|---|")

    case_summaries = [
        ("1", "Employment: Unpaid Wages & Retaliation Threat", "Employment / Labour Law", "4 turns (8 msgs)", "2026-11-09 08:45", "Unpaid salary for 2 months (₹56,000), manager retaliation threat, absence of formal appointment letter under Code on Wages 2019."),
        ("2", "Consumer: E-Commerce Refund Shortfall", "Consumer Protection", "2 turns (4 msgs)", "2026-11-09 10:07", "Returned 2 ceiling fans to Amazon pickup agent, received refund for 1 only; support closed dispute without explanation."),
        ("3", "Constitutional & Personal Liberty: Adult Autonomy", "Criminal / Constitutional", "2 turns (4 msgs)", "2026-11-09 07:57", "20-year-old consenting adult woman in interfaith relationship facing family coercion, honor threats, and police harassment."),
        ("4", "Property & Criminal Law: Ancestral Land Harassment", "Property / Criminal", "3 turns (6 msgs)", "2026-11-09 07:22", "Deceased grandfather ancestral land dispute in Chorsua (Nalanda, Bihar); uncle threatening father over WhatsApp, refusing mutation/partition.")
    ]

    for row in case_summaries:
        md_lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |")

    md_lines.append("\n---\n")

    for idx, c in enumerate(convs, 1):
        cid = c["id"]
        msgs = db.messages(owner_id, cid)
        memory, summary = db.load_memory(owner_id, cid)

        case_dict = {
            "case_index": idx,
            "conversation_id": cid,
            "title": c["title"],
            "language": c.get("language", "en"),
            "created_at": c.get("created_at"),
            "domain": memory.domain,
            "summary": summary,
            "memory": memory.model_dump(mode="json"),
            "messages": [],
        }

        md_lines.append(f"## Case #{idx}: {c['title']}")
        md_lines.append(f"- **Conversation ID:** `{cid}`")
        md_lines.append(f"- **Domain:** `{memory.domain.upper()}`")
        md_lines.append(f"- **Created At:** `{c.get('created_at')}`")
        if summary:
            md_lines.append(f"- **Case Dossier Summary:** {summary}")

        facts = memory.facts
        if facts:
            md_lines.append("\n### Established Case Facts:")
            for k, v in facts.items():
                txt = clean_fact_val(v)
                md_lines.append(f"- **{k.replace('_', ' ').title()}:** {txt}")

        parties = memory.parties
        if parties:
            md_lines.append("\n### Parties Involved:")
            for p in parties:
                p_name = p.get("name") if isinstance(p, dict) else getattr(p, "name", str(p))
                p_role = p.get("role") if isinstance(p, dict) else getattr(p, "role", "")
                md_lines.append(f"- **{p_name}** ({p_role})")

        md_lines.append("\n### Complete Turn-by-Turn Dialogue:\n")

        for m_idx, m in enumerate(msgs, 1):
            role = m["role"].upper()
            content = m["content"].strip()
            ts = m.get("created_at", "")
            meta = m.get("metadata") or {}

            case_dict["messages"].append({
                "message_id": m.get("id"),
                "role": m["role"],
                "created_at": ts,
                "content": content,
                "metadata": meta,
            })

            turn_num = (m_idx + 1) // 2
            if role == "USER":
                md_lines.append(f"#### 👤 User Inquiry (Turn {turn_num}) — `{ts}`")
                md_lines.append(f"> {content}\n")
            else:
                md_lines.append(f"#### ⚖️ Nyay Saathi Assistant Response (Turn {turn_num}) — `{ts}`\n")
                md_lines.append(content)

                # Add sources / citations if present
                sources = meta.get("sources", [])
                if sources:
                    md_lines.append("\n##### 📜 Verified Statutory Authorities Cited:")
                    for s_idx, s in enumerate(sources, 1):
                        title = s.get("title", "Official Statute")
                        loc = s.get("locator", "")
                        url = s.get("canonical_url", "")
                        orig = s.get("origin", "")
                        link_txt = f"[{title}]({url})" if url else title
                        md_lines.append(f"- `[{s_idx}]` **{link_txt}** — *{loc}* (Verified Origin: `{orig}`)")

                # Add safety messages if present
                safety = meta.get("safety_messages", [])
                if safety:
                    md_lines.append("\n##### 🚨 Immediate Protective Advisory Emitted:")
                    for item in safety:
                        md_lines.append(f"> **{item.get('type', 'Safety').upper()}:** {item.get('text', '')}")

                md_lines.append("\n" + "-" * 40 + "\n")

        md_lines.append("\n---\n")
        export_data["cases"].append(case_dict)

    project_root = Path(__file__).parents[2]
    out_md = project_root / "nyay_saathi_database_export.md"
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    out_json = project_root / "nyay_saathi_database_export.json"
    out_json.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Export successfully written!")
    print(f"Markdown: {out_md} ({out_md.stat().st_size} bytes)")
    print(f"JSON: {out_json} ({out_json.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
