# Third party notices

V2 reuses the existing application and locked dependencies. No additional public repository implementation was copied for the primary-agent redesign. See `docs/v2-reuse-and-licenses.md` and `docs/v1-source-manifest.json` for reuse provenance and the unresolved PDF distribution/license decision. Statements below describing the fresh implementation refer to the original V1 work.

Nyay Saathi is a fresh implementation. No reference repository was adopted wholesale.

The 2026-11-06 task-publication repair adapts the application's existing source parser, canonical citation pattern, LangGraph checkpoint workflow and locked LangChain/OpenAI/Pydantic integrations. The unit contracts, claim verifier, deterministic composer, task policies and staged-update connections are application-specific code. No new external code, data, asset, dependency or model was copied; the existing notices and attributed patterns below continue to apply.

The independent request-routing increment reuses existing LangGraph/LangChain, OpenAI SDK, source fetching/parsing, anonymous SQLite persistence and citation components under the notices below. New contracts, task policy, entity candidates, transition validation and offline runner are application-specific code. No additional third-party code, dataset, asset, dependency or model was adopted. Current official documentation and compatibility versions are recorded in `docs/research-log.md`.

The 2026-11-06 complaint-resolution increment reuses the existing anonymous persistence, LangGraph, source/citation, python-docx and ReportLab integrations. Journey projections, recipient playbooks, preparation policies and channel strategies are application-specific new code. No additional repository code, dataset or asset was copied; previous notices below continue to apply. Platform policy text was not reproduced wholesale.

The 2026-11-06 public-research integration reuses the application's existing source-discovery, ingestion, citation and graph components and the already locked OpenAI/HTTPX/PyMuPDF libraries. Official OpenAI SDK type definitions and httpcore TLS implementation were inspected for API compatibility; no additional third-party implementation, dataset or asset was copied. Citation-format normalisation is application-specific code added alongside the attributed LawGlance-inspired resolver below.

- LangChain and LangGraph are used under their published licences. Documentation: https://docs.langchain.com/
- Chroma is used as the local vector store. Documentation: https://docs.trychroma.com/
- OpenAI client libraries are used for configured API integrations. Documentation: https://developers.openai.com/
- PyMuPDF, Tesseract integration, python-docx, ReportLab, React, Vite, and their transitive dependencies retain their respective licences. Exact versions are in `backend/uv.lock` and `frontend/package-lock.json`.
- LawGlance `citations.py` at commit `1a3d7427c9381e2479379f7e477350e3ec472e86` (Apache-2.0) informed the supported-citation-marker resolution pattern. Nyay Saathi rewrites that concept for `[Source: title — locator]`, stable passage IDs, and its own schemas; no cache or RAG-chain code was copied. Source: https://github.com/lawglance/lawglance/blob/1a3d7427c9381e2479379f7e477350e3ec472e86/citations.py
- OpenAI Structured Outputs Samples at commit `7f4e3446ac9a081b2686314d028ce539b6f286f9` (MIT, Copyright 2024 OpenAI) informed the closed-schema and user-facing/internal-output separation pattern. The Next.js implementation was not copied. Source: https://github.com/openai/openai-structured-outputs-samples
- OpenNyAI (MIT) and LegalBench-RAG (MIT) were inspected for compatibility and evaluation ideas. No code was reused.
- Lexora was inspected but had no licence file at commit `87d62f4`; no code, data, or assets were reused.
- Official Indian statutory text and government guidance remain attributed to their issuing authorities and canonical URLs in the source register. Inclusion does not imply government endorsement.
