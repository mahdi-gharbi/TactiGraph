# Approved milestone sequence

## M1 — implemented first vertical slice

Pinned ingestion for match 19717; normalized match/event/pass/shot tables; local lineup
source; analytical API; React pitch, shot timeline, and exact evidence. Dependency locks,
synthetic tests, Docker configuration, and CI support this slice.

## M2 — implemented dataset foundation

Resumable import for all 457 listed WSL matches, coverage and exclusion reports, Alembic,
team/player dimensions, lineup stints, possession/control episodes, schema-aware pressure,
training-only EDA and immutable split manifests. Match dates remain intact.

Training: 2018/19 + 2019/20. Tuning: first approximately two-thirds of 2020/21.
Calibration: remainder of 2020/21. Test: 2023/24. Exact counts are 194/89/42/132;
IDs are frozen in `configs/splits/wsl-v1.json` before experimentation.

## M3 — implemented xG experiment

Logistic regression and LightGBM, non-penalty shot outcome target; separate smoothed penalty
rate. No shot endpoint, outcome, provider xG, identity, or future context as features.
Development-only model selection; held-out calibration; locked future-season evaluation.
Publish log loss, Brier, ROC/PR-AUC, reliability, match-bootstrap intervals, and limitations.

Completed in xg-v1: logistic retained by the prespecified tuning rule; 3,506 final-test
non-penalty shots; log loss .314618, Brier .090669. Sigmoid rejected on development data.
Five team-disjoint stress folds, coefficients, permutation importance and model provenance
are available. The original final test is now inspected; later versions must disclose this.

## M4 — implemented xT and networks

Turnover-aware 12×8 spatial Markov model; compare 8×6 in development. Separate shot and loss
terminal states, prevent duplicate loss counting, test convergence. Add directed completed-pass
networks, rate denominators, period comparison, xG/xT momentum, and candidate-shift summaries.

Completed in xt-v1: 12×8 selected on tuning Brier; refitted on 82,214 training+tuning
episodes; converged in 67 iterations. Final test: 35,899 episodes, Brier .010676,
log loss .054245. Two baselines and 1,000 paired match-bootstrap draws are published.
Match Lab now includes seven comparison metrics, passing networks, separate trailing
curves, source-backed evidence and candidate shifts. No schema migration was required.

## M5 — implemented graph experiment

Predict a subsequent shot after the third completed pass of an eligible open-play episode.
Only pre-cutoff information; active-player nodes; past-five-minute directed pass edges.
Two GINE layers, hidden width 32, dropout .2; compare prevalence, logistic and LightGBM
baselines, three seeds, topology/history/edge-attribute ablations. Test suffix invariance
and team-disjoint generalization. Publish a negative result if the GNN is not justified.

Completed in graph-v1: 8,252 training, 3,893 tuning, 1,725 calibration and 6,607 test
samples. Three seeds for GINE and all four ablations; five team-disjoint stress groups.
GINE mean test log loss .260677 versus LightGBM .249144; the graph contribution gates
did not pass. LightGBM serves stored third-pass forecasts. Source cutoffs and model
artifacts are inspectable from Match Lab; the full comparison is in Experiments.

## M6 — functional delivery accepted, validation reservations retained

Implemented: local deterministic state machine, three guided comparisons, controlled claim
verification, evidence navigation, a digest-gated local Qwen adapter and bounded methodology
search are implemented. The 60 tactical cases pass deterministic machine checks. The
60-query retrieval experiment selected hybrid (held-out Recall@5 .9667, MRR@5 .7744;
MRR target .80 not met). Experiments displays the actual results and pending review status.
Independent semantic review remains pending. The user accepted progression to M7;
local Qwen evaluation is optional following the choice of Groq. See `docs/analyst-workflow.md`.

On 25 September the user approved Groq as the preferred interactive LLM provider for this
PC, with Ollama optional and deterministic fallback retained. The GPT-OSS 20B adapter
is implemented and evaluated with real requests: 40/40 selections succeeded, 20 mandatory
abstentions were enforced, and all 60 machine checks passed. No repairs or fallbacks occurred.
Held-out-match generation p95 was 12.76 s. This reuses the authored regression cases and
does not replace independent semantic review. See `docs/groq-setup.md`.

Explicit state machine; Pydantic tool contracts; six-call budget, one repair attempt;
Groq preferred with optional pinned Qwen3 4B/Ollama. Deterministic numerical claims and evidence verification.
BM25 versus local MiniLM/hybrid methodology retrieval. No semantic search for numerical facts.
Create the two 60-case golden sets before tuning; measure correctness, abstention, citations,
retrieval, tool success, latency and costs. Public demo uses clearly labeled cached reports.

## M7 — research and polish

Fixed-network player removal
is implemented in the API and Match Lab, with directed reachability, component sizes,
remaining pass weight, source evidence and a restore control. Hand-calculated tests cover
bridge removal, isolates and an empty remainder.

Style discovery is implemented: training-only standardized PCA/K-means on 2,326
15-minute team windows, four measured profiles, 3,153 later-season projections,
five-seed and 20 match-bootstrap stability checks. Training silhouette .2675,
seed ARI .9807–.9988, bootstrap ARI .8382–.9585. Match Lab links assignments to
paginated source passes; Experiments shows profile means and stability. The model
card documents modest separation, inclusion rules and interpretation limits.

15-minute period PCA/K-means with stability tests and measured cluster labels. Remove-a-player
graph sensitivity with no causal claims. Complete linked UI, accessibility, reports and model cards.

## M8 — public release

Release candidate prepared locally at the user's request; deployment is deferred.
Twelve coverage-selected matches and 36 deterministic reports are frozen with
content fingerprints. The review packet remains unapproved; public serving hides
pending reports and readiness requires 36 reviewed, current reports. The package
includes a Render Blueprint, isolated Docker/PostgreSQL staging, a transactional
copy into an empty private database, and a backup/rollback runbook. The cloud
deployment, independent review and actual hosting costs remain outstanding.

One Docker web service on Render and private PostgreSQL. Precompute 36 verified reports for
12 matches selected by coverage. Record real metrics and deployment costs; review publication
rights, attribution/logo, raw-data exclusions, backups and rollback. No paid APIs. No cloud
deployment is performed in the first coding session.
