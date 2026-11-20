# Android and Supabase migration

Target selected by the owner: **all backend execution on Supabase**, with the existing React UI bundled into an Android Capacitor app. The existing Vercel demo remains on its existing Python backend and deployment. This document supersedes the older hosting proposal only for the Android version.

## Deployment separation

- Work branch: `codex/android-supabase`. Do not push to the Vercel deployment branch or change the Vercel project's environment or routes as part of mobile work.
- Existing browser development uses `VITE_BACKEND=legacy` by default. No Supabase authentication is initialized on that path.
- Android uses `VITE_BACKEND=supabase` and calls `/functions/v1/nyay-api/api/...` at the configured HTTPS Supabase project origin.
- Android project URL supplied by the owner: `https://daojcrxjjkqoirqbvhjn.supabase.co`, organization “Nyay Sathi” (`eatddnxpdlcocibvfohd`). Dashboard access was confirmed on 19 November 2026 and the initial seven-table migration was applied there. The project is in Tokyo (`ap-northeast-1`). The connector currently fails with `Unknown tool` before reaching Supabase; the authenticated dashboard was used as a fallback.
- The other connected project, containing health-app tables, is not the target and must not be changed.

## Implemented locally

- Capacitor 8 Android project with the existing React assets, provisional package ID `in.nyaysaathi.app`, HTTPS local origin, no cleartext/mixed content, no Android backup of app data, and microphone manifest permission. No custom app icon or signing key has been created.
- Android sync/open/run npm commands.
- Optional Supabase transport, public-key validation, lazy session initialization and single-flight anonymous sign-in. Native builds fail clearly if left on the same-origin legacy backend.
- Only same-origin `/api/` calls are mapped to the configured function. External provider requests and citation URLs do not receive Supabase or BYOK credentials. Supabase calls omit cookies and the browser CSRF header; redirects are rejected.
- Initial PostgreSQL migration for independent cases/conversations, case memory, messages, drafts, turn execution identities and durable stream events. All tables have RLS and explicit grants. Trusted answer, memory and turn records are not client-writable. Composite ownership foreign keys prevent cross-owner associations. An invoker RPC creates a case/chat atomically under RLS.
- The foundation migration is also applied to the hosted Android project. A post-migration query confirmed seven tables, RLS enabled on every table, no unauthenticated SELECT grants, and no authenticated INSERT grants on trusted message/memory/draft/turn tables. See `supabase/deployment-receipts/2026-11-19-foundation.md`.
- Package 1 & 2 schema extension (`supabase/migrations/20261119120000_package1_auth_durable_cases_and_runtime.sql`) reconciles `20261119091306` migration history idempotently, adds 7 additional RLS-protected tables (`nyay_user_keys`, `nyay_case_documents`, `nyay_user_actions`, `nyay_submission_steps`, `nyay_editorial_reviewers`, `nyay_editorial_propositions`, `nyay_verified_contacts`), extends `nyay_turn_executions` with `lease_token` and `generation` fencing, extends `nyay_turn_events` with per-execution monotonic `seq` and block metadata, and adds 4 transactional RPCs (`nyay_admit_turn`, `nyay_append_turn_event`, `nyay_commit_turn`, `nyay_decide_editorial_proposition`).
- Package 4–7 schema extension (`supabase/migrations/20261119140000_package4_to_7_workflows_google_and_knowledge.sql`) adds 10 additional RLS-protected tables (bringing the total schema to 24 RLS-enabled `nyay_*` tables): `nyay_provider_connections` and separate service-role-only `nyay_provider_secrets` (`REVOKE ALL` from `anon, authenticated`), `nyay_drive_case_folders` and `nyay_drive_manifests` (opaque folder names, SHA-256 duplicate-safe idempotency, moved/deleted/revoked reconciliation), `nyay_gmail_evidence_messages`, `nyay_gmail_approvals` (payload-hash binding), and `nyay_gmail_dispatches` (ambiguous timeout reconciliation), plus `nyay_legal_provisions`, `nyay_legal_relations`, and `nyay_usage_budgets`.
- Package 3 Android native bridges (`frontend/android/app/src/main/java/in/nyaysaathi/app/MainActivity.java`, `AndroidManifest.xml`, `res/xml/file_paths.xml`): `window.NyayNativeSecureStorage` backed by Android Keystore (`AES/GCM/NoPadding` 256-bit key wrapping `SharedPreferences`), `window.NyayNativeFiles` for native `FileProvider` saving/sharing of PDF/DOCX/JSON exports, hardware back-button drawer/menu dismissal (`window.__nyayHandleBackPress`), and `in.nyaysaathi.app://oauth-callback` deep-link forwarding.
- Full TypeScript/Deno `nyay-api` Edge Function (`supabase/functions/nyay-api/`) implementing Auth verification, independent cases and multi-chat reopening, lease-fenced turn execution, urgent safety with injected clock and contact expiry suppression, certified legal knowledge pre-retrieval, transitional BNS/BNSS vs IPC/CrPC temporal applicability resolution and corrective retrieval diagnostics, risk-calibrated mechanical checks, disguised-law blocking, independent semantic review, targeted repair, case-patch authorization, sequenced `nyay.stream.v1` SSE with `after_seq` reconnect replay, upload malware/JS blocking and bounded PDF extraction, WebCrypto `AES-256-GCM` BYOK sealing and transfer bundles, Google Drive case folder & manifest adapter (`drive.ts`), Gmail correspondence & payload-bound send approval adapter (`gmail.ts`), and editorial reviewer role enforcement.
- Desired product screens (`frontend/src/components/ActionWorkflowsPanel.tsx`, `Drawer.tsx`, `App.tsx`, `UserKeyCard.tsx`): Three-Action Home (`Know My Rights`, `Resolve a Complaint`, `Report Financial Fraud`), `My Cases` screen supporting multiple conversations per case, 7-section Case Workspace (`Overview`, `Evidence`, `Legal Basis`, `Documents`, `Communications`, `Timeline`, `Next Actions`), distinct outcome lifecycle tracker (`submissions`, `promises`, `processed_refunds`, `remedy_receipt`, `closure`), Verified Official Contact Cards, Drive Evidence Manifest controls, Email Review & Payload-Bound Approval screen, and Settings/Privacy controls.
- Executable runtime feasibility benchmarks (`frontend/src/runtime-feasibility.test.ts`), end-to-end vertical-slice integration tests against embedded PostgreSQL (`frontend/src/nyay-api-vertical-slice.test.ts`), Section 6 Golden Scenario & Security evaluation suite (`frontend/src/package4-to-7-golden-scenarios.test.ts`), Android native bridge & UI suite (`frontend/src/components/package3-to-6-ui.test.tsx`), and full execution ledger (`docs/plans/agy-upgrade-status.md`).

## Not implemented or released yet

The backend rewrite is **not complete**, and the app is not ready for a public Android release. No Edge Function has been deployed. Do not enable the Supabase mode for demo users yet.

Required work before cutover:

1. Database foundation is applied. Restore the connector for reliable deployment/inspection and run hosted security/performance advisors. Preserve the existing schema and apply subsequent reviewed migrations incrementally.
2. Enable/configure Auth for guest and account flows, abuse prevention and eventual account linking. Use native secure token storage for a production Android release; current SDK persistence is WebView storage.
3. Port the existing API contracts to `nyay-api` Edge Functions. Preserve ownership checks and distinguish unknown routes from capabilities still being migrated.
4. Port the primary reasoning/research loop, strict answer schemas, mechanical checks, claim/dependency validation, independent semantic review and targeted repair. Replay the existing failure fixtures. Do not replace the verified pipeline with a single unrestricted chat completion.
5. Implement atomic turn leases/commits, version checks, payload-hash replay checks, approved-content persistence before SSE, reconnect/event replay and final reconciliation. Keep review and coherent-answer gates before consequential advice is visible.
6. Port public corpus retrieval and bounded official-source acquisition. Indexing, reranking, parsing and amendment maintenance need workloads compatible with Supabase's CPU, memory and duration limits. Use persistent jobs for work that exceeds one invocation; streaming does not remove worker duration limits.
7. Replace Python PDF/OCR/export dependencies with tested runtime-compatible implementations or revise those capabilities explicitly. Preserve Hindi, evidence provenance, original documents, consent and output fidelity. No external Python host is authorized for this target.
8. Port BYOK key sealing/usage, voice/live-session routes, roleplay, case actions, journey, transfers, drafts and document exports. Backend secrets belong in Supabase secrets; never in `VITE_*`, the APK, generated assets or Git.
9. Add mobile back-button behavior, OAuth deep links, runtime microphone permissions, safe-area/keyboard verification, native file saving/sharing and external-link handling. A browser download link alone does not establish Android export support.
10. Run the API compatibility/security suites, two-user isolation tests, retry/disconnect tests, before/after quality/latency evaluation, and actual emulator/device testing. Produce a signed AAB only after release requirements are met.

Drive and Gmail from the larger blueprint are additional capabilities; they are not supplied by merely adding Supabase or packaging the frontend.

## Local commands

```sh
cd frontend
npm ci
npm test
npm run build
```

For an Android migration build, create ignored `frontend/.env.local` from `.env.example`, set `VITE_BACKEND=supabase`, the target project URL and its **publishable** key, then run:

```sh
npm run android:sync
npm run android:open
```

Never change the Vercel project's settings to these Android values. Do not commit `.env.local`. With no deployed mobile API this is a container/transport test build, not an operational replacement for the demo.

Capacitor's generated Android project uses Java 21 and SDK 36. At setup time, only Java 11 was found and Android Studio/SDK were not found in the standard macOS locations, so APK/AAB compilation was not claimed. Install Android Studio and its supported JDK/SDK, configure the local SDK path, then validate on device. The source has been generated and the React build verified; no APK has been built or signed.

## References

Verification on 19 November 2026: all **98 frontend/transport/golden-scenario/database-policy tests across 13 test files passed** (plus **359 Python backend tests passed**); `npm run build` passed; `cap sync android` passed. Ownership-behavior, Drive manifest, Gmail payload-bound approval, usage-budget enforcement, and transitional legal knowledge tests ran against embedded PostgreSQL with test Auth roles across all 24 RLS-enabled `nyay_*` tables. The hosted schema's foundation RLS and grants were separately queried after applying the initial migration through the authenticated dashboard. No Vercel deployment, Edge Function deployment, APK compilation or paid model call was performed.

- [Capacitor installation](https://capacitorjs.com/docs/getting-started)
- [Android environment](https://capacitorjs.com/docs/getting-started/environment-setup)
- [Supabase Edge Functions](https://supabase.com/docs/guides/functions)
- [Edge Function limits](https://supabase.com/docs/guides/functions/limits)
- [Supabase anonymous sign-in](https://supabase.com/docs/guides/auth/auth-anonymous)
- [Row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
