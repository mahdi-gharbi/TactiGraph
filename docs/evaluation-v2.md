# Query v2: review first, measure second

Query v2 adds bilingual question interpretation and deterministic methodology search.
The existing guided analyst, v1 retrieval experiments, and stored reports keep their
original results. The new corpus has eleven topics in English and French (22 chunks).
It uses accent-normalized BM25 in both local and public images, with no encoder or
optional model download. Chunk IDs include the version, topic and language. Retrieval
returns definitions, never match statistics.

## Current status

The query-v2 evaluation set is **draft and unreviewed**. There are 100 semantic
scenarios, each with an English and French question. The 200 language variants are
correlated and must not be represented as 200 independent observations. The split is
60 development / 40 final semantic scenarios, with translations and parameterized
scenario families kept together. Categories are 50 analytical comparisons, 20
methodology questions, 10 mixed questions, 10 ambiguous requests and 10 unsupported
requests. Both WSL and Premier League are represented. Context uses a selected team
and match; the execution harness resolves concrete, existing IDs in each league.

The scenarios and translations were authored as a draft, including parameterized
window families. They are not independent ground truth. Proposed thresholds are
targets, not achieved measurements. No live-provider or final benchmark is authorized
by preparing a worksheet. No human scores are supplied by the agent.

## Prepare independent schema and relevance review

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_query_review.py
```

`output/query-v2/schema-review-r2/packet.json` contains the frozen-content proposal:
protocol, bilingual questions, expected plans/statuses, relevance labels and both
corpus languages. `ratings.json` has blank reviewer/date fields and null decisions.
Give both files to a person who did not write the prompts, expectations or corpus.
The reviewer checks all 100 paired scenarios for:

- Answerability and intended analysis in the selected match/team context.
- Period-local, chronological, non-overlapping window labels.
- Equivalent French and English meaning, including ambiguity and refusal cases.
- Correct and sufficient methodology relevance labels.
- Accurate corpus definitions, interpretation limits and proposed evaluation policy.

The reviewer records their name, an ISO timestamp with timezone, independence
attestation, corpus/protocol approval and all per-scenario decisions. Questions about
what the data cannot show should be distinguished from requests to invent that data.
Every scenario and the full protocol/corpus have content hashes. Changing any input
invalidates approval. Corrections go into a new review directory; existing ratings
must remain intact. Re-exporting unchanged inputs preserves all existing ratings.

`validate_review` checks completeness, dates, attestations and exact content hashes.
It cannot authenticate a person's identity; reviewer independence remains a human
attestation. Do not fill these fields automatically or invent a reviewer.

## Freeze and execute

The `freeze` function in `analyst/query_evaluation.py` requires completed independent
review and a concrete candidate model. It records review, input, corpus and code
hashes, including prompts/contracts and the all-claim verifier. It never overwrites
an existing lock. A changed implementation requires a new reviewed version.

The injected runner calls `query.run_query` using the correct database/session for
each scenario's league. `context_resolver` supplies an existing `match_id` and
`team_id`; question/expected labels are never sent to the model as scoring guidance.
The evaluator passes only the question, language and selected UI context. Match
selection should be frozen before execution and satisfy required period coverage;
do not choose contexts based on response quality.

- `dev_smoke` requires a mock runner and uses only development scenarios. Its results
  are execution-contract checks; `metrics_are_model_evidence` is false and acceptance
  is explicitly `not_assessed_mock`.
- `development` with a live runner requires independent approval and unchanged freeze.
- `final` also requires that approval and freeze; do not use it to tune prompts,
  models, topics or thresholds. Retain the first final output and disclose any later
  access. Use a new experiment version for subsequent model selection.

The library never calls a provider by itself. The caller must label a real runner
as `live`; injecting a provider under the `mock` label would violate the protocol.
Exceptions and failed requests should be retained rather than selecting only successes.

## Metrics and denominators

The summary separates supported task success, correct clarification, and correct
unsupported abstention, each with its own denominator. A provider outage that happens
to return abstention does not count as successful unsupported-question handling.
Provider success uses attempted provider cases; fallback and supported-abstention
rates remain separate. Tokens and p50/p95 latency are recorded alongside model,
fingerprint and the effective retrieval method.

Repair attempts, provider error counts and cases with incomplete usage are recorded
separately. Input/output token sums include only observed provider-reported usage.
If any attempted request lacks complete usage, `token_totals_status` is
`observed_lower_bound`; a failed or interrupted request must not be assumed to cost
zero tokens. These figures do not establish billed cost. Schema reviewer and blinded
reviewer independence checks exclude both the project GitHub login `mahdi-gharbi`
and configured Git author name `mahdi elgharbi`, in addition to the agent/generic
author labels. Identity still requires the human independence attestation.

Every returned numerical claim is reconciled by the injected all-claim verifier;
the evaluator does not accept checking only one core metric. This validates tool
values and provenance contracts, not independent semantic correctness. Methodology
citations must resolve to exact chunk text, language, version, topic and document ID.
The current evaluator reports verified numerical reports, invalid methodology
citations and retrieval coverage separately.

Methodology retrieval is measured in two ways. Independent BM25 retrieval runs with
the query/language and **without** the interpreter's topic filter, against reviewed
relevance labels. End-to-end retrieval checks the chunks actually returned by the
query application. Report Recall@5 and MRR@5 with their respective case counts. Do
not attribute v1 MiniLM/hybrid results to this different v2 BM25 corpus or serving path.

## Blinded guided/query usefulness pilot

After schema approval, collect actual outputs for twelve fixed cases: two leagues ×
three intents × two languages. The same concrete context/windows must be supplied
to guided and query modes. Preserve the original outputs before hiding provider
metadata. This is a small pilot, not a population accuracy estimate.

The input JSON is a list of records with `case_id`, `league`, `intent`, `language`,
`question`, `guided` (actual report), and `query` (actual query response). Export with:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_query_blind_review.py --source output/query-v2/actual-pairs.json
```

The exporter requires all twelve cells, does not run a provider, and refuses empty
claim outputs. It assigns A/B deterministically from each exact pair hash, hides
provider/mode/latency metadata, and records both displayed and full-output hashes.
Give the reviewer `blind-packet.json` and the blank `ratings.json`. Keep
`private-key.json` away from them until scoring is complete. Do not invent a paired
answer to fill a missing case; retain and report that failure separately.

For each A/B answer score factual accuracy, source support, clarity of limits and
usefulness from 0 (wrong/missing/misleading) to 2 (correct/clear/useful), with 1 for
partial or ambiguous quality. Mark critical errors and explain every score below 2.
Choose A, B or tie only after inspecting both sources. `validate_pair_ratings`
rejects incomplete scores, missing notes, changed content, absent reviewer/date or
missing independence attestation. Preserve both reviewer scores when adjudicating
disagreements. Completion of this pilot does not approve the separate public release.

The existing twelve-report guided review remains available through
`scripts/prepare_human_review.py` and `docs/human-evaluation.md`.

## Workbench commands after review

`scripts/query_workbench.py` connects the gates to the actual local databases. Its
`prepare-review` command is safe now; it leaves all decisions blank:

```powershell
.\.venv\Scripts\python.exe scripts/query_workbench.py prepare-review --output output/query-v2/schema-review-r2
```

Copy `configs/query-context-v2.json.sample` to a private working path such as
`output/query-v2/contexts.json`. Its `null` IDs are placeholders, not usable example
matches. Supply existing positive match/team IDs for both leagues in development
and final, with different matches between partitions. Choose matches for complete
coverage of the proposed windows and available published models before reading
their query results. The tool verifies membership and source manifests; the freeze
records exact contexts and source hashes.

After the independent reviewer has completed the worksheet, run:

```powershell
.\.venv\Scripts\python.exe scripts/query_workbench.py freeze --contexts output/query-v2/contexts.json --review output/query-v2/schema-review-r2/ratings.json --output artifacts/analyst-query-v2/freeze.json
.\.venv\Scripts\python.exe scripts/query_workbench.py evaluate --phase development --contexts output/query-v2/contexts.json --review output/query-v2/schema-review-r2/ratings.json --freeze artifacts/analyst-query-v2/freeze.json --output output/query-v2/development-results.json
```

Those commands are intentionally blocked by the current blank worksheet. Evaluation
uses real Groq calls and records tokens and latency; monetary cost remains explicitly
uncalculated. It checks the frozen model, code, contexts and source manifests before
execution. Do not run it under a mock label or use the final set for selection. If
development work changes the candidate, create a new version and review/freeze it.

When the candidate is fixed and the final evaluation is appropriate:

```powershell
.\.venv\Scripts\python.exe scripts/query_workbench.py evaluate --phase final --contexts output/query-v2/contexts.json --review output/query-v2/schema-review-r2/ratings.json --freeze artifacts/analyst-query-v2/freeze.json --output output/query-v2/final-results.json
.\.venv\Scripts\python.exe scripts/query_workbench.py generate-pairs --result output/query-v2/final-results.json --contexts output/query-v2/contexts.json --review output/query-v2/schema-review-r2/ratings.json --freeze artifacts/analyst-query-v2/freeze.json --output output/query-v2/blind-review
```

The workbench writes a non-overwritable final-access marker **before** execution.
An interrupted final attempt still counts as inspection. Existing result files are
never overwritten. `generate-pairs` performs no provider calls: it selects analytical
scenario IDs deterministically before inspecting answer quality, loads their actual
final query responses, verifies recorded request/response hashes, and recomputes the
guided report for identical context, intent, windows and language. It reconstructs
omitted internal support IDs from that verified deterministic execution, then checks
every claim before export. A selected missing/failed answer stops export; it is never
silently replaced with a successful case. The two translations use the same selected
semantic scenario in each league/intent cell.

After the independent reviewer finishes the A/B worksheet:

```powershell
.\.venv\Scripts\python.exe scripts/query_workbench.py validate-pairs --packet output/query-v2/blind-review/blind-packet.json --ratings output/query-v2/blind-review/ratings.json
```

Only the worksheet validation is automated. Scores, reviewer identity, independence
and semantic judgments must come from the human reviewer.
