# Plan: add missing official law texts + fix answer structure

For: the agent implementing this (Antigravity). Written by Claude Code, 2026-11-09.
Repo: `~/Downloads/Nyay Sathi V2`, branch `snapshot/2026-11-08-hardening-and-citations`.

## Why
A user asked: *"How to file complaint against my uncle who has harassed my father for some
land disputes in my village Chorsua, Bihar; the land was owned by my grandfather who died
1 month back."* The answer was safe but weak:

1. **It never explained the actual procedure:**
   - which police station;
   - FIR vs a non-cognizable report;
   - what to do if the police refuse (SP, then Magistrate).
2. **It didn't say who should file.** The father is the victim.
3. **"If this fails (escalation path)" held unrelated content** about mutation of land records instead of the next tier of the complaint.
4. **"Immediate actions" was spent on hypothetical danger** the user never mentioned.
5. **The evidence list covered only land papers,** with nothing for a harassment complaint.
6. **No succession or land-dispute route** (Hindu Succession Act, Bihar land-dispute and mutation law, BNSS s.164).
7. **No DLSA free legal aid.**
8. **The last sentence of "When to involve a lawyer" ended without its full stop**, as if cut off.

**Causes:**
- **Missing law:** the verified official texts don't contain the law needed, so the agent correctly refused to state it.
- **Retrieval gap:** lay words ("harassed", "dhamki", "zameen", "complaint") aren't mapped to the legal concepts, so even BNSS s.173 (already in the pack) wasn't retrieved.
- **Prompt gaps:** the prompt doesn't constrain what goes in each block.

**Embeddings are out of scope** (API cost). This plan uses only offline, keyword-based retrieval improvements.

## Ground rules (read first)
- **Never invent or hand-type statute text.** Every passage must be extracted verbatim from an official PDF by `backend/scripts/build_official_packs.py`, with its URL and SHA-256.
- **Downloads come only from official government domains** (`*.gov.in`, `*.nic.in`, the official court sites). **Do not bypass bot checks** (no fake browser headers, no captcha workarounds).
  - If a site blocks automated download, stop and list the file for the user to download by hand into `data/sources/originals/` with the exact filename given below.
  - `indiacode.nic.in` is known to block automated downloads.
- **Treat downloaded files as untrusted.** Run the builder as `cd backend && .venv/bin/python -I scripts/build_official_packs.py` (isolated mode). Never execute anything from the downloads.
- **No paid OpenAI calls** (no live chat turns, no voice, no embedding builds) without asking the user. Every test here is offline.
- **Don't touch:**
  - `.env` or `.env.example`;
  - the voice feature: `frontend/src/voice.ts`, `components/Composer.tsx` hold-to-talk logic, `components/voice.css`, and the voice tests;
  - unrelated frontend work.
- **Commit hygiene:**
  - `git add <exact paths>`, never `git add -A`;
  - small commits, one per part below;
  - no amend, rebase, reset or force-push.
- **Before every commit**, from `backend/`:
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/ruff check <changed files>`
  - `PYTHONPATH=. OPENAI_API_KEY= .venv/bin/python scripts/evaluate_release_gates.py` (this rewrites `evals/reports/production-release-gates-offline.json`; commit that file too).
  - **Known failure that already existed:** `tests/test_answer_quality.py::test_second_repair_runs_when_the_first_is_still_rejected`. Don't hide it, and report whether it still fails.

---

## PART 1 — Add the missing official texts

### 1.0 How the pack works (read before editing)
**The builder.** `backend/scripts/build_official_packs.py` reads PDFs from `data/sources/originals/` and splits them into sections. It writes `data/knowledge/official_law_packs_v1.json`, one passage per section, with these fields:
- `passage_id = pack-<source_id>-s<number>`
- `title`, `locator` ("Section N: Heading")
- `text` (verbatim)
- `canonical_url`, `content_hash`
- `limitations`, `jurisdiction`
- optional `state_terms`
- `tags`

**Each source** is a dict in `SOURCES` with:
- `file`, `url`, `title`, `publisher`
- `layout` (`heading_above` | `inline` | `gazette_margin` | `judgment`)
- page ranges, `domain`, `jurisdiction`, `effective_date`, `limitations`
- `tags`, and `sections: {number: [extra lay keywords]}` (or `paragraphs` for judgments).

**How the pack is used.** `backend/app/knowledge/search_index.py` (`OpenSearchLegalIndex`) loads the pack into a local BM25 index.
- Sources with `state_terms` (Bihar) are only returned when the question names that state or a listed city.
- `backend/app/agent/runner.py::_pre_retrieve_certified` pulls pack passages into every turn:
  - a limit of 12 with a 0.65 relative floor;
  - plus one small lookup per matched concept from `CONCEPT_EXPANSIONS`.

**Tags matter.** BM25 matches on passage text plus tags, so lay keywords in `sections[...]` are how "dhamki" finds criminal intimidation.

### 1.1 BNSS 2023: add sections (PDF already downloaded: `bnss-2023-ncrb.pdf`)
In the existing `bnss-2023` source, add to `sections`:

| Section | Expected heading (verify against the PDF) | Lay keywords to add |
|---|---|---|
| 164 | Procedure where dispute concerning land or water is likely to cause breach of peace | land, zameen, jameen, khet, plot, boundary, kabza, possession, dispute, jhagda, breach of peace, SDM, executive magistrate |
| 174 | Information as to non-cognizable cases and investigation of such cases | NCR, non-cognizable, police refused, complaint not registered, minor offence, magistrate permission |
| 175 | Police officer's power to investigate cognizable case | 175(3), magistrate order investigation, police not acting, FIR not registered |
| 223 | Examination of complainant | complaint to magistrate, private complaint, court complaint, parivad |

Also widen the keywords of the existing **173** with: shikayat, शिकायत, complaint, police refused, superintendent of police, SP, written complaint, harassment.

**Acceptance:** the builder prints each section and the heading text matches the table. If a heading differs, **stop and report**. Don't guess section numbers.

### 1.2 Bharatiya Nyaya Sanhita, 2023 (new source)
- **Download:** the official BNS 2023 PDF.
  - **Preferred:** NCRB's Sankalan portal, the same family of URLs as the BNSS file: `https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/...`.
  - **Otherwise:** the Ministry of Home Affairs or the Gazette of India (egazette.gov.in).
  - Save as `data/sources/originals/bns-2023-ncrb.pdf`.
- **Source config:**
  - `source_id: "bns-2023"`, `domain: "criminal"`, `jurisdiction: "India"`;
  - `effective_date: "2024-07-01"`;
  - `limitations`: "From the official BNS 2023 text (in force from 1 July 2024). Whether conduct is an offence depends on the facts; check amendments."
  - Determine the `layout` by inspecting the PDF; it's probably `heading_above` like the BNSS.

| Section | Expected heading (verify) | Lay keywords |
|---|---|---|
| 115 | Voluntarily causing hurt | maar-peet, beat, hit, assault, injury, chot |
| 126 | Wrongful restraint | stopped, blocked, rasta roka, restraint |
| 324 | Mischief | damage, nuksan, destroyed, crops, fence, property damage |
| 329 | Criminal trespass and house-trespass | trespass, ghus, entered land, encroachment, kabza |
| 351 | Criminal intimidation | threat, dhamki, धमकी, threatened, jaan se marne ki dhamki, harass, pareshan |
| 352 | Intentional insult with intent to provoke breach of peace | abuse, gaali, insult, provoke |

If any heading differs from the table, stop and report.

### 1.3 Hindu Succession Act, 1956 (new source)
- **Download:** the official text from India Code or the Legislative Department.
  - India Code blocks bots, so **ask the user** to download it by hand.
  - Filename: `data/sources/originals/hindu-succession-act-1956.pdf`.
  - Record the URL they used.
- **Source config:**
  - `source_id: "hindu-succession-act-1956"`, `domain: "property"`, `jurisdiction: "India"`;
  - `limitations`: "Applies to Hindus, Buddhists, Jains and Sikhs. Shares depend on all surviving heirs, any will, and whether the property was ancestral/coparcenary or self-acquired; amended in 2005."
- **Sections:**
  - **6** (devolution of interest in coparcenary property): ancestral, coparcenary, joint family, daughter, 2005;
  - **8** (general rules of succession in the case of males): grandfather died, father died, inheritance, waris, wirasat, share, hissa;
  - **9** (order of succession among heirs in the Schedule);
  - **10** (distribution of property among heirs in class I of the Schedule): equal share, sons, daughters, widow, mother;
  - the **Schedule (Class I heirs)**, if the builder can extract it as one passage. If not, skip it and note that.
- **Tags:** inheritance, succession, property, zameen, land, batwara, partition, heirs, uttaradhikar, उत्तराधिकार, विरासत.

### 1.4 Bihar land law (new sources, Bihar `state_terms`)
- **Bihar Land Disputes Resolution Act, 2009:**
  - Official PDF from the Bihar Revenue & Land Reforms Department or the Bihar Gazette (`state.bihar.gov.in`, `lrc.bih.nic.in`, `egazette.bih.nic.in` or similar official domains);
  - file `bihar-land-disputes-resolution-act-2009.pdf`.
  - **Pick sections by heading** (record the numbers you find):
    - the definitions of "competent authority" and the kinds of disputes covered;
    - the provision giving the competent authority (DCLR) power to decide disputes;
    - the procedure for application and hearing;
    - appeal or revision.
- **Bihar Land Mutation Act, 2011 (dakhil kharij):**
  - same domains; file `bihar-land-mutation-act-2011.pdf`.
  - **Pick by heading:** application for mutation (including on succession or inheritance), objections, time limit if stated, appeal.
- **Config for both:**
  - `jurisdiction: "Bihar"`, `state_terms: BIHAR_TERMS`, `domain: "property"`;
  - `limitations`: "Original text as published; check later amendments and the current online process (Bihar Bhumi) with the Circle Office."
- **Tags:**
  - for both: zameen, jameen, land, khet, plot, raiyat, jamabandi, dakhil kharij, दाखिल खारिज, mutation, circle office, anchal, CO, DCLR, land dispute, bhumi vivad;
  - add `"chorsua"`-style village names to neither (the state filter already needs "Bihar" or a city).
- **If these Acts can't be found on an official domain, skip them** and report. Don't use third-party sites.

### 1.5 Builder changes
- **New layouts:** if a new PDF doesn't fit an existing `layout`, add the smallest possible new layout handler in the builder (stdlib + PyMuPDF only), modelled on the existing ones. Keep the "sections accepted only in sequence" safety rule.
- **Schema:** the pack JSON schema stays the same. Bump nothing except adding passages.
- **Rebuild:** run the builder, then confirm:
  - every new passage has non-empty `text`, a `locator` "Section N: Heading", a `canonical_url` on an official domain, and a `content_hash`;
  - no passage text is shorter than 80 characters, unless the section really is short (print and check those).

### 1.6 Lay-word concept mappings (`backend/app/agent/runner.py`, `CONCEPT_EXPANSIONS`)
**Note:** `runner.py` has a small uncommitted edit by the user (3 lines). Make your change around it and don't revert it.

Each entry is `(regex over the user's words, "legal terms to search")`. Follow the existing style: English, Hinglish and Devanagari alternatives in one regex.

| User words (regex alternatives) | Search terms |
|---|---|
| complaint, shikayat, शिकायत, FIR, thana, police station, report to police | `information cognizable offence police station complaint superintendent` |
| police refused, FIR nahi likha, not registering, complaint not taken | `non-cognizable information superintendent magistrate investigate` |
| harass, pareshan, परेशान, threat, dhamki, धमकी, abuse, gaali, beat, maar-peet, मारपीट | `criminal intimidation hurt wrongful restraint insult breach of peace` |
| land, zameen, jameen, ज़मीन, जमीन, khet, plot, kabza, boundary, encroach | `land dispute possession breach of peace trespass mutation` |
| died, death, expired, guzar gaye, inheritance, wirasat, waris, hissa, batwara, partition, property share | `succession heirs inheritance class I share coparcenary mutation` |
| lawyer fees, free lawyer, can't afford, vakil ka paisa | `free legal aid legal services criteria` (an LSA s.12 mapping may already exist; extend it) |

### 1.7 Part 1 tests (new file `backend/tests/test_legal_coverage.py`)
Use `OpenSearchLegalIndex(Settings(openai_api_key=None), None)` with no network, as `tests/test_practice.py::test_coach_safeguards_are_verified_passages_only` does.

1. **The pack has the new passages.** Each expected `passage_id` is present with a non-empty text and the expected heading in `locator`, for BNSS 164/174/175/223, BNS 115/126/324/329/351/352, HSA 6/8/10, and the Bihar Acts you added. Skip a source cleanly with `pytest.skip` if its original wasn't available, mirroring `test_real_bihar_gazette_splits_into_its_hundred_sections` in `tests/test_research_quality.py`, so CI works without the PDFs.
2. **Pre-retrieval for the real question.** Build a minimal `state` and call `PrimaryAgent._pre_retrieve_certified` (see the existing tests in `tests/test_answer_quality.py` for how they construct the agent offline) with the exact user message above. Assert `state["passages"]` contains:
   - BNSS s.173;
   - BNS s.351;
   - at least one of BNSS s.164 or a Bihar land Act passage;
   - HSA s.8 (if downloaded);
   - LSA s.12.
3. **Hinglish:** `"chacha zameen ke liye papa ko dhamki de rahe hain, thana mein shikayat kaise karein, Bihar"` → BNS s.351 and BNSS s.173.
4. **State filter:** the same land question naming **Uttar Pradesh** instead of Bihar returns **no** Bihar-Act passages.
5. **No false matches:** a consumer refund question returns none of BNS 351, HSA or the Bihar land Acts.
6. **Concept mappings:** each new row in the 1.6 table matches its examples, and does **not** match "landed in Delhi" (word boundaries) or "I'm dying to know".

---

## PART 2 — Answer structure rules + the cut-off sentence

### 2.1 Replace the system prompt with the generic version
Replace the whole of `backend/app/prompts/primary.md` with `docs/plans/primary-prompt-v2.md`, verbatim.
- **What it is:** a generic, issue-agnostic rewrite (no topic-specific rules). It adds:
  - a silent work-it-out procedure: issues → people → goal → route → law → gaps;
  - "how do I…" answers that must cover who, where, what, deadline, what next, and if refused;
  - one job per block (`alternatives` = the next tier of the same route; `immediate_actions` = today, case-specific; `evidence_checklist` matched to the route);
  - a labelled route per issue;
  - safety mentioned only on real risk;
  - claims limited to what their passage says;
  - a practical route even when the law is unverified;
  - complete sentences;
  - a silent final self-check;
  - `legal_issues` phrased as questions for a lawyer.
- **What it keeps:** every term the code and reviewer rely on (block types, grounding labels, `emit_safety` / `research_legal_issue` rules, `urgent_case_continuity`, case-memory patch kinds and domains). Don't rename them.
- **Before replacing:** diff it against the current `primary.md`, and keep any line added since 2026-11-09 by someone else if the new file doesn't cover it. Report anything you keep.

**Prompt tests:** add a test in `backend/tests/test_answer_quality.py` that `primary.md` contains each of these phrases:
- "Work it out before you write"
- "what to do if it is refused or ignored"
- "next tier of the **same** route"
- "only when the user's message suggests a current risk"
- "matched to that route"
- "Before you finish"
- "phrased as questions for a lawyer"
- "knowledgeable friend"
- "never name sources inline"

Also assert `len(primary.md) < 10500` and that every block type and grounding label in `backend/app/agent/contracts.py` appears in it.

**Release gates:** run `scripts/evaluate_release_gates.py` and the full pytest. If an existing test asserts old prompt wording, update that assertion to the new equivalent wording, and say so in the commit message. Don't weaken what it checks.

### 2.2 The cut-off sentence: diagnose, then fix
**Symptom:** the `human_handoff` block ended "…especially if there are serious threats or an urgent risk to possession", with no final full stop.

Already ruled out by reading the code:
- no length slicing in `backend/app/agent/blocks.py` (`compose_blocks` path);
- `MODEL_CITATION_NUMBER_RE` and `strip_citation_markers` don't remove trailing text;
- no CSS line-clamp on `.res-block-human_handoff`.

**Diagnose first** (offline):
1. The user can find the conversation id in the URL (`/chat/<id>`). With the dev backend running, `GET /api/conversations/<id>` in the browser returns the message `metadata.resolution_blocks`. Ask the user to save that JSON, or have them run it, rather than decrypting the database yourself.
2. Compare the `human_handoff` block's `content` with the raw claim text.
3. Pick the matching explanation and fix:
   - **(a) The model wrote it without a full stop** (most likely): handled by the new prompt rule plus the check in 2.3.
   - **(b) The text was cut during repair or review merge:** inspect `runner.py` (the repair loop and `_compose`) for any place that rebuilds claim text, and fix it.
   - **(c) It was cut in the UI:** inspect `frontend/src/components/MessageView.tsx` for slicing of `block.content`.

**Write a regression test for whichever cause you find.**

### 2.3 Mechanical completeness check (`backend/app/agent/verification.py`, `mechanical_checks`)
- **Rule:** a claim whose text, after stripping, doesn't end in `. ? ! : ) ” "` or `]` and isn't a table, list or heading-only line is **sent to repair**, not blocked, with the reason "unfinished sentence".
  - Look at how existing pending reasons are recorded and reuse that path.
  - Don't add a model call; repair already exists and has a budget (`agent_max_repairs`).
- **Templates are exempt:** claims with `kind == "template"` (runtime referral texts) are skipped.
- **Tests** (`tests/test_answer_quality.py`):
  - an unfinished claim becomes pending with that reason;
  - a finished one passes;
  - a markdown list or table passes;
  - a template is untouched.

### 2.4 Block-order sanity (`backend/app/agent/blocks.py`)
- **No ordering change.** Only add a test that when an answer has two `recommended_route` claims with "For the harassment:" and "For the land records:" labels, both appear in the rendered `recommended_route` block, in order.
- **Alternatives stay with their route:** a land-records claim the model put in `alternatives` is **not** moved automatically. That's the prompt's job; do not add heuristics that rewrite model content.

### 2.5 Offline release-gate scenario (`backend/scripts/evaluate_release_gates.py`)
Add one scenario modelled on the existing ones, with the uncle/land/Bihar question and a scripted (fake-provider) answer that follows the new rules. Assert that:
- pre-retrieval contains BNSS 173 and BNS 351;
- the composed answer has a `recommended_route` block with both labels and an `alternatives` block mentioning the Superintendent of Police;
- every claim ends with terminal punctuation.

This keeps the gate offline (it uses fake providers, as the existing scenarios do).

---

---

## PART 3 — Warm, friendly answers instead of legal documents

**The problem.** Answers read like a legal document, not a helpful assistant. Three things cause it:
1. **The prompt asks for precision but says nothing about voice.** The model writes formally ("Stick to what your father personally experienced", "This explains the record-update route but does not determine…") and names sources inline ("(Bihar government guidance on mutation, Page 2.)").
2. **Every block gets a form-like title** from `BLOCK_TITLES` in `backend/app/agent/blocks.py`: "Recommended route", "If this fails (escalation path)", "Evidence to preserve", "Important clarification". The frontend has its own labels too (`frontend/src/icons.ts`).
3. **Every block renders as a bordered card with a grounding pill**, so even a one-line answer looks like a filled-in form.

**Accuracy and verification stay exactly as they are.** This part changes voice and presentation only.

### 3.1 Voice in the prompt
Already done: `docs/plans/primary-prompt-v2.md` includes a `## Voice` section (installed by 2.1). It asks for:
- a knowledgeable-friend tone and one specific human opening line;
- "you" and active voice;
- no legalese, no meta-commentary about sources, and no inline source names (the citation chips do that);
- plain "why";
- honest reassurance;
- one closing offer of further help;
- a natural conversational register in Hindi and Hinglish.

The self-check also asks: "Does it read like a helpful person talking, not a legal document?"

The opening line and closing offer go **inside** existing claims: the first `direct_answer` claim and a final `practical_precaution` claim. **Don't add new block types or claim kinds.**

### 3.2 Conversational section titles (`backend/app/agent/blocks.py`, `BLOCK_TITLES`)
Replace the titles. Keep the keys and the three languages:

| Block | en | hi | hinglish |
|---|---|---|---|
| direct_answer | *(no visible title; see 3.3)* "In short" | "संक्षेप में" | "Short mein" |
| recommended_route | What I'd suggest | मेरी सलाह | Meri salah |
| immediate_actions | What you can do today | आज आप क्या कर सकते हैं | Aaj aap kya kar sakte hain |
| alternatives | If that doesn't work | अगर इससे बात न बने | Agar isse baat na bane |
| evidence_checklist | Keep these ready | ये चीज़ें तैयार रखें | Ye cheezein ready rakhein |
| document | Here's a draft you can use | आपके लिए एक मसौदा | Aapke liye ek draft |
| question | One thing that would help me | एक बात बताइए | Ek baat bataiye |
| limitation | What I can't confirm yet | जो अभी पक्का नहीं है | Jo abhi pakka nahi hai |
| human_handoff | When a lawyer would help | वकील की मदद कब लें | Vakil ki madad kab lein |

**Update the dependent tests.** `backend/tests/test_answer_quality.py:160-161` asserts `"When to involve a lawyer"`; change both assertions to the new title. Search the rest of the backend tests and `scripts/evaluate_release_gates.py` for the old titles and update every assertion. The "Lawyer escalation bundle" UI and its documents are separate and keep their formal wording, because they are written for a lawyer.

### 3.3 Lighter rendering (`frontend/src/components/MessageView.tsx`, `frontend/src/icons.ts`, `frontend/src/styles.css`)
**Coordinate with the ongoing UI refresh.** Build on the current files; don't revert other recent changes.
- **`direct_answer`** renders as the plain lead paragraph of the message, with no card, border, title or pill.
- **Other blocks:**
  - render as light sections: a small icon plus the new title as a subheading, with body text below;
  - **no bordered card per block**;
  - keep one subtle card only for `document` (so the draft is clearly separate and copyable) and for `human_handoff` (with its button).
- **Grounding pills:**
  - show them as a small icon (for example ShieldCheck) with the label in the tooltip and `aria-label`, not a text pill on every block;
  - keep the visible text pill only on `limitation` ("What I can't confirm yet").
- **`icons.ts` labels:** make them match the new titles from 3.2, or read them from the block's `title` field so there's one source of truth.
- **Inline source names:** `formatInlineCitations` in `MessageView.tsx` (it italicises "(Title, Locator)" before a citation) should stop formatting them. If the model still writes one, it shows as plain text. The prompt now forbids them, and the numbered chips stay.
- **Hindi and Hinglish titles** come from the backend `title`; don't hard-code English in the UI.

### 3.4 The reviewer must not punish warmth (`backend/app/prompts/primary-review.md`)
Add one sentence to rule 2 ("Calibrated practical & draft review"): *"A short empathetic opening, plain-language explanation of why a step helps, honest reassurance, and an offer of further help are supported `practical_precaution` content as long as they add no legal rule, entitlement, deadline or promised outcome."* Change nothing else in the reviewer prompt.

### 3.5 Tests
- **Backend:**
  - `BLOCK_TITLES` has the new titles in all three languages;
  - a composed answer's `human_handoff` block title is "When a lawyer would help" (en) and "Vakil ki madad kab lein" (hinglish);
  - the reviewer prompt contains the new sentence;
  - the prompt tests from 2.1 include "knowledgeable friend" and "never name sources inline".
- **Frontend (vitest):**
  - `direct_answer` renders as a paragraph with no heading and no grounding pill;
  - other blocks render their backend `title` as a subheading;
  - a `document` block is still a copyable card;
  - grounding is exposed through `aria-label` on an icon;
  - "(Title, Locator)" before a citation is no longer italicised.
  - Update existing tests that query old titles (`frontend/src/components/resolution.test.tsx`, `components.test.tsx`).
- **Both Playwright suites and the release gates must pass.**

### 3.6 Live tone check (ask the user first)
Together with the live check at the end, ask before running three questions (about 3 chat turns, up to about 14 model calls each):
1. the uncle/land question;
2. a consumer refund question;
3. a Hinglish salary question.

Report for each:
- Does it open with a specific human line?
- Is there no legalese and no inline source names?
- Are the titles conversational?
- Are the legal points still cited?

---

## PART 4 — Cut token use without changing what the answers say

**Baseline**, measured on 2026-11-09 from 35 real turns in `model_call_events` (token counts only, no content):

| Stage | Calls | Average input | Cached | Average output |
|---|---|---|---|---|
| primary | 60 | 8,720 | 3,900 (45%) | 1,342 |
| review | 37 | 13,509 | 763 (6%) | 732 |
| web_search | 24 | 12,731 | 2,695 | 393 |
| repair | 14 | 11,106 | 1,567 | 2,257 |

**Per turn:** 3.9 calls, about 42,400 input and 4,200 output tokens on average; the largest was 197,677.

**What's not the problem:** the system prompt (about 2,500 tokens, mostly cached).

**What is:**
1. **The reviewer** gets the whole draft plus *every* evidence entry.
2. **Web search** results are large (`search_context_size` is already `"low"`).
3. **Repair** re-sends everything and rewrites the whole answer.
4. **Pre-retrieval** can put up to 16 full passages into every primary call.

**Target:** about 22,000–25,000 input tokens per turn (around −40%), with the same answers.

**Rule for every step below:** behaviour must stay the same. Each step needs a test proving the model still receives everything it needs, and an offline before/after measurement of the request size, using the `size` the provider already computes in `backend/app/agent/provider.py`, from fake-provider tests.

### 4.1 Reviewer gets only what it must check (`runner.py::_review`, about line 675)
- **Today:** `{"draft": answer.model_dump(), "pending_claim_ids": ..., "evidence": registry.payload()}`. `registry.payload()` is *all* evidence entries, full text.
- **Change it to:**
  - **`claims`:** *all* claims as compact `{claim_id, block_type, grounding, kind, text, evidence_ids}`. The reviewer still needs every claim for cross-block coherence (reviewer rule 3).
  - **`pending_claim_ids`:** unchanged.
  - **`case_patches`:** only if there are any.
  - **`evidence`:** only the entries referenced by the `evidence_ids` of **pending** claims, plus the user-message segments those claims cite. Not every passage retrieved.
  - **Dropped:** `tasks`, `central_question`, `unresolved` and other draft fields the reviewer prompt doesn't use. Check `primary-review.md` and `AgentReview` in `contracts.py` before dropping anything; keep every field they reference.
- **Tests:**
  - the review payload contains every claim's text, and the full text of every evidence entry cited by a pending claim;
  - it does **not** contain an uncited retrieved passage;
  - existing review tests still pass.
- **Expected saving:** about 8,000 input tokens per review.

### 4.2 Repair as a patch, not a rewrite (`runner.py::_repair`, about line 712)
- **Today:** it re-sends the full context, the previous answer and the full review, and the model returns a whole new `AgentAnswer` (about 2,250 output tokens).
- **Change it to:**
  - **Send:**
    - the rejected or uncertain claims with their `repair_instructions`;
    - the evidence they cite;
    - the compact list of all other claim texts (for coherence);
    - the current user message;
    - `prior_assistant_coverage`.
  - **Ask for** a new small schema `RepairPatch {replacements: [AnswerClaim], removals: [claim_id], additions: [AnswerClaim]}` (add it in `contracts.py` with the same strict-schema style).
  - **Merge** it into the existing answer by `claim_id`. Supported claims stay byte-for-byte, which the current instruction already demands.
  - **Re-review** runs as today, on the replaced and added claims only.
- **Tests:**
  - the merge keeps untouched claims identical;
  - removals are removed and additions are appended in their block order;
  - a patch that references an unknown `claim_id` is rejected and falls back to the current behaviour (the answer is kept and the claims withheld).
- **Expected saving:** about 6,000 input and 1,700 output tokens per repair.

### 4.3 Fewer, tighter web searches (`backend/app/agent/research.py`)
Search results dominate the input of the `web_search` stage, so the lever is how many searches happen.
- **Skip covered gaps:** before searching a question, run `retrieve_certified` for it. If an `official_pack` or certified passage scores above the existing floor, use it and skip the web search for that question. Record `{"tool":"web_search","status":"skipped_local_coverage"}` in `tool_records`. Part 1 adds the local law that makes this hit often.
- **One query per gap:** each `ResearchQuestion` gets one search. Keep `agent_max_queries` as the hard cap, but stop at 1 per `material_gap` unless the first search returned nothing usable.
- **Keep `search_context_size: "low"`.**
- **Tests:**
  - a gap covered by a pack passage makes no search call (fake provider call count = 0);
  - an uncovered gap still searches once.

### 4.4 Leaner pre-retrieval (`runner.py::_pre_retrieve_certified`)
- **Today:** `state["passages"]` is capped at `agent_max_passages * 2` (16 by default).
- **Change it to:**
  - cap at `agent_max_passages` (8) for the first primary call, keeping the order by relevance: certified first, then packs, then concept extras;
  - **always keep** at least one passage per matched concept, so legal aid and the like aren't crowded out (the existing per-concept design).
- **Tests:**
  - the existing `tests/test_answer_quality.py` pre-retrieval tests still pass;
  - the Bihar custody question still gets the vehicle-release, bail and legal-aid passages;
  - the new Part 1 coverage tests still pass.

### 4.5 Better prompt caching (`backend/app/agent/provider.py`)
This changes cost and latency, not token counts. Cached input tokens are billed at a discount and processed faster.
- **Cache key:** pass `prompt_cache_key` (supported by the installed SDK) in `ResponsesProvider.complete`. Use `f"nyay:{stage_family}:{conversation_id}"`, where the stage family is `primary` for primary and repair, and `review` for review, so repeated calls in a turn and later turns of the same case reuse the cached prefix. Plumb the conversation id through the existing `state`.
- **Ordering:** keep the request **prefix static and identical across calls of the same stage**: instructions, then tool definitions, then schema, then stable context (evidence sorted by `passage_id`, case memory), then the volatile parts (conversation turns, the current message, research results) last. Fix any place that builds the input with volatile data first.
- **Tests:**
  - `prompt_cache_key` is sent and stable for two calls of the same stage in one conversation;
  - the instructions and evidence block are byte-identical between round 1 and round 2 of a primary call.

### 4.6 Keep the new prompt cheap
The v2 prompt from 2.1 adds about 700 tokens. That's acceptable because it sits in the cached static prefix (4.5). Don't add examples or long lists to it later; any new rule must replace an old one.

### 4.7 Measure (offline first, live only with permission)
- **Offline:** add a measurement test or script that runs the release-gate scenarios with fake providers and prints the request size per stage before and after Part 4. Commit the numbers in the commit message.
- **Live, only after asking the user:** as part of the live checks at the end, record per-stage `input_tokens`, `cached_tokens` and `output_tokens` from `model_call_events` for the same questions. Report against the baseline table above. If any answer is worse than before Part 4 (missing cited law, lost coherence), say so and revert that step.

## Deliverables and order
1. **Commit 1 — BNSS sections** (1.1) plus the rebuilt pack, the concept mappings (1.6) and tests 1.7 #1–#3 and #6 for the BNSS part.
2. **Commit 2 — BNS** (1.2) plus tests.
3. **Commit 3 — HSA and the Bihar land Acts** (1.3, 1.4), whatever could be downloaded, plus tests #2, #4 and #5. **List anything the user must download by hand.**
4. **Commit 4 — prompt rules** (2.1) plus prompt tests.
5. **Commit 5 — completeness check** (2.3) plus tests, and the diagnosis result and fix for the cut-off (2.2).
6. **Commit 6 — block-order test** (2.4) and the release-gate scenario (2.5).
7. **Commit 7 — conversational titles** (3.2) and the reviewer sentence (3.4), plus backend tests.
8. **Commit 8 — lighter rendering** (3.3) plus frontend tests.
9. **Commit 9 — reviewer payload** (4.1) plus tests and the offline size before and after.
10. **Commit 10 — repair as patch** (4.2) plus tests.
11. **Commit 11 — local-first search and leaner pre-retrieval** (4.3, 4.4) plus tests.
12. **Commit 12 — prompt caching** (4.5) plus tests, and the measurement (4.7).

**After all commits, report to the user:**
- what was added (sources, sections and their verified headings);
- what couldn't be downloaded;
- the cut-off root cause;
- the test counts;
- whether the existing failing test still fails.

**Then ask the user** whether to run the live checks (the original question plus the 3.6 tone questions; about 3 chat turns, up to about 14 model calls each). Don't run them without a yes.
