# Nyay Saathi V2 — Legal Knowledge Corpus Coverage, Provenance & Refresh Plan

Date: 20 November 2026  
Corpus version: `2026-11-20.v1`  
Owner: Antigravity (Legal database and retrieval workstream)

## 1. Supported Coverage Declaration

### Supported Scenarios (Prototype Bounded Scope)
1. **Consumer refunds, defective products, and service complaints**:
   - Statutory definitions (`Section 2(7)` consumer & commercial-purpose explanation, `Section 2(10)` defect, `Section 2(11)` deficiency, `Section 2(47)` unfair trade practice), District Commission jurisdiction & complaint filing (`Sections 34, 35`), reliefs (`Section 39`), 2-year limitation & condonation (`Section 69`), product liability & exceptions (`Sections 84, 87`), and repeal/savings of CPA 1986 (`Section 107`).
   - Commencement notifications (`S.O. 2351(E)` dated `2020-07-20` and `S.O. 2421(E)` dated `2020-07-24`), Consumer Protection (E-Commerce) Rules, 2020 (`Rules 3, 4, 5, 6(3), 7`) + 2021 Nodal Officer Amendment (`G.S.R. 328(E)`), Jurisdiction Rules, 2021 (`G.S.R. 912(E)`), CDRC Rules 2020 (pre-2023-08-17 fees) vs 2023 Amendment (`G.S.R. 606(E)` nil fee up to Rs. 5 lakh), Mediation Rule 4 exclusions, National Consumer Helpline (`1915`), DoCA `e-Jagriti`, and *Experion Developers v. Sushma Ashok Shiroor* (SC 2022, distinguished for homebuyer/RERA vs retail goods).
   - Pending amendment preserved but excluded from approved answers: Consumer Protection (E-Commerce) (Amendment) Rules, 2026 (`reviewState: 'pending'`, commencement unverified).
2. **Financial fraud (substantive & FIR procedure, including historical transition)**:
   - Post-1 July 2024: Bharatiya Nyaya Sanhita, 2023 (`Sections 316, 318, 319, 358`), Bharatiya Nagarik Suraksha Sanhita, 2023 (`Sections 173 Zero FIR / e-FIR, 175(3), 531`), and MHA Gazette Commencement Notifications (`S.O. 850(E)`, `S.O. 848(E)`, published `2024-02-23`, effective `2024-07-01`).
   - Pre-1 July 2024 historical regime: Indian Penal Code, 1860 (`Section 420` saved under BNS `s.358`) and Code of Criminal Procedure, 1973 (`Section 154` saved under BNSS `s.531`).
3. **Banking and payment grievances**:
   - RBI Circular `DBR.No.Leg.BC.78/09.07.005/2017-18` (6 July 2017): immediate reporting, 3-working-day zero liability, customer-negligence exception (shared OTP/PIN/password before reporting vs post-reporting bank liability), 10-working-day shadow reversal, 90-day resolution, burden of proof on bank.
   - RBI Circular `DPSS.CO.PD.No.1417/02.14.006/2018-19` (published 4 Jan 2019, effective 1 Mar 2019): non-bank PPI / digital wallet unauthorised transaction liability.
   - RBI Circular `DPSS.CO.PD No.629/02.01.014/2019-20` (published 20 Sep 2019, effective 15 Oct 2019): failed UPI/IMPS (`T+1`) and ATM/Card/POS (`T+5`) auto-reversal TAT and Rs. 100/day compensation.
   - RBI Master Direction `DoR.AUT.REC.No.27/24.01.041/2022-23` (updated 7 Mar 2024): credit/debit card unsolicited card prohibition (twice-charges penalty), 7-working-day closure, and billing disputes.
   - Reserve Bank – Integrated Ombudsman Scheme, 2021 (`RB-IOS 2021`, effective `2021-11-12`, `cms.rbi.org.in`, 30-day bank escalation prerequisite) and historical Banking Ombudsman Scheme, 2006 (`validUntil: 2021-11-12`).
4. **Legal aid cross-cutting support**:
   - Legal Services Authorities Act, 1987 (`Section 12` eligibility criteria).

### Supported Regions
- **India** (national central statutes, rules, RBI circulars, SC precedent)
- **Maharashtra** (Maharashtra State Consumer Disputes Redressal Commission grievance procedures, e-Jagriti filing adoption, and Mumbai/Thane/Raigad District Commission directory from `grahak.maharashtra.gov.in`)
- **Bihar** (Bihar Prohibition and Excise Act, 2016 regional statute retained as regional/cross-state boundary reference)

Queries specifying any other state (e.g., Karnataka, Uttar Pradesh, Delhi) retrieve applicable national India-wide law and emit an explicit missing-state-coverage limitation.

## 2. Embedding & Retrieval Configuration

- **Embedding Model**: `text-embedding-3-small`, 384 dimensions
- **Embedding Configuration Version**: `openai:text-embedding-3-small:dimensions=384:v1`; corpus and query vectors must use this exact configuration.
- **Vector Dimensions**: `384` (`cosine` similarity over L2-normalized vectors)
- **Retrieval Architecture**:
  - Independent **semantic cosine search** (no keyword-match prerequisite) + independent **BM25 / PostgreSQL `tsvector` lexical search** + exact statutory section/circular matching + Hindi/Hinglish cross-language query normalization (preserving names, dates, amounts, negation, and uncertainty; never altering stored originals).
  - Fused via **Reciprocal Rank Fusion (RRF)** (`1 / (60 + rank)`), filtered by region, temporal validity (`incidentDate` or `asOfDate`), and `reviewState === 'approved'`, with **transitive companion-passage closure** (`relatedPassageIds`) enforced within `request.limit`.

## 3. Source Provenance Summary

All 29 official sources are preserved as raw original PDF/HTML files under `data/sources/originals/` (gitignored) with full SHA-256 hashes recorded in `data/legal_corpus/v1/sources.json` and `data/legal_corpus/v1/documents.json`:
- `consumeraffairs.gov.in`: CPA 2019, S.O. 2351(E), S.O. 2421(E), E-Commerce Rules 2020, 2021 Amendment, 2026 Pending Amendment, Jurisdiction Rules 2021, CDRC Rules 2020 & 2023 Amendment, Mediation Rules 2020, Consumer Protection Unit / e-Jagriti.
- `consumerhelpline.gov.in`: NCH 1915 About & Contact.
- `indiacode.gov.in`: CPA 1986 (`A1986-68.pdf`, scanned PDF preserved; saving clause extracted from CPA 2019 s.107).
- `api.sci.gov.in`: *Experion Developers v. Sushma Ashok Shiroor* (2022).
- `ncrb.mha.gov.in`: BNS 2023 (`BNS2023.pdf`), BNSS 2023 (`BNSS2023.pdf`), MHA Gazette Commencement Notification (`S.O. 850(E)` / `S.O. 848(E)`).
- `rbi.org.in`: Circulars `DBR.No.Leg.BC.78/09.07.005/2017-18`, `DPSS.CO.PD.No.1417/02.14.006/2018-19`, `DPSS.CO.PD No.629/02.01.014/2019-20`, Master Direction `DoR.AUT.REC.No.27/24.01.041/2022-23`, and Press Release `2021-2022/1184` (RB-IOS 2021).
- `grahak.maharashtra.gov.in`: Maharashtra SCDRC grievance guide & District Commission directory.
- `cdnbbsr.s3waas.gov.in` / `betastate.bihar.gov.in`: NALSA Legal Services Authorities Act, 1987 & Bihar Prohibition and Excise Act, 2016.

## 4. Continuous Update & Editorial Review Responsibilities

Implemented in `legal_knowledge/updater.py` and `supabase/migrations/20261120050000_legal_corpus_vector_and_updates.sql`:
1. **Scheduled & Discovered Inputs**: Cron checks `nyay_legal_sources` (trusted official URLs). Agent-discovered URLs are staged as `agent_discovered_candidate` (`reviewState = 'pending'`) and NEVER granted direct corpus publication rights.
2. **Private Data Isolation**: Private case documents, Gmail threads, Drive files, and model-generated answers are explicitly blocked (`PrivateDataIsolationError`) and never indexed into `nyay_legal_passages`.
3. **Materiality & Editorial Gate**: Any change to text/locators, unverified `effective_from`, or discovered candidate is classified `material_change = true` and requires an identified human editorial reviewer (`advocate.*`, bar-enrolled reviewer) before embedding/activation. Model IDs (`model:*`, `llm:*`, `agent:*`) are rejected at both Python and PostgreSQL RPC layers.
4. **Narrow Auto-Promotion Policy**: Permitted ONLY when `trust_tier = 'trusted_registry'`, `effective_from` is already verified, and normalized passage text and locators are 100% identical (whitespace/serialization-only refresh).
5. **Freshness Warnings, Cache Invalidation & Rollback**: Pending material changes attach a freshness warning to currently active passages; activation increments `cache_epoch`, clears stale `nyay_legal_retrieval_cache` entries, preserves older versions with `effective_until` for historical queries, and supports atomic `rollback_version` recovery.

## 5. Unresolved Legal & Integration Limitations

1. **Pending Qualified Indian Lawyer Audit**: Texts are verbatim official extractions, not yet signed off by a qualified Indian advocate (the `cpa-ecommerce-amendment-2026` PDF also has incomplete commencement extraction and remains `reviewState: 'pending'`).
2. **`retrieval-port.ts` `incidentDate === null` Filter**: In the backend-owned `applicablePassages()` (`supabase/functions/nyay-api/retrieval-port.ts:46`), time-bound passages are rejected when `request.incidentDate === null` (it does not fall back to `request.asOfDate`). Our `RetrieveEvidence` implementation evaluates `asOfDate` and emits an explicit limitation for general current-law questions, and flags this for coordinated adjustment with the Backend & Agent Integration owner without modifying `retrieval-port.ts` unilaterally.
3. **Edge Runtime Query Embedding**: Supabase calls OpenAI's embeddings endpoint with the exact model and 384 dimensions. Missing, malformed, or unavailable embeddings disable admission or retry the persisted step; the reviewed legal-answer path does not silently fall back to keyword-only retrieval.
4. **Scanned/Portal-Blocked Sources**: `cpa-1986-indiacode.pdf` (1986 scanned PDF without text layer), `indiacode.gov.in` historical IPC 1860 / CrPC 1973 full PDFs, and `rbidocs.rbi.org.in` Akamai-gated PDFs (`RBIOS2021_121121_A.pdf`) could not be text-extracted directly; historical saving text and RB-IOS 2021 salient features were extracted from official BNS s.358, BNSS s.531, CPA 2019 s.107, and RBI Press Release `prid=52549`.
5. **Hosted Verification Pending**: Local PGlite + ONNX evaluations pass, but hosted Supabase migration (`20261120050000_legal_corpus_vector_and_updates.sql` with `pgvector` HNSW), `pg_cron` refresh scheduling, and live Edge runtime measurements have not been deployed or run (per task boundary).
