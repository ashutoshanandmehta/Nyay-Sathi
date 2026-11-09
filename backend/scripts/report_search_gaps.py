"""Offline report: which official web pages answers keep citing, and what web search costs.

Pages cited again and again are candidates for the official law packs (added by a person, like
the BNSS and Bihar packs), after which those questions need no live search at all. Read-only;
no model or network call. Search queries themselves are not stored, by design, so the report
works from cited sources and call telemetry.

    cd backend && .venv/bin/python -I scripts/report_search_gaps.py [path/to/nyay_saathi.sqlite3]
"""

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_DB = Path(__file__).resolve().parents[2] / "runtime" / "nyay_saathi.sqlite3"


def report(db_path: Path) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cited: Counter = Counter()
    details: dict[str, dict] = {}
    turns = 0
    for (meta_json,) in conn.execute("SELECT metadata_json FROM messages WHERE role='assistant'"):
        turns += 1
        meta = json.loads(meta_json or "{}")
        for src in {s.get("canonical_url"): s for s in meta.get("sources") or []}.values():
            if src.get("origin") != "web" or not src.get("canonical_url"):
                continue
            url = src["canonical_url"]
            cited[url] += 1
            details.setdefault(url, {"title": src.get("title") or "", "locator": src.get("locator") or ""})

    searches_per_turn: dict[str, int] = defaultdict(int)
    search_input = search_calls = 0
    for request_id, payload_json in conn.execute("SELECT request_id, payload_json FROM model_call_events"):
        payload = json.loads(payload_json or "{}")
        if payload.get("stage") != "web_search":
            continue
        search_calls += 1
        searches_per_turn[request_id] += 1
        search_input += (payload.get("usage_reported") or {}).get("input_tokens") or 0
    conn.close()

    lines = [f"# Web search report ({db_path.name})", ""]
    with_search = len(searches_per_turn)
    lines.append(
        f"- Assistant turns: {turns}; turns that searched: {with_search}; web searches: {search_calls}"
    )
    if search_calls:
        lines.append(
            f"- Search input tokens: {search_input:,} total, {search_input // search_calls:,} per search, "
            f"{search_calls / with_search:.1f} searches per searching turn"
        )
    lines += ["", "## Official pages cited more than once (pack candidates)", ""]
    repeated = [(url, n) for url, n in cited.most_common() if n > 1]
    if not repeated:
        lines.append("None yet.")
    else:
        lines.append("| Times cited | Site | Page | Where |")
        lines.append("|---|---|---|---|")
        for url, n in repeated:
            d = details[url]
            lines.append(
                f"| {n} | {urlparse(url).hostname} | [{d['title'][:60]}]({url}) | {d['locator'][:60]} |"
            )
    lines += ["", "## Sites cited", ""]
    hosts = Counter()
    for url, n in cited.items():
        hosts[urlparse(url).hostname] += n
    lines += [f"- {host}: {n}" for host, n in hosts.most_common()] or ["None yet."]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB))
