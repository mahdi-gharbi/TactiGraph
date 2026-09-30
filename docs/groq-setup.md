# Optional Groq analyst

The user approved an optional hosted LLM on 25 September 2026, replacing the earlier
local-only preference for interactive claim selection. Analytics, training and numerical
verification remain local. Public live generation is still disabled. Qwen3 remains optional.

Initial candidate: **`openai/gpt-oss-20b`**, via Groq's Chat Completions endpoint with
strict JSON schema. It is the fixed integration candidate, not a winner selected by model
comparison. Its separate provider evaluation is recorded below.

1. Create a standard project API key at https://console.groq.com/keys.
2. Keep the account on the Free plan for the no-paid-inference requirement. Check model
   access and quotas in your Groq console. The application cannot infer billing-plan status
   from a key and does not upgrade plans or provision paid services.
3. In the project's ignored `.env` file, set:

   ```dotenv
   GROQ_API_KEY=your_key_here
   TACTIGRAPH_GROQ_MODEL=openai/gpt-oss-20b
   TACTIGRAPH_GROQ_TIMEOUT_SECONDS=20
   ```

4. Restart the Python backend. In Evidence Analyst, select Groq and generate a comparison.
   No model download is needed for this provider. A missing key, quota error, network failure
   or invalid claim selection yields a labeled deterministic fallback.

Do not paste the key into chat, commit it, or put it in a `VITE_` variable. The frontend
never receives it. The local Compose configuration explicitly passes `GROQ_API_KEY`
from the project's `.env` to its backend container; it is never baked into the image.

Only the intent and already verified aggregate claim text are sent to Groq. No raw event
sequences, event UUID lists, database access, arbitrary user prompt or executable tools are
sent. The LLM returns claim IDs, which are validated for membership, duplicates and the
required core claim. At most one repair is allowed. All limitations remain appended.
Returned prose and numbers are never displayed. Error bodies are not reflected to clients.

Metadata records provider, requested/returned model, request ID, optional system fingerprint,
token counts, latency, repairs and rejection/fallback status. Hosted model weights cannot
be digest-pinned; the fingerprint is not a weight checksum. Real quality, latency and quota
behaviour are recorded separately from deterministic correctness. Unit tests use mocked
responses; the benchmark below uses real Groq requests.

## Provider regression evaluation — 25 September 2026

`tactigraph evaluate-analyst --groq` freezes the provider protocol, case checksum and
code hashes before evaluation, spaces requests by six seconds, and checkpoints every case.
An unchanged rerun reuses completed cases/results; changed code requires a new version.
Publish the exported summaries with `tactigraph publish-analyst`.

Results: development 30/30 and held-out-match partition 30/30 machine checks passed.
There were 20 real selections in each partition (40 total), with no repair, rejection or
deterministic fallback. The other 20 cases were refused before contacting Groq. Generation
p95 was 21.13 seconds for development and 12.76 seconds for the held-out-match partition;
these are end-to-end client request timings on this connection, excluding benchmark pacing.
Token totals were 11,092 input and 3,750 output across the 40 selections, excluding the
initial connection smoke test. No billing amount is inferred from token counts.

This reuses the authored cases already inspected for the deterministic workflow. It is
a provider regression evaluation, not a fresh unseen-question test or a general chatbot
benchmark. The model selects approved claim IDs; it does not author prose, compute facts
or choose arbitrary tools. Independent human semantic review remains pending.

The public aggregate is `experiments/analyst-v1/groq-results.json`; no key or raw-event
lists are exported. The Experiments page separates provider selections, refusals,
fallbacks, repairs, tokens and latency.

References: https://console.groq.com/docs/structured-outputs and
https://console.groq.com/docs/rate-limits (checked 25 September 2026).
