# Verification

## Additive analyst and diagnostics v2 — 4 October 2026

| Check | Observed result |
| --- | --- |
| Backend suite | **203 passed**; two upstream deprecations and a Windows core-count warning |
| Ruff / generated contracts / frontend build | Passed |
| Synthetic Chromium journeys | **6 passed**, desktop and mobile; guided/free bilingual output, citations, clarification, API error recovery, stale-team response rejection |
| Real Groq integration | User-example FR/EN questions answered on both leagues; intended windows and tool claims checked; separate from final benchmark |
| Scientific diagnostics | 20 seeded permutations/group; WSL 3,506 shots / 132 matches; EPL 1,551 / 57; original predictive metrics replayed |
| Constant calibration | Unavailable with reason; original v1 result files preserved |
| HTTP concurrency | 640 calls, 0 errors across 1 / 5 / 10 concurrent clients; actual sockets, invented fixture |
| Load p50 / p95 | 13.623 / 28.742 ms (n=40); 22.477 / 96.585 (n=200); 41.242 / 263.127 (n=400) |
| Recorded walkthrough | Three minutes; actual local FR/EN requests, proof opening and clarification |
| GitHub Docker verification | Production image built and started; public endpoint boundaries and exclusion of training runtimes pass |
| GitHub PostgreSQL / restore | Migration, invented ingestion, stored predictions, evidence and restore into a separate new database pass |
| Human review | Twelve v1 worksheets and 200-question v2 packet prepared; scores/approvals remain blank |

Load hardware: Intel i7-10510U, 8 logical CPUs, 21,300,441,088 bytes physical RAM reported
by Windows CIM. Client and single-process SQLite server share this Windows/Python 3.12.10
host. Chromium tests ran concurrently; background desktop load was uncontrolled.
These measurements exclude real-provider calls and cannot estimate production capacity.
[Full request counts, routes and conditions](../experiments/operations-v2/synthetic-http.json).

The WSL v1 lock already had a different original code hash before these changes.
Diagnostics disclose it, verify artifact/development hashes and reproduce all original
probability scores. The original v1 test cache had no recorded byte hash; v2 records
its first checksum after checking membership, sample counts and replayed scores.
These retrospective diagnostics are not a new untouched holdout evaluation.

The current independent quality benchmark is intentionally unrun while the user
prepares review for later. Proposed 90%/95% targets are not achieved-score claims.
Both GitHub jobs passed on implementation commit `e5a9656`: full checks and production
Docker smoke, plus PostgreSQL, backup/restore, desktop/mobile journeys and HTTP load.
The restore compares every invented-data table's row count and content fingerprint
before verifying the API. This is not a production recovery-time objective.
[Observed CI steps](../experiments/operations-v2/ci-verification.json) ·
[GitHub run](https://github.com/mahdi-gharbi/TactiGraph/actions/runs/37207971434).
The Docker daemon is unavailable on the local Windows host; Docker verification used CI.

## M5 graph experiment — 24 September 2026

| Check | Observed result |
| --- | --- |
| Backend suite | 81 tests passed; two upstream TestClient deprecation warnings |
| Ruff, generated API types, TypeScript and Vite | Passed |
| Browser journeys | 18 passed: 9 desktop and 9 mobile, including graph evaluation and cutoff evidence |
| Development graphs | 8,252 train / 3,893 tuning / 1,725 calibration; finite features, unique cutoffs and exactly one ball holder |
| Locked test | 6,607 eligible episodes from 132 matches, 566 positives |
| Graph study | Three seeds × full GINE plus four ablations; five team-disjoint stress groups |
| Decision | GNN not justified; serve the tuning-selected LightGBM baseline |
| Selected model | Log loss .249144, Brier .066991, PR-AUC .350951 |
| Stored predictions | 20,477 across 457 matches; test predictions agree exactly with the evaluated export |
| Independent checks | Log loss/Brier recomputed; all test cutoff references and episode labels reconciled |
| Prior models | Frozen xG and xT code hashes unchanged |
| Warm local API p95 | Graph report 6.93 ms; match prediction page 6.51 ms |
| Production | Docker image builds; PostgreSQL report/prediction parity passes in public mode |
| Runtime boundary | No Torch, PyG, NumPy, sklearn or LightGBM installed in the production container; raw-event API returns 404 in public mode |

Latency is 20 sequential calls after three warmups on this Windows machine, not a
production load guarantee. PostgreSQL parity covers the existing demonstration match
19717 and the aggregate graph report, not a full-corpus PostgreSQL import. Local private
verification output is `output/m5-verification.json`. Source datasets, per-event model
inputs and checkpoints are excluded from public images and Git. No cloud deployment or
paid inference was performed. Model selection and evaluation details are in the graph
model card and exported aggregate experiment.

## M4 tactical analytics and xT — 22 September 2026

| Check | Observed result |
| --- | --- |
| Backend suite | 65 tests passed, including hand calculations, terminal rules and test-label mutation |
| Ruff lint/format | Passed |
| OpenAPI / TypeScript / Vite | Passed |
| Playwright Chromium | 14 passed: 7 desktop, 7 mobile |
| Visual inspection | Networks, arrow direction, separate curves and xT surface inspected on desktop/mobile |
| Source reconciliation | Match 19717 pass/entry/field-tilt counts, edge weights and signed xT agree with independent raw-JSON calculations |
| Comparison benchmark | 20 warm sequential local requests, match 19717; p95 477 ms |
| xT procedure | 12×8 chosen on tuning Brier; 82,214 fitting episodes, 67 iterations |
| xT held-out evaluation | 132 matches; 35,899 episodes; 406 goals; Brier .010676; log loss .054245 |
| Uncertainty | 1,000 paired match-bootstrap draws against both baselines |
| Leakage | Test-label changes leave fitted training surfaces unchanged; no calibration/test rows in fitting |
| Prior experiment | Frozen xG code hash unchanged; xT code still matches its pre-test lock |
| Production image | Docker build passed; NetworkX included, model-fitting extras absent |
| PostgreSQL runtime | Comparison, trends and xT report serve without NumPy or sklearn |
| Database parity | Full match 19717 comparison payloads match exactly between SQLite and PostgreSQL |
| Publication boundary | Public analytical citations only; raw events remain local-only |

Source reconciliation for Arsenal in 45–60 / 60–75: 105/114 attempted passes,
89/95 completions, 11/10 final-third entries, and 30/25 both-team field-tilt
denominator passes. The performance sample used Python 3.12.10, Windows 10 build
19045, Intel family 6 model 142 stepping 12. This is one sequential local benchmark,
not a concurrency or production-host guarantee. Verification outputs/screenshots stay
in ignored `output/`; only aggregate model results are published under `experiments/`.

The 2023/24 test season had already been inspected during xg-v1. The xT protocol and
artifacts were locked before its own test evaluation; this prior-inspection limitation
is explicitly disclosed in the model card and UI. GNN/analyst/retrieval remain later milestones.

## M3 xG release — 22 September 2026

| Check | Observed result |
| --- | --- |
| Backend synthetic suite | 43 tests passed |
| Ruff lint and format | Passed |
| OpenAPI / TypeScript / Vite build | Passed |
| Playwright Chromium | 10 passed: 5 desktop, 5 mobile |
| Visual inspection | Desktop, mobile and reliability diagrams inspected; clipped mobile grid corrected |
| Frozen experiment | Feature/fitting code hash still matches the pre-test lock |
| Test access | One real final-test evaluation; repeat evaluation reads the stored report |
| Serving model | Logistic C=1, sigmoid rejected by the development rule |
| Final test | 132 matches, 3,506 non-penalty shots, 402 goals |
| Logistic probability scores | Log loss .314618; Brier .090669 |
| Probability uncertainty | 1,000 paired match-bootstrap draws; full intervals exported |
| Team stress | Five groups evaluated after excluding their fitting/calibration matches |
| Application predictions | 11,815 finite probabilities, all in [0,1] |
| Exclusion | One outside-pitch non-penalty shot remains in evidence but is not scored |
| SQLite/PostgreSQL | Match 19717 summary and all 30 shot probabilities/provenance identical |
| PostgreSQL migration | Revision 0003 preserves the existing match and accepts stored predictions |
| Production serving | Image builds; API works without scikit-learn or LightGBM installed |
| Private outputs | Source data, binary models and real-data verification fixtures remain ignored |

Tests now cover prefix/outcome mutation invariance, forbidden-feature exclusion, fitting
partition enforcement, held-out label mutation without artifact changes, immutable evaluation,
hand-calculated probability metrics, paired match bootstrap, prediction citations, partial
coverage and invalidation after source reimport. Browser tests reconcile rendered values
against the API and check actual panel bounds, rather than only document scroll width.

The serving decision was made on tuning. LightGBM's paired final-test log-loss difference
interval also crosses zero; no positive superiority claim is made. Public summaries omit
intercept/slope diagnostics for the constant prevalence predictor because they are not
jointly identifiable. No model predictions or selection decisions were changed during UI work.

See [the model card](xg-model-card.md), [frozen protocol](../configs/xg-v1.json) and
[aggregate results](../experiments/xg-v1/results.json). Local MLflow runs and complete
artifacts remain private under `artifacts/`. Reproduction instructions are in the README.

Two upstream TestClient/AnyIO deprecation warnings remain. xT, GNN, retrieval and analyst
acceptance targets remain unmeasured. No public deployment or paid API call was performed.

## M2 foundation verification (previous milestone)

These are observed implementation results, not predictive-model performance claims.

| Check | Observed result |
| --- | --- |
| Backend synthetic suite | 34 tests passed |
| Ruff checks and formatting | Passed |
| OpenAPI / generated TypeScript / production build | Passed |
| Playwright Chromium | 8 passed: 4 desktop, 4 mobile |
| Visual inspection | Desktop and mobile foundation dashboards inspected |
| Pinned corpus | 457 / 457 matches ingested and exported; no remaining failures |
| Independent source reconciliation | Every match's event-type counts match its cached source JSON |
| Resume | 452 completed matches skipped; five recovered; no duplicate records |
| Integrity audit | All nine checks passed |
| Split manifest | 194 train, 89 tuning, 42 calibration, 132 test |
| M1-to-M2 migration | Existing SQLite and PostgreSQL databases upgraded to revision 0002 |
| PostgreSQL repeat import | Same 3,510 events, 969 passes, 30 shots and 3,510 context rows |
| SQLite/PostgreSQL comparison | Match 19717 summaries identical |
| Docker | Multi-stage application image built and PostgreSQL integration verified |
| Private file boundary | `/data/tactigraph.db` returns 404 |
| Git exclusion | Raw data ignored; ingestion source remains versionable |

## Corpus reconciliation

At commit `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`, the complete import contains:

- 1,587,305 events, 431,009 passes and 11,816 shots.
- 660 players, 15 teams and 16,688 reconstructed lineup stints.
- 90,336 provider possessions and 130,384 control episodes.
- 812,139 episode-action memberships and one context record per source event.

A separate scan of all 457 cached event files compared event-type counts per match
against SQL counts: no mismatches. The audit also checks actor membership, episode
match/team/period consistency, split assignment, quality coverage and count reconciliation.
Full private reports are in `data/reports/foundation.json`, `source-reconciliation.json`
and `source-manifest.json`. Ten Parquet tables are exported for each match.

The frozen split uses 7 March 2021 as the last tuning date. Its SHA-256 is
`ab2d58e2a548f86911b5a80fe86a84a9634eb46a202a44d56f8abbbaed30cee4`.
EDA queries read only the 194 training matches. A synthetic test changes held-out
outcomes and verifies that training EDA remains identical.

## Source quality and explicit handling

Five matches initially failed strict coordinate bounds. Inspection showed finite source
coordinates just outside the nominal pitch. Normalization now preserves them and records
88 flags: 56 movement endpoints and 32 event origins outside the pitch. Spatial views
exclude these locations without clipping them; counts and evidence retain the events.
All five matches were successfully retried. No match is excluded from the corpus.

There are 11,924 events without locations, including event categories for which location
is inapplicable. No shots lack a source location, no passes lack endpoints, and no
completed passes lack recipient IDs. Supported source versions observed are 1.0.3
(80 matches) and 1.1.0 (377 matches). No additional quality-flag categories were observed.

## Regression coverage

Synthetic tests cover atomic rejection, duplicate identifiers and indices, event order,
period boundaries, pressure missingness, shot reconciliation, evidence resolution,
public raw-event restrictions, lineup changes and dismissals, before-event score state,
control-episode boundaries, immutable outcome-blind splits, source-hash resume and retries,
Parquet exports, and preservation of existing databases during migration.

Future-event mutation leaves prefix-replayed active players unchanged. Final stint end
fields are descriptive only and must not enter predictive features. A concurrency test
checks SQLite readers during an open write transaction; WAL resolved the lock contention
encountered during the first browser checks.

Browser checks exercise the four-season archive, the real audit, training-only labels,
shot counts and citations, period/team filters, keyboard interaction and mobile overflow.
Screenshots are private local outputs under `output/`.

## Limits

Groq activation checkpoint (25 September 2026): 116 Python tests and four analyst browser
journeys pass with the backend key configured. Unit fixtures explicitly override the key
alias so they never inherit real credentials. A separate live browser smoke test returned
`groq_selection` in 2.61 seconds, with one request and zero repairs. The 60-case provider
regression, request pacing, tokens and latency are documented in `groq-setup.md`.
No credential string was found in the exported experiment JSON, frontend JavaScript or
OpenAPI schema. Frozen xG, xT and graph code hashes remain unchanged.

M6 engineering checkpoint (24 September 2026): 105 Python tests and 22 real-data browser
checks passed, including desktop and mobile analyst/evidence/evaluation journeys. Type
generation, production frontend build, Ruff and Prettier checks passed. Frozen xG, xT,
graph and retrieval experiment code hashes remain unchanged.

The subsequent fixed-network removal increment passes 108 Python tests, including
hand-calculated directed connectivity, bridge removal, isolates, empty remainders and
public API validation. All 24 browser journeys passed across desktop and mobile after
allowing 60 seconds for the analyst journey's first local encoder load (23 passed in
the full run, the one cold-start timeout passed on its targeted rerun). Its visual
review covers desktop and mobile. The M6 production
image also passed PostgreSQL result parity, explicit BM25 fallback without ML packages,
and public raw-event/live-generation restrictions. No cloud deployment was performed.
The final image including network removal built successfully and repeated the PostgreSQL
checks. The analyst journeys also passed from a freshly restarted server (4/4 cases).

A warm single-client local API benchmark used 3 warmups and 20 requests per route on
Windows 10, Intel64 Family 6 Model 142 Stepping 12, Python 3.12.10. Observed p95 was
12.3 ms for research summaries, 24.3 ms for hybrid methodology search and 812.0 ms for
deterministic period comparison. Docker build and a model download ran concurrently.
This does not measure cold encoder loading, concurrent users, LLM generation or cached
public reports. Local raw timings and hardware details are in `output/m6-verification.json`.

- Full-corpus validation ran on SQLite. PostgreSQL migration and repeated real-match
  ingestion ran on match 19717, not all 457 matches.
- At the M2 checkpoint, no predictive model had been evaluated. M3–M5 results above
  supersede that status. M6 retrieval and deterministic analyst evaluations are documented
  in `analyst-workflow.md`; local LLM performance remains unevaluated. No causal inference
  is supported.
- Probability and deterministic/retrieval results are measured; the local LLM evaluation,
  independent human semantic review and public-release performance gates remain open.
- Lineup and episode reconstruction follows explicit source-event rules; it is not tracking.
- Pytest reports two upstream TestClient/AnyIO deprecation warnings.
- No cloud resources were provisioned and no public release was performed.

Reproduction commands and publication boundaries are in the root README.

## M7 — style discovery verification (25 September 2026)

Real-corpus development produced 2,326 training and 3,153 projected windows.
Five alternate initializations and twenty match-bootstrap refits were measured;
the full results are in `experiments/styles-v1/results.json`. Two identical runs
reproduced the reported metrics. Synthetic checks cover half-open boundaries,
incomplete windows, invalid geometry, future-partition invariance, unavailable
results and source invalidation. The Python suite passes 120 tests. Ruff checks,
generated OpenAPI types and the production frontend build pass.

Six desktop/mobile browser journeys pass for style evidence pagination and keyboard
activation, existing fixed-network removal/restore, and experiment navigation.
Rendered desktop and mobile profile screenshots were visually inspected; no
horizontal overflow was observed. The aggregate report and model card disclose
modest separation and descriptive, non-causal interpretation. No new Docker or
PostgreSQL verification is claimed for M7; no schema change was needed.

## M8 — local release candidate

The user chose preparation only, with no cloud deployment. The synthetic Python
suite passes 125 tests, including review gates, exact-content approval binding,
source invalidation, blocked public raw/live endpoints and refusal to overwrite
a nonempty transfer destination. OpenAPI generation and production builds pass.

All 36 reports were independently recomputed from the SQLite research database and
the selected PostgreSQL staging database. Seventy-two core measurements also match
the pinned raw-event oracle; all 192 distinct evidence references resolve.
The isolated PostgreSQL copy contains 12 matches, 40,587 events and 317 shot
predictions. The private seed is about 30 MB, versus about 1.15 GB for the research
database. No raw data or seed is included in the application image or repository.

A custom-format PostgreSQL backup was restored into a separate new database. The
restored database reproduces all 36 reports and resolves the same 192 references.
The live database and research data were not overwritten. Per-endpoint local timings,
selection and report fingerprints are recorded in `experiments/showcase-v1/results.json`.
The timings are warm single-client TestClient measurements, not cloud performance.

Independent semantic/publication review is still pending. Public cached reports
remain hidden and readiness returns 503 intentionally. No deployment or successful
production launch is claimed. See `docs/public-release.md` for the review packet,
deployment procedure and backup/rollback instructions.

The final image is 164,269,334 bytes; the PostgreSQL staging database is 45,063,191
bytes. Image inspection confirms no `.env`, raw data, private seed, review packet,
model artifacts, Groq credential, PyTorch or scikit-learn runtime. Two local-preview
and eight public-mode desktop/mobile browser journeys pass. Mobile report selection,
keyboard evidence navigation, contrast and pending-review presentation were checked.
The Render YAML was checked against the published reference; account-side Blueprint
validation remains a deployment step and was not performed without a Render account.
# Premier League extension verification (26 September 2026)

- Full 380-match import and audit completed; all nine corpus integrity checks pass.
- 1,313,773 events, 9,908 shots, 20 teams and 644 players are available.
- Separate xG, xT, third-pass experiment and passing-style models are published.
- 129 backend tests pass; Ruff checks and formatting pass.
- Eight Premier League browser checks pass across desktop and mobile, covering
  league isolation, xG/xT provenance, graph results, styles, source evidence and
  deterministic analyst requests. Existing WSL dashboard and startup/guide
  regression checks also passed during integration.
- Production frontend build succeeds. Original WSL/research report hashes are unchanged.
- The first full import rejected two negative source durations; the tested adapter
  now retains those events, records their original values as quality warnings,
  and stores unavailable normalized durations. Both matches imported on resume.
- Final browser checks were rerun successfully after restarting the local server.
