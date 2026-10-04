# Bilingual Evidence Analyst

In the local application, select a league and match, open **Evidence Analyst**,
then choose **Question libre / Free question**. Select the team, language and form
windows. Ask, for example:

> Compare la création d’occasions entre les minutes 45–60 et 60–75, et explique le xG.

The interpreter returns one typed plan. Python executes progression, chance
creation or passing concentration, builds numerical sentences from fixed EN/FR
templates, and verifies every claim against the tool results. BM25 retrieves exact
definition excerpts from the bilingual methodology-v2 corpus. The provider never
supplies the displayed values, citations, SQL or prose definitions.

## Context and limits

- Match and team IDs come from the selected server-validated context. Another named
  context requires changing the selection. The league prefix selects its database.
- No times mentioned: use and display the form windows. Explicit absolute minutes
  45–60 / 60–75 mean second-half minutes 0–15 / 15–30. Relative half minutes are
  accepted. Windows remain ordered, non-overlapping, within one covered period.
- An incomplete interval such as “after minute 60” requires clarification.
- One comparison and at most two methodology topics per question.
- Causal claims, guaranteed outcomes and unavailable off-ball observations abstain.
  Questions explaining these methodological limitations are supported.
- Missing models omit their metrics. Unusable sources or insufficient evidence
  prevent a verified numerical answer. No missing value is replaced with zero.
- Provider errors and the total 30-second deadline offer the guided form. One
  schema-repair attempt is included in that deadline, including Groq's structured
  output validation rejection. Changing match, team, language, text or windows
  invalidates the visible answer and any pending request.

## API

`POST /api/v1/analyst/query` accepts `question`, `language` (`fr` or `en`),
`match_id`, `team_id`, `before` and `after`. Windows contain `period`, `start_ms`
and `end_ms`. The defaults are second-half 0–15 and 15–30 minutes.
Premier League uses `/leagues/premier-league/api/v1/analyst/query`.

Responses have `status` (`answered`, `clarification_required`, `abstained`),
`message`, interpreted `plan`, optional `report`, cited `methodology`, `metadata`
and stage `trace`. Query reports have their own version and language-specific ID.
Existing `/analyst/report` contracts and saved v1 reports remain readable.

Metadata records provider/model/fingerprint, attempts, repairs, observed token
usage, provider failures, fallback reason, duration and effective corpus/method.
`usage_complete=false` means a failed call did not report its consumption; the
observed token counts are then a lower bound. Monetary cost is left unset.

The local `/api/v1/operations` endpoint exposes bounded process counters and sampled
latencies. JSON request logs include a random request ID, route template, status,
DB durations and analyst stages. They exclude prompts, credentials, SQL text,
concrete event paths and request bodies. Counts reset with the process.

## Reproduce

Configure the existing Groq adapter as described in [Groq setup](groq-setup.md),
then rebuild and start the application. The pinned GPT-OSS 20B model supports strict
structured outputs according to [Groq's documentation](https://console.groq.com/docs/structured-outputs).

```powershell
.\.venv\Scripts\tactigraph.exe openapi
npm.cmd --prefix frontend run types
npm.cmd --prefix frontend run build
.\.venv\Scripts\tactigraph.exe serve
```

For a bounded real integration check, use existing IDs in the selected league:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_query_live.py --match 19717 --team 968 --output output/query-v2/my-smoke.json
```

This makes two real Groq integration calls using the user's example,
with consumption returned by the provider. It is separate from the reviewed
benchmark. It checks the intended plan, windows, citations and all numerical claims.
Results cannot establish population accuracy. Final benchmark and human quality
scores remain pending in the [review protocol](evaluation-v2.md).

## Publication

GitHub hosts the source repository. It does not host this application. Interactive
query endpoints are local-only and return 404 in public mode. Opening interactive
public access requires a separate access, quota and inference-budget decision.
The existing showcase still requires its independent report/publication approvals.
