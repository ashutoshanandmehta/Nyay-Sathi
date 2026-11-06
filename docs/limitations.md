# Known limitations

Independent request interpretation/general public research is implemented and offline-tested, not live-validated. Consumer policies remain preparation policies rather than a complete filing-admissibility engine; other legal domains use bounded research/handoff. Unknown organizations and public websites do not establish legal authority. Calculated statutory deadlines are withheld without a validated clock policy. See [routing boundaries](request-routing.md) and [executed validation](../evals/reports/request-routing-2026-11-06.md).

- The legal corpus is deliberately limited to the supported consumer workflow. It currently has 621 searchable BM25 and Chroma passages drawn from 18 downloaded official documents plus selected provision-level excerpts. It is broader than the earlier sample but is not every Indian consumer instrument, state rule, order, circular, judgment, or an authoritative consolidated current-law service.
- The intake, evidence, procedure, drafting, and lawyer-preparation playbooks are application guidance written from official sources and remain pending review by an Indian lawyer. They are not legal authority.
- The selected Experion judgment has materially different homebuyer, Consumer Protection Act 1986, and RERA facts; subsequent treatment was not independently checked and the decision cannot predict a retail refund outcome.
- The Consumer Protection Act, principal rules, jurisdiction rules, procedure and mediation instruments, commencement notifications, e-commerce corrigendum/amendments, current government guidance, NALSA guidance and one selected Supreme Court judgment were downloaded from official hosts and hashed. Discovery pages themselves are not treated as claim-supporting passages.
- The official 2026 E-Commerce Amendment PDF has incomplete/corrupted extracted notification and commencement text. Its effective date remains unknown, and the app must not rely on it for applicability until manual Gazette verification.
- Landlord, employment, criminal, and other domains receive factual intake and handoff preparation only.
- No lawyer has reviewed the prompts, statutory excerpts, generated text, or evaluation results. Legal review is pending.
- Live chat generation, structured intake, 621-passage embeddings/retrieval, independent feedback review, and the multi-request non-delivery regression were smoke-tested after an OpenAI credential was configured. Transcription, Realtime speech and the operator web-discovery CLI were not live-tested in the final budgeted run.
- OCR requires the Tesseract executable and Hindi language data. Without it, scanned evidence is explicitly marked unavailable, partial, or unreadable.
- SQLite and the synchronous SQLite LangGraph saver are suitable for local or lightweight deployments, not horizontally scaled production.
- Anonymous browser ownership has no recovery or cross-device access. Clearing the owner cookie may remove access even while server data remains until deletion or an operator retention process.
- Local deletion cannot make claims about OpenAI retention, backups, filesystem snapshots, or exported copies.
- CSRF protection uses a double-submit token with SameSite cookies. HTTPS deployment must set `COOKIE_SECURE=true` and retain restrictive origins.
- The application has practical safeguards but has not undergone an independent penetration test, privacy impact assessment, accessibility audit, or production reliability review.
- Automated checks establish software behavior, not legal correctness or likely case outcome.
