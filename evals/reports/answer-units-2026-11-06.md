# Task-scoped publication evaluation — 6 November 2026

This is an offline engineering evaluation. No live model/search evaluation was run and the configured user's API key was not used. New provider boundaries are tested with labelled doubles and network/model guards. This does not measure legal correctness, live routing accuracy, production latency or resolution rates. Lawyer review remains pending.

## Executed checks

- Backend pytest suite: **494 passed**, including new claim/dependency/freshness/coverage, public-search adapter, domain isolation, budget, staged-update transaction and compiled HTTP mixed-task tests. Exact result is saved in `../raw_outputs/pytest-answer-units-2026-11-06.xml`.
- Frontend: 11 tests passed; TypeScript/Vite production build passed.
- Playwright: 9 passed, 3 intentional desktop/mobile applicability skips. The backend runs with an empty API key; browser workflows cover chat, refresh, independent cases, uploads, composer clearing, mobile UI and system panels.
- Offline fault-injection runner: 12/12 contracts passed. All 7 expected supported task outputs were retained; 0 seeded forbidden phrases escaped. These are fixture-specific counts, not statistical estimates or semantic accuracy claims. Raw outputs: `../raw_outputs/answer-units-offline-2026-11-06.jsonl`; metrics: `answer-unit-metrics.json`.

## Significant regressions covered

| Scenario | Observed offline result |
|---|---|
| Failed milk safety assessment plus factual draft | Draft retained; unsupported safety verdict omitted |
| One failing task and two independent successful tasks | Both supported outputs retained |
| Canonical citation with a different generated title | Registry title rendered; generated title discarded |
| Correct passage ID attached to unsupported meaning | Claim withheld |
| Fraud with consumer-only evidence | Consumer evidence cannot support the task or invoke consumer vectors |
| FSSAI/RBI/FDA public discovery | General adapter preserves parsed URLs; consumer ingestion policy remains separate |
| Missing acknowledgement/style advice | Nonblocking supported text retained |
| Invented personal filing deadline | Affected claim withheld |
| Review timeout after approved content | Unchanged approved content survives; modified content cannot reuse approval |
| Material evidence changes under the same passage ID | Previous review invalidated |
| Unknown/unexposed evidence, duplicate reviews, unknown tasks | Affected output withheld |
| Missing/blocked/cyclic dependencies | Dependent content and incomplete artifact withheld |
| Compiled HTTP mixed task | Partial response, staged facts and draft persist; retry does not duplicate or regenerate |
| Staged proposals and concurrency | Other owners denied; stale CAS rolls back; deletion removes proposals |
| Follow-up context | Recent turns, current edited draft, contradictions and IST date reach generation/review |

## Historical evidence and future live runs

The earlier five-prompt live evaluation remains a historical result under `five-public-prompts-20261106T152947Z.md`. It was not rerun. Its saved interpreter output, source sets, final answers and review findings informed these fault cases. Original generated candidates were not saved, so this report does not claim to replay those exact model outputs. The new runner uses explicitly labelled synthetic candidate/reviewer fixtures and does not copy expected output into actual fields.

Future live evaluations must explicitly use the configured budget and record actual candidate units, claim/task reviews, tool executions, case versions, sources, model IDs, prompt hashes, latency and usage. Public retrieval precision, source-filtering loss, research reuse rate and false rejection in real traffic require representative live/human-labelled data; they were not estimated from these fixtures.

Existing dependency warnings concern PyMuPDF SWIG and Chroma embedding configuration deprecations; they do not fail the checks. No dependency was upgraded in this increment.
