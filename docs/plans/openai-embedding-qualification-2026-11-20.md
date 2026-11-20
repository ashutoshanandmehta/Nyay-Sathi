# OpenAI 384d legal embedding qualification — 20 November 2026

Admission remains paused. No hosted migration, function deployment, secret change, Vercel change, or Sol live evaluation was performed.

The approved replacement is `text-embedding-3-small` with `dimensions=384`, configuration version `openai:text-embedding-3-small:dimensions=384:v1`. All 50 passages were re-embedded and the JSON corpus, guarded SQL bootstrap, Edge bundle, migration defaults, verification query, and offline query fixtures now use the same space. E5 vectors are not mixed with the new corpus.

## Provider execution evidence

- Successful corpus rebuild: 50 passages, 22,369 input tokens, four bounded requests.
- A first four-request attempt reached the API successfully but the local writer failed on Python 3.9 `zip(strict=...)` before persisting vectors. The retry was deliberate and bounded. Content-hashed checkpoints were then added; a later rebuild completed with `requests: 0`.
- Raw semantic evaluation: 15 cases, expected recall@5 `0.8333`, no temporal forbidden hit. Raw Hindi semantic ranking alone missed both expected passage sets, so raw semantic performance was not accepted as the production gate.
- Production SQL hybrid evaluation after model-specific calibration: all 15 inherited English/Hindi/Hinglish/historical/unsupported cases passed, plus one general-current-law case with a null incident date. Lexical RRF weight is 2, semantic weight is 1; strong/corroborated cosine floors are 0.40/0.30. Unsupported queries are rejected by the coverage boundary rather than cosine alone.
- Every runtime embedding call includes a recorded canary. Wrong model/index/dimension/norm or canary cosine below `0.99999` fails closed and prevents silent provider-alias drift.

## Verification

- `npm test -- --maxWorkers=1`: 157 tests in 20 files passed.
- `npm run build`: passed; existing >500 KB chunk warning remains.
- `npx --yes deno check --sloppy-imports supabase/functions/nyay-api/index.ts`: passed with Deno 2.9.6.
- Rebuild replay: zero provider requests from the content-hashed checkpoint.
- Secret scan/review: the live key is only in ignored `.env`, mode 600. No key is present in tracked fixtures or checkpoints.

## Remaining release gates

- **8/10 high:** embedding calls are not reconciled into the SQL generation budget. Keep admission paused until an OpenAI project hard cap is verified or embedding usage is added to the durable budget ledger.
- **7/10 high:** hosted migration history, seed counts/RLS, Edge secret, canary call, latency, and recovery have not been verified on `daojcrxjjkqoirqbvhjn`.
- **6/10 medium:** query text leaves Supabase and may contain personal data. Confirm the project's retention control/ZDR eligibility and operational privacy decision before pilot traffic.
- **5/10 medium:** the public model ID is an alias. The canary fails closed on material drift, but provider changes can make retrieval unavailable until a complete re-embedding and requalification.
