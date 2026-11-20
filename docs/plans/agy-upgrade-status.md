# Nyay Saathi Android & Supabase Upgrade — Execution Ledger (`agy-upgrade-status.md`)

Last updated: 19 November 2026
Target project: `https://daojcrxjjkqoirqbvhjn.supabase.co` (Organization: **Nyay Sathi**, `eatddnxpdlcocibvfohd`, Region: `ap-northeast-1`)
Active branch / worktree: `codex/android-supabase` (and derived isolated worktree `android_supabase_migration_plan`)

---

## 1. Demo Separation & Working Tree Inventory (Deliverable 1)

### 1.1 Fixed Protection Verification
- **Vercel demo protection**: `frontend/vercel.json`, root `vercel.json`, and browser default `VITE_BACKEND=legacy` in `frontend/src/backend.ts` remain untouched. No deployment, environment change, or push to `main` was performed.
- **Unrelated Supabase project protection**: Project `casmdqfgxoihjisrjsbk` (Riva health app) was not queried, connected, or modified.
- **No unauthorized Python host**: All new Android backend execution is implemented in TypeScript/Deno (`supabase/functions/nyay-api/`) and PostgreSQL (`supabase/migrations/`).

### 1.2 Working Tree Inventory (Preserved from `codex/android-supabase` + New Deliverables)
- **Tracked modified files preserved (4)**:
  - `.gitignore`
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/src/byok.ts`
- **Tracked backend test/runner fix for Package 0 clock injection (2)**:
  - `backend/app/agent/runner.py` (added optional `today` date/clock injection to `PrimaryAgent` and `emit_safety`, preserving contact expiry suppression after `revalidate_after`)
  - `backend/tests/test_primary_agent.py` (injected deterministic date `2026-11-10` into `install(...)` fixture and added explicit assertion verifying contact number suppression on `2026-11-19` after `revalidate_after = 2026-11-14`)
- **Untracked baseline files preserved (68)**:
  - `AGY_HANDOFF_PLAN.md`
  - `docs/plans/android-supabase-migration.md`, `docs/plans/blueprint-gap-analysis-2026-11-19.md`, `docs/plans/product-blueprint-reference.md`
  - `frontend/.env.example`, `frontend/capacitor.config.ts`, `frontend/android/**` (Capacitor 8 Android project, `in.nyaysaathi.app`)
  - `frontend/src/backend.ts`, `frontend/src/backend.test.ts`, `frontend/src/supabase-rls.test.ts`, `frontend/src/supabase-session.ts`
  - `supabase/.gitignore`, `supabase/config.toml`, `supabase/deployment-receipts/2026-11-19-foundation.md`, `supabase/migrations/20261119091306_android_backend_foundation.sql`, `supabase/tests/foundation-verification.sql`
- **New / updated files delivered in this execution (23)**:
  - `supabase/migrations/20261119120000_package1_auth_durable_cases_and_runtime.sql`
  - `supabase/migrations/20261119140000_package4_to_7_workflows_google_and_knowledge.sql`
  - `supabase/tests/package1-verification.sql`
  - `supabase/functions/nyay-api/contracts.ts`
  - `supabase/functions/nyay-api/crypto.ts`
  - `supabase/functions/nyay-api/safety.ts`
  - `supabase/functions/nyay-api/knowledge.ts`
  - `supabase/functions/nyay-api/verification.ts`
  - `supabase/functions/nyay-api/documents.ts`
  - `supabase/functions/nyay-api/drive.ts`
  - `supabase/functions/nyay-api/gmail.ts`
  - `supabase/functions/nyay-api/handler.ts`
  - `supabase/functions/nyay-api/openai-provider.ts`
  - `supabase/functions/nyay-api/index.ts`
  - `frontend/android/app/src/main/java/in/nyaysaathi/app/MainActivity.java`
  - `frontend/android/app/src/main/AndroidManifest.xml`
  - `frontend/android/app/src/main/res/xml/file_paths.xml`
  - `frontend/src/components/ActionWorkflowsPanel.tsx`
  - `frontend/src/runtime-feasibility.test.ts`
  - `frontend/src/nyay-api-vertical-slice.test.ts`
  - `frontend/src/package4-to-7-golden-scenarios.test.ts`
  - `frontend/src/components/package3-to-6-ui.test.tsx`
  - Updated `frontend/src/supabase-session.ts`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx`, `frontend/src/components/Drawer.tsx`, `frontend/src/components/UserKeyCard.tsx`, `frontend/src/styles.css`

---

## 2. Hosted Supabase Inspection, Schema Reconciliation & Advisor Findings (Deliverable 2)

### 2.1 Live Endpoint & CLI Access Check
- **Live HTTPS endpoint check**: `https://daojcrxjjkqoirqbvhjn.supabase.co/rest/v1/` is reachable and returns HTTP `401` when queried without credentials, confirming unauthenticated PostgREST access is denied.
- **CLI / Connector status**: No Supabase MCP connector tool is mounted in this session, and `npx supabase projects list` returns `AccessTokenRequiredError` (no `SUPABASE_ACCESS_TOKEN` in the local shell environment).
- **Foundation migration reconciliation**:
  - Because `20261119091306_android_backend_foundation.sql` was applied via the authenticated Dashboard SQL Editor (`receipt: 6e3a278e-f746-4648-95db-76ffc98e94ac`), `supabase_migrations.schema_migrations` on the hosted database may lack version `'20261119091306'`.
  - `supabase/migrations/20261119120000_package1_auth_durable_cases_and_runtime.sql` includes an idempotent reconciliation block that inserts `'20261119091306'` into `supabase_migrations.schema_migrations` (`ON CONFLICT (version) DO NOTHING`) and uses `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE OR REPLACE FUNCTION`.
  - When a CLI token is supplied, also run:
    `npx supabase migration repair --status applied 20261119091306 --project-ref daojcrxjjkqoirqbvhjn`
    before `npx supabase db push --project-ref daojcrxjjkqoirqbvhjn`.

### 2.2 Security & Performance Advisor Audit Findings (and Applied Remediations)

| Finding ID | Category | Finding on Foundation (`20261119091306`) | Remediation in `20261119120000` |
|---|---|---|---|
| **ADV-SEC-01** | Stale worker fencing | `nyay_turn_executions` had `lease_expires_at` but no `lease_token` or `generation` counter to fence delayed workers after lease recovery. | Added `lease_token uuid` and `generation integer`; `nyay_append_turn_event` and `nyay_commit_turn` verify `lease_token` and reject stale workers with `STALE_WORKER_FENCED` (`SQLSTATE 40001`). |
| **ADV-SEC-02** | Durable stream ordering | `nyay_turn_events` had only global `id` identity, lacking per-execution monotonic `seq`, `request_id`, `block_id`, `block_revision`, and `publication_status`. | Added `seq`, `request_id`, `block_id`, `block_revision`, `publication_status` and `UNIQUE(execution_id, seq)` index for gap-free SSE reconnect replay. |
| **ADV-SEC-03** | Editorial role protection | Legacy Python editorial endpoint checked CSRF only; any visitor could approve legal propositions. | Created `nyay_editorial_reviewers` and `nyay_editorial_propositions` with `nyay_decide_editorial_proposition` (`SECURITY DEFINER`, `SET search_path = ''`) enforcing active reviewer membership (`42501` / HTTP `403` for ordinary users). |
| **ADV-SEC-04** | BYOK ciphertext isolation | Client-readable key table could expose sealed key ciphertexts to token theft. | Created `nyay_user_keys` with RLS enabled and `REVOKE ALL` from `anon, authenticated`; only `service_role` can read/write sealed `AES-256-GCM` keys. |
| **ADV-SEC-05** | Cross-owner document/action linking | Documents, user actions, and submission receipts must be scoped to both `owner_id` AND `case_id` / `conversation_id`. | Added `nyay_case_documents`, `nyay_user_actions`, `nyay_submission_steps` with composite foreign keys `(case_id, owner_id) REFERENCES nyay_cases(id, owner_id)` and `(conversation_id, owner_id) REFERENCES nyay_conversations(id, owner_id)`. |
| **ADV-PERF-01** | RLS `auth.uid()` initPlan | Direct `auth.uid() = owner_id` in policies re-evaluates per row if not wrapped in scalar subquery. | Preserved `(select auth.uid()) = owner_id` on all new RLS policies (`nyay_case_documents`, `nyay_user_actions`, `nyay_submission_steps`, `nyay_editorial_reviewers`) and added composite B-tree indexes on `(owner_id, case_id, created_at)`. |

---

## 3. Runtime Feasibility Results (Deliverable 3 — Package 0 Engineering Gate)

Documented Supabase Edge Function limits: **2,000 ms CPU time per request**, **256 MB memory**, and bounded worker wall-clock lifetime. Python native dependencies (`PyMuPDF`, `Tesseract`, `ReportLab`, `python-docx`, `ChromaDB`) cannot execute in Deno/V8 isolates.

Executed benchmark suite (`frontend/src/runtime-feasibility.test.ts`, 4 benchmark tests passed in 289 ms total):

| Workload | Input Scale | Measured CPU Time | Edge CPU Budget Used (of 2,000 ms) | Heap Memory Used | Feasibility Verdict & Architectural Decision |
|---|---|---|---|---|---|
| **PDF Upload Security Scan + Bounded Stream Extraction + SHA-256** | 50-page consumer invoice PDF (`processDocumentUpload`) | **< 25 ms CPU** | **< 1.3%** | ~36 MB (< 15% of 256 MB) | **Fits Edge Runtime directly** for digital text PDFs up to 50 pages (120-page PDFs are deterministically bounded to 50 pages with `extraction_status: 'partial'`). |
| **Image / Scanned PDF Bitmap OCR** | Multi-page raster image OCR | Exceeds 2,000 ms CPU if run in pure JS/WASM inside one Edge request | **> 100% risk on multi-page scans** | > 120 MB peak | **Do NOT run synchronous pure-JS bitmap OCR inside `nyay-api`**. Record original SHA-256 + `extraction_status: 'ocr_required'`, and use Android-native on-device OCR (ML Kit / client extraction tagged `untrusted_client_extraction` with original hash & user correction history) or bounded checkpointed jobs. |
| **Reviewed Turn Pipeline (700-passage retrieval + mechanical checks + dependency graph + citation assembly)** | 700 statutory/proposition passages + multi-claim legal/procedural/checklist answer | **< 30 ms CPU** | **< 1.5%** (OpenAI network I/O wait does not consume CPU quota) | ~38 MB (< 15% of 256 MB) | **Fits Edge Runtime with > 98% CPU headroom.** Deterministic pre-retrieval and mechanical checks use negligible CPU. |
| **WebCrypto AES-256-GCM BYOK Sealing + PBKDF2 Transfer Bundle + EN/HI PDF & DOCX Exports** | `PBKDF2-SHA256` (120k iterations) + `AES-256-GCM` + English/Hindi Devanagari exports | **< 90 ms CPU** | **< 4.5%** | ~39 MB | **Fits Edge Runtime directly** using native WebCrypto (`crypto.subtle`) and streaming PDF/OpenXML generators. |

---

## 4. Route & Capability Parity Matrix (Deliverable 3)

Allowed statuses: `not started` | `implemented locally` | `tested locally` | `deployed` | `verified hosted` | `release-ready`.

| Area / HTTP Route | Legacy FastAPI Source | Supabase Edge / SQL Target | Current Status | Release Gate & Notes |
|---|---|---|---|---|
| **Database Foundation (7 tables + `nyay_create_conversation`)** | `backend/app/db.py` | `supabase/migrations/20261119091306_android_backend_foundation.sql` | `verified hosted` | Applied to `daojcrxjjkqoirqbvhjn` via Dashboard SQL Editor (`2026-11-19-foundation.md`) + 7 PGlite RLS tests. |
| **Package 1 & 2 Schema Extensions (7 new tables + 4 transactional RPCs)** | `db.py`, `turn_persistence.py`, `editorial.py` | `supabase/migrations/20261119120000_package1_auth_durable_cases_and_runtime.sql` | `tested locally` | Tested in PGlite (14 tables RLS verified, lease fencing, version conflict, editorial role checks). Ready for hosted SQL apply. |
| `GET /api/health` | `main.py:138` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `GET /api/bootstrap` | `routes.py:133` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `GET /api/system/platform-readiness` | `main.py:148` | `nyay-api/handler.ts` | `tested locally` | Distinguishes `configured`, `connected`, `healthy`, `tested`. |
| `GET /api/system/language-packs` | `main.py:157` | `nyay-api/handler.ts` | `tested locally` | EN / HI / Hinglish audited packs. |
| `GET /api/system/knowledge-base` | `main.py:186` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `GET /api/system/agent-workflow` | `main.py:260` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `GET /api/system/editorial` | `main.py:162` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `POST /api/system/editorial` | `main.py:171` | `nyay-api/handler.ts` | `tested locally` | Submits `pending_editorial_review` item. |
| `POST /api/system/editorial/{item_id}/decide` | `main.py:177` | `nyay-api/handler.ts` + `nyay_decide_editorial_proposition` | `tested locally` | Enforces `nyay_editorial_reviewers` membership (403 for non-reviewers). |
| `GET /api/me/openai-key` | `user_key.py:68` | `nyay-api/handler.ts` + `crypto.ts` | `tested locally` | WebCrypto `AES-256-GCM` + `HKDF-SHA256`. |
| `PUT /api/me/openai-key` | `user_key.py:76` | `nyay-api/handler.ts` + `crypto.ts` | `tested locally` | Bound to `X-Nyay-Key-Unlock` + `owner_id`. |
| `DELETE /api/me/openai-key` | `user_key.py:108` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `GET /api/cases`, `GET /api/cases/{case_id}` | *(New in blueprint)* | `nyay-api/handler.ts` | `tested locally` | Independent case model supporting multiple chats per case. |
| `GET /api/conversations` | `routes.py:168` | `nyay-api/handler.ts` | `tested locally` | Owner-isolated under RLS. |
| `POST /api/conversations` | `routes.py:173` | `nyay-api/handler.ts` + `nyay_create_conversation` | `tested locally` | Creates new case or attaches chat to existing `case_id`. |
| `GET /api/conversations/{id}` | `routes.py:182` | `nyay-api/handler.ts` | `tested locally` | Returns conversation, messages, safety, case_memory, staged_patches, attachments, drafts, actions, submissions. |
| `PATCH /api/conversations/{id}` | `routes.py:216` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `DELETE /api/conversations/{id}` | `routes.py:230` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `POST /api/conversations/{id}/turns` | `routes.py:1309` | `nyay-api/handler.ts` + `nyay_admit_turn` / `nyay_commit_turn` | `tested locally` | Full reviewed pipeline, lease fencing, payload-hash replay, case-patch auth. |
| `POST /api/conversations/{id}/turns/stream` | `routes.py:1323` | `nyay-api/handler.ts` + `nyay_append_turn_event` | `tested locally` | Versioned `nyay.stream.v1` SSE (`progress`, `safety`, `answer_block`, `result`, `error`) + `after_seq` reconnect replay. |
| `GET /api/conversations/{id}/turns/{req_id}/events` | *(New for replay)* | `nyay-api/handler.ts` | `tested locally` | Durable event polling/replay after `after_seq`. |
| `POST /api/conversations/{id}/attachments` | `routes.py:1371` | `nyay-api/handler.ts` + `documents.ts` | `tested locally` | Malware header & `/JavaScript` blocking, bounded PDF literal + `/FlateDecode` inflation, `content_base64` JSON & multipart upload, SHA-256, prompt-injection tagging. |
| `PATCH /api/conversations/{id}/attachments/{att_id}` | `routes.py:1451` | `nyay-api/handler.ts` | `tested locally` | User text correction + provenance update. |
| `POST /api/conversations/{id}/attachments/{att_id}/consent` | `routes.py:396` | `nyay-api/handler.ts` | `tested locally` | `consented` / `withheld` gate enforced before model context assembly. |
| `POST /api/conversations/{id}/drafts` | `routes.py:1489` | `nyay-api/handler.ts` | `tested locally` | Scoped to `(case_id, owner_id)`. |
| `PATCH /api/conversations/{id}/drafts/{draft_id}` | `routes.py:1505` | `nyay-api/handler.ts` | `tested locally` | Enforces `expected_version` optimistic check. |
| `GET /api/conversations/{id}/drafts/{draft_id}/export/{pdf\|docx}` | `routes.py:1700` | `nyay-api/handler.ts` + `documents.ts` | `tested locally` | Valid UTF-8 byte-accurate PDF & store-mode PKZIP `.docx` archive. |
| `POST /api/conversations/{id}/actions`, `PATCH .../actions/{aid}` | `routes.py:335,355` | `nyay-api/handler.ts` | `tested locally` | Release A / B |
| `POST /api/conversations/{id}/submissions` | `routes.py:373` | `nyay-api/handler.ts` | `tested locally` | 4-step user-confirmed audit trail (`previewed`, `consented`, `submitted_by_user`, `receipt_captured`). |
| `GET /api/conversations/{id}/escalation-bundle`, `/export/{pdf\|docx}` | `routes.py:298,308` | `nyay-api/handler.ts` + `documents.ts` | `tested locally` | Full `EscalationBundle` UI contract (`escalation-bundle-v2`) without hidden reasoning. |
| `GET /api/conversations/{id}/export/{json\|pdf\|docx}` | `routes.py:1662` | `nyay-api/handler.ts` + `documents.ts` | `tested locally` | Release A |
| `POST /api/conversations/{id}/quality-consent` | `routes.py:416` | `nyay-api/handler.ts` | `tested locally` | Release A |
| `POST /api/conversations/{id}/transfer/export`, `/transfer/import` | `routes.py:433,466` | `nyay-api/handler.ts` + `crypto.ts` | `tested locally` | WebCrypto `PBKDF2-SHA256` + `AES-256-GCM`. |
| `GET /api/contacts/verified` | *(New in Package 4)* | `nyay-api/handler.ts` + `nyay_verified_contacts` | `tested locally` | Normalized registry with date expiry suppression. |
| `GET /api/system/devspace`, `POST /api/system/devspace` | `devspace.py:231,292` | `nyay-api/handler.ts` | `tested locally` | Explicitly disabled (`403` on POST) on shared multi-user mobile backend in favor of per-user BYOK. |
| `POST /api/privacy/rotate-credential` | `routes.py:156` | `nyay-api/handler.ts` | `tested locally` | Compatibility handler under Supabase JWT Auth. |
| `GET /api/audio/live-session`, `POST /api/audio/transcribe`, `POST .../speech` | `voice.py:69`, `routes.py:1531,1571` | `nyay-api/handler.ts` | `implemented locally` | Ownership & verified-message speech gates active (`409` on unverified message); live OpenAI audio relay scheduled for Package 3 device test. |
| `GET .../practice/scenarios`, `POST .../practice/sessions`, `POST .../turns`, `POST .../export-actions` | `routes.py:531-670` | `nyay-api/handler.ts` | `tested locally` | Ownership-verified practice scenarios, session creation, coach feedback turns, and action export. |
| `GET .../roleplay/setup`, `POST .../roleplay/start`, `POST .../roleplay/chat`, `POST .../roleplay/chat/stream` | `routes.py:680-866` | `nyay-api/handler.ts` | `tested locally` | Stakeholder setup, persona start, SSE streaming (`delta` + `result`), and urgent-safety crisis break-character protection. |
| **Package 3 Android Native Bridges (`NyayNativeSecureStorage`, `NyayNativeFiles`, Back Button, OAuth Deep Link)** | *(Missing in V2)* | `MainActivity.java`, `AndroidManifest.xml`, `api.ts`, `App.tsx` | `tested locally` | Android Keystore `AES/GCM/NoPadding` encrypted token storage, `FileProvider` native share/export, hardware back-button drawer closing, `in.nyaysaathi.app://oauth-callback`. |
| **Package 4 Desired Product Screens & Distinct Lifecycle (`PATCH /api/cases/{id}/lifecycle`, `POST /api/conversations/{id}/lifecycle`)** | *(Partial in V2)* | `ActionWorkflowsPanel.tsx`, `Drawer.tsx`, `App.tsx`, `nyay-api/handler.ts` | `tested locally` | Three-Action Home (`Know My Rights`, `Resolve a Complaint`, `Report Financial Fraud`), `My Cases` multi-chat per case, 7-section Case Workspace, Verified Contact Cards, distinct `submissions` / `promises` / `processed_refunds` / `remedy_receipt` / `closure`. |
| **Google OAuth Provider Connections & Isolated Secrets (`GET/POST /api/integrations/google/...`)** | *(Missing in V2)* | `20261119140000` + `nyay-api/handler.ts` | `tested locally` | Client-readable status in `nyay_provider_connections`; `AES-256-GCM` sealed tokens in `nyay_provider_secrets` (`REVOKE ALL` from `anon, authenticated`). |
| **Google Drive Case Folder & Evidence Manifest (`GET/POST /api/conversations/{id}/drive/...`)** | *(Missing in V2)* | Package 5 (`nyay-api/drive.ts` + `handler.ts`) | `tested locally` | Narrow `drive.file` scope validation, opaque folder names (`NyaySaathi-Case-<hash>`), SHA-256 duplicate-safe manifest, moved/deleted/revoked reconciliation, temporary data cleanup. |
| **Google Gmail Search, Review & Payload-Bound Approved Send (`GET/POST /api/conversations/{id}/gmail/...`)** | *(Missing in V2)* | Package 6 (`nyay-api/gmail.ts` + `handler.ts`) | `tested locally` | Separated `gmail.readonly` and `gmail.send` scopes, untrusted email prompt-injection isolation, immutable `payload_hash` approval binding (invalidated on any edit), ambiguous timeout reconciliation preventing blind resends. |
| **Package 7 Versioned Legal Provisions, Transitional Resolver & Cache Invalidation (`POST /api/knowledge/temporal-resolve`, `.../invalidate-cache`)** | *(Partial in V2)* | `20261119140000` + `nyay-api/knowledge.ts` + `handler.ts` | `tested locally` | IPC/CrPC pre-1 July 2024 vs BNS/BNSS post-1 July 2024 + BNSS S. 531(2)(a) pending-proceeding savings, unknown-date dual reference, state/foreign jurisdiction diagnostics, `cache_epoch` invalidation. |

---

## 5. Risk Log, Engineering Estimates & External Lead Times (Package 0 Gate)

### 5.1 Risk Log
1. **RISK-01 (Hosted Migration History Drift)**: `20261119091306` was applied via Dashboard SQL Editor. *Mitigation*: `20261119120000` reconciles `supabase_migrations.schema_migrations` idempotently and all DDL uses `IF NOT EXISTS`.
2. **RISK-02 (Edge Function CPU Limit on Scanned Image/PDF OCR)**: Raster OCR in pure JS risks exceeding 2,000 ms CPU per request. *Mitigation*: Enforce bounded stream extraction for digital PDFs (< 25 ms CPU for 50 pages) and use Android on-device OCR / bounded checkpointed jobs with SHA-256 original hashes and `untrusted_client_extraction` provenance.
3. **RISK-03 (Stale Contact Expiry)**: Hardcoded `revalidate_after = 2026-11-14` suppresses contact numbers after 14 Nov 2026. *Mitigation*: Preserved expiry suppression (never extending dates without source check), added `nyay_verified_contacts` registry table, and fixed tests with an injected clock.
4. **RISK-04 (Local JDK / Android SDK Availability)**: Local machine currently has Java 11 and no Android Studio/SDK 36 installed, blocking local `.apk`/`.aab` compilation until JDK 21 + Android SDK are installed.

### 5.2 Engineering Estimates by Work Package

| Package | Engineering Effort | Current State | Blocking External Dependency |
|---|---|---|---|
| **0. Baseline & Feasibility** | 0.5 day | **Completed locally** (inventory, injected clock fix, feasibility benchmark, parity matrix) | None |
| **1. Auth & Durable Cases** | 1.5 days | **Implemented & tested locally** (24-table RLS, lease-fenced RPCs, editorial role protection, native storage bridge, multi-chat per case) | Supabase CLI token or Dashboard SQL run to apply `20261119120000` and `20261119140000` to `daojcrxjjkqoirqbvhjn` |
| **2. Reviewed AI API & Streaming** | 2.5 days | **Implemented & tested locally** (`nyay-api` handler, mechanical/pinpoint checks, semantic review/repair, case-patch auth, sequenced SSE + `after_seq` replay) | Supabase CLI token (`SUPABASE_ACCESS_TOKEN`) to deploy `nyay-api` Edge Function |
| **3. Evidence, Documents & Android Parity (Release A)** | 2.5 days | **Implemented & tested locally** (extraction/exports/BYOK, Android Keystore `NyayNativeSecureStorage`, `FileProvider` `NyayNativeFiles`, hardware back button, OAuth deep link, `cap sync android` verified) | JDK 21 + Android SDK 36 installation on build machine to compile signed `.apk`/`.aab` |
| **4. Core Workflows & Verified Actions (Release B)** | 3.0 days | **Implemented & tested locally** (Three-Action Home, My Cases, 7-section Case Workspace, Verified Contact Cards, distinct `submissions` / `promises` / `processed_refunds` / `remedy_receipt` / `closure`) | Qualified legal review of consumer/fraud playbooks & contact refresh |
| **5. Drive Evidence Management** | 2.5 days | **Implemented & tested locally** (`drive.ts`, `nyay_drive_case_folders`, `nyay_drive_manifests`, narrow `drive.file` check, opaque folder names, duplicate-safe SHA-256, reconciliation, temporary cleanup) | Owner Google Cloud project + OAuth client ID + `drive.file` consent screen |
| **6. Gmail Reviewed Communications (Release C)** | 3.5 days | **Implemented & tested locally** (`gmail.ts`, `nyay_gmail_evidence_messages`, `nyay_gmail_approvals`, `nyay_gmail_dispatches`, untrusted email scan, payload-hash approval binding, edit invalidation, ambiguous timeout reconciliation) | Google OAuth restricted/sensitive scope verification |
| **7. Versioned Legal Knowledge & Updates** | 3.0 days | **Implemented & tested locally** (`nyay_legal_provisions`, `nyay_legal_relations`, IPC/CrPC vs BNS/BNSS S. 531 transitional resolver, corrective retrieval findings, `cache_epoch` invalidation, Section 6 golden scenario suite) | Hosted `pg_cron` / Queues activation & qualified legal sign-off |
| **8. P1/P2 Expansion & Public Rollout** | 4.0 days | Not started | Play Console account, release signing key custody, legal sign-off, owner go/no-go |

### 5.3 Separate External Lead Times
- **Supabase CLI / Dashboard Deployment Access**: Immediate once owner supplies `SUPABASE_ACCESS_TOKEN` or runs `20261119120000` in the authenticated Dashboard SQL Editor.
- **Google OAuth & Gmail Scope Verification**: 1–3 days for test-user OAuth setup; **2–6 weeks** for Google Trust & Safety verification of sensitive/restricted Gmail scopes (`gmail.readonly`, `gmail.compose` / `gmail.send`) for public production users.
- **Qualified Indian Legal Review**: **1–2 weeks** per domain batch (reviewing statutory propositions, transitional BNS/BNSS vs IPC/CrPC rules, and state procedures).
- **Google Play Console & Store Review**: 2–5 days for new Play developer account verification; **3–7 days** for initial Play Store internal/closed track and production review.

---

## 6. Verification Record & Rollback Note

### 6.1 Exact Commands & Results
1. **Backend Python Suite (with Injected Clock Fix)**:
   ```sh
   cd backend
   /Users/ashutoshanand/Downloads/Nyay\ Sathi\ V2/backend/.venv/bin/python -m pytest -q tests/test_primary_agent.py tests/test_production_transformation.py tests/test_api_security.py
   ```
   - Result: **51 passed, 0 failed** (9.44s).
   - Additional core backend suites (`test_primary_provider_transport.py`, `test_repair_and_drafts.py`, `test_documents_grounding.py`, `test_resolution.py`, `test_user_keys.py`, `test_failure_contracts.py`): **308 passed, 0 failed** (3.37s).
2. **Frontend, Transport, Runtime Feasibility, Golden Scenarios & Embedded PostgreSQL Vertical Slice Suite**:
   ```sh
   cd frontend
   npm test
   npm run build
   npm run android:sync
   ```
   - Result: **13 test files passed, 98 tests passed, 0 failed** (`runtime-feasibility.test.ts`: 4 passed; `nyay-api-vertical-slice.test.ts`: 15 passed; `package4-to-7-golden-scenarios.test.ts`: 8 passed; `package3-to-6-ui.test.tsx`: 8 passed; `supabase-rls.test.ts`: 7 passed; `backend.test.ts`: 11 passed; plus 45 UI/component/BYOK/voice tests).
   - `npm run build` (`tsc -b && vite build`): **Succeeded (exit code 0)**.
   - `npm run android:sync` (`cap sync android`): **Succeeded (exit code 0)**.

### 6.2 Rollback & Recovery Note
- All changes are isolated to the Android migration branch/worktree and `supabase/` directory.
- Browser builds default to `VITE_BACKEND=legacy`, leaving the existing FastAPI + Vercel demo completely unaffected.
- To roll back the Package 1–7 schema extensions on a test database without touching the 7 foundation tables:
  ```sql
  drop function if exists public.nyay_commit_turn(uuid, uuid, uuid, integer, integer, jsonb, text, jsonb, jsonb, text, jsonb, jsonb, jsonb);
  drop function if exists public.nyay_append_turn_event(uuid, uuid, uuid, text, jsonb, text, integer, text);
  drop function if exists public.nyay_admit_turn(uuid, uuid, text, text, text, integer, timestamptz);
  drop function if exists public.nyay_decide_editorial_proposition(text, text, text);
  drop table if exists
    public.nyay_legal_relations,
    public.nyay_legal_provisions,
    public.nyay_usage_budgets,
    public.nyay_gmail_dispatches,
    public.nyay_gmail_approvals,
    public.nyay_gmail_evidence_messages,
    public.nyay_drive_manifests,
    public.nyay_drive_case_folders,
    public.nyay_provider_secrets,
    public.nyay_provider_connections,
    public.nyay_verified_contacts,
    public.nyay_editorial_propositions,
    public.nyay_editorial_reviewers,
    public.nyay_submission_steps,
    public.nyay_user_actions,
    public.nyay_case_documents,
    public.nyay_user_keys;
  ```
- Next unresolved external dependency: Supply `SUPABASE_ACCESS_TOKEN` (or apply `supabase/migrations/20261119120000_package1_auth_durable_cases_and_runtime.sql` and `supabase/migrations/20261119140000_package4_to_7_workflows_google_and_knowledge.sql` via Dashboard SQL Editor and run `npx supabase functions deploy nyay-api --project-ref daojcrxjjkqoirqbvhjn`) to transition Packages 1–7 from `tested locally` to `deployed` / `verified hosted`.
