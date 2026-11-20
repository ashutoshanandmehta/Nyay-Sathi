# Hosted multilingual E5 qualification

20 November 2026. Target Supabase project `daojcrxjjkqoirqbvhjn`, Tokyo. **Result: failed to qualify; stop the Supabase WASM approach.** The only hosted mutation was a disposable benchmark. The target had no application Edge Functions and no resumable or legal corpus tables. Its foundation table exists and the CLI migration ledger returned empty. Admission was never opened. Sol Medium, budget reconciliation, observability and the protected Vercel demo were unchanged.

## Limits and artifact

Supabase documents 256 MB memory, 2 seconds CPU per request, a 150-second request idle timeout, and a 150-second Free worker lifetime. Function bundles are limited to 20 MB via local CLI and 5 MB via server-side bundling. The built-in embedding model is English-only `gte-small`. The worker’s embedding call has a separate three-second deadline. [Edge limits](https://supabase.com/docs/guides/functions/limits) · [Supabase AI models](https://supabase.com/docs/guides/functions/ai-models)

The reference is `Xenova/multilingual-e5-small@onnx-int8`, revision `761b726dd34fb83930e26aab4e9ac3899aa1fa78`. The 118,308,185-byte ONNX artifact has SHA-256 `f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193`. The local tokenizer digest is `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`. Both hosted attempts streamed and SHA-256-checked the exact weights. Token IDs were prepared from the original tokenizer for fixed English, Hindi and Hinglish inputs. Tokenization was deliberately excluded from hosted measurements so the model could be tested with less overhead. [Pinned upstream revision](https://huggingface.co/Xenova/multilingual-e5-small/tree/761b726dd34fb83930e26aab4e9ac3899aa1fa78)

## Two focused hosted attempts

| Attempt | Client cold wall time | Verified model available in worker | Reported memory at failure | Result |
|---|---:|---:|---|---|
| v1, streamed model and pinned CDN WASM loader | 17,564 ms | 12,101 ms | 8.35 MB used JS heap, 124.03 MB external | Node compatibility loader rejected the HTTPS module URL. Request `01a1f64d-fc15-7864-a706-0caf55b2eb92`. |
| v2, streamed model and package-local WASM loader, one thread | 17,918 ms | 12,091 ms | 8.63 MB used JS heap, 124.88 MB external | WASM initialization rejected shared memory before inference. Request `01a1f64f-0cdd-70aa-b580-c714b78776b5`. |

The function logs corroborate both download and failure stages. Hosted RSS was reported as zero by Deno, so these fields do not establish a full memory peak. Both invocations returned diagnostic envelopes with no vectors. Warm latency, hosted inference CPU and hosted retrieval parity could not be measured. Download time alone exceeded the client deadline by about four times on both cold workers. This is evidence against the tested design and runtime, not an assertion that every possible E5 implementation exceeds memory.

The probe `nyay-e5-qualification` was replaced with an inert version 3. A subsequent HTTPS request returned **410**. The temporary benchmark credential was destroyed. The version remains registered because the CLI has no management access token and the connector has no delete operation. The inactive route does not download artifacts, accept case data or generate embeddings.

## Local comparison

On the Mac, the native reference loaded the model in 1,194 ms after imports. One embedding per language took 5–19 ms wall and 21–45 ms CPU. Peak process RSS was 653 MB (decimal). With the fallback local WASM package loader, one run initialized in 2,291 ms and took 165–623 ms per embedding. Peak process RSS reported by the host timer was 722 MB. A separate ranking run initialized in 1,035 ms and took 67–225 ms per embedding. These are workstation measurements and include runtime allocations.

| Query | WASM cosine vs. native reference | Expected passage | Hybrid rank, native / WASM | Semantic rank, native / WASM |
|---|---:|---|---:|---:|
| English | 0.997945 | RBI failed-transfer turnaround | 2 / 2 | 2 / 2 |
| Hindi | 0.998113 | E-commerce refund provision | 1 / 1 | 3 / 3 |
| Hinglish | 0.997380 | RBI failed-transfer turnaround | 4 / 4 | 6 / 5 |

The synthetic comparison used the seeded corpus and actual hybrid SQL RPC in PGlite with normalized local vectors. `supabase/benchmarks/e5/edge-probe.ts` type-checks with Deno 2.9.6. `probes.ts` contains only fixed token IDs and reference vectors. For a local reproduction, load the pinned ONNX file with `probe(() => Deno.readFile(path), callback)`, write callback vectors keyed by language to a JSON file, then run `node supabase/benchmarks/e5/local-rank.mjs <vectors.json>` from the backend worktree.

## Concrete managed inference alternative

Use **Hugging Face Protected Inference Endpoints** with a custom CPU container, one 2 GB replica, and the exact ONNX model and tokenizer above pinned by digest. Select Tokyo if the required SKU is available. Confirm the actual region and terms before provisioning. Reuse Antigravity’s native ONNX preprocessing and emit the existing `{model,version,embedding}` contract. No change to indexed vectors or the Supabase application boundary is necessary if parity passes. The endpoint must enforce bounded input and avoid logging payloads or tokens. [Protected endpoints and data handling](https://huggingface.co/docs/inference-endpoints/guides/security) · [Custom containers](https://huggingface.co/docs/inference-endpoints/guides/custom_container)

Proposed trial cap: **US$2 of incremental inference spend**, a single replica capped at the published US$0.033/hour rate, at most 24 billable hours, approximately **US$0.79** before tax and other charges. Schedule a pause after the trial and verify it reached the paused state. Keep automatic credit recharge off and require a verified prepaid cap that blocks usage at exhaustion. The 24-hour stop alone is an operational cap. If the provider account cannot enforce the credit cap, or the SKU, subscription or fees exceed the ceiling, leave provisioning blocked pending approval. No managed endpoint or paid subscription was created. [CPU pricing](https://huggingface.co/docs/inference-endpoints/pricing) · [Billing and credits](https://huggingface.co/docs/hub/en/billing)

Query text can contain personal or case details and would leave Supabase for the inference processor. The managed trial should use synthetic queries only. Confirm endpoint region, vendor terms and credential scope before case data. Hugging Face states it does not store endpoint payloads or tokens and retains operational logs for 30 days. Disable request-body logging in the custom container and verify that behavior. Separate embedding credentials from the Sol key.

Before connecting the endpoint, run byte and tokenizer parity checks, compare normalized outputs and expected passage ranks with the local references, and verify English, Hindi, Hinglish, historical and unsupported queries. Measure cold, warm and post-idle times. A ready replica must reliably answer within the worker’s three-second budget. Prewarming is an additional cost and does not itself pass the test. Only then proceed with the [hosted migration checks](legal-retrieval-integration-rollout.md). Keep ordinary admission paused and use a restricted test path for up to three synthetic Sol Medium runs with a separate US$4 ceiling and the existing reservation and reconciliation checks. Record usage and verify citations and independent review. Hosted migrations and the live Sol evaluation remain gated and were not run.
