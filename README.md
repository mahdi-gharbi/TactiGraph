# TactiGraph AI

<img src="frontend/src/assets/statsbomb-logo.png" alt="StatsBomb — data provider" width="130" />

**Football intelligence you can trace back to the evidence.**

A Data Science and Applied AI portfolio project built on official StatsBomb open data.
This repository implements **M1–M7 functionality and an M8 release candidate**, not the complete
eight-milestone MVP. The Match Lab connects four pinned WSL seasons to analytical views and
exact event citations. No xG, xT, GNN, LLM, or retrieval metrics are fabricated.

## Available now

The local workspace also supports **men's Premier League 2015/16 (380 matches)**
through the top-bar league selector. It has a separate database, chronological
split and model versions. See [setup, usage and experiment limits](docs/premier-league.md).
The original research measurements below refer to WSL.

- Pinned, resumable ingestion of all **457 listed WSL matches** across four seasons.
- SHA-256 source manifests, local cache integrity checks, and atomic database replacement.
- Normalized events, passes, shots, teams, players, lineup stints, possessions and control episodes.
- Alembic migrations, per-match quality reports, typed Parquet exports and corpus integrity audit.
- Immutable chronological split: **194 train / 89 tuning / 42 calibration / 132 test**.
- Training-only EDA dashboard: event distributions, shot zones, temporal patterns and team/player profiles.
- SQLite quick start and PostgreSQL Docker setup using the same SQLAlchemy models.
- FastAPI shot counts, summaries, pitch layers, and deterministic evidence resolution.
- React Match Lab with shot map, period/player/time filters, shot timeline, and evidence drawer.
- Logistic and LightGBM xG experiments with a locked future-season test and match-bootstrap intervals.
- **Logistic regression selected:** test log loss **0.3146**, Brier **0.0907** on **3,506 non-penalty shots**.
- Separate penalty estimates, 11,815 stored predictions, model provenance and calibration charts.
- Turnover-aware xT: a locked 12×8 grid, 35,899 test episodes and match-bootstrap comparisons.
- Period comparisons, final-third-entry rates, field tilt and directed passing networks.
- Separate five-minute xG/signed-xT curves, candidate shifts and paginated analytical evidence.
- Third-pass shot prediction: **6,607 test episodes**, three GINE seeds, four ablations and five team-disjoint stress groups.
- **LightGBM retained:** log loss **0.2491**, Brier **0.0670**, PR-AUC **0.3510**; the GNN contribution was not established.
- Stored third-pass predictions with cutoff/source/model citations and explicit in-sample labels.
- Local evidence analyst with verified numerical templates, three guided intents and an evidence drawer.
- Three-case WSL field guide in Evidence Analyst: question, saved measurement, source events and interpretation limit. The cases are illustrative, not a representative sample.
- **60/60 deterministic tactical cases pass machine checks**; independent semantic review remains pending.
- A frozen, 12-report stratified worksheet and scoring protocol for independent human evaluation. [Review protocol](docs/human-evaluation.md).
- Evaluated methodology retrieval: hybrid held-out Recall@5 **96.7%**, MRR@5 **77.4%**, below the MRR target.
- Optional digest-gated Qwen3 claim selection with one repair and deterministic fallback; real LLM evaluation pending.
- Groq GPT-OSS 20B selection: 40/40 real selections and 20 mandatory abstentions pass the authored regression checks; independent review pending. [Setup and evaluation limits](docs/groq-setup.md).
- Remove a player from an observed passing network: remaining pass weight, connectivity and components, with explicit counterfactual limits.
- Four descriptive passing profiles from 15-minute windows, training-only PCA/K-means,
  match-bootstrap stability and linked source passes. [Style model card](docs/styles-model-card.md).
- Responsive layout, keyboard-accessible shot markers, and explicit unavailable model states.
- Synthetic backend tests, real-data Playwright journeys, generated OpenAPI types, and CI.

## Quick start — Windows / PowerShell

For the already installed local workspace, double-click `Start-TactiGraph.cmd`.
It starts the background server on port 8003 and opens the app. Run it again after
a PC restart; a browser tab alone does not keep the backend running. Startup logs
are under `output/local-server.*.log`. The detailed printable project report and
user guide is at **http://127.0.0.1:8003/guide** and linked in the application sidebar.
Its standalone source is `frontend/public/guide.html`.

Requirements: Python 3.12 and Node.js 22. No paid APIs or accounts are needed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv==0.6.14
.\.venv\Scripts\uv.exe sync --frozen --extra dev --extra modeling
npm.cmd --prefix frontend ci
.\.venv\Scripts\tactigraph.exe ingest
npm.cmd --prefix frontend run build
.\.venv\Scripts\tactigraph.exe serve
```

Open **http://127.0.0.1:8000**. API documentation: **http://127.0.0.1:8000/docs**.

After full ingestion, reproduce xT with `tactigraph xt develop`, `tactigraph xt evaluate`,
then `tactigraph xt publish`. See [the xT model card](docs/xt-model-card.md) and
[tactical metric definitions](docs/tactical-analytics.md). Training never runs in API requests.
The first ingestion needs internet access; later runs reuse checksum-verified cached files.

The quick start imports only match 19717 (Arsenal WFC–Liverpool WFC). Populate the full
foundation and Overview dashboard with:

```powershell
.\.venv\Scripts\tactigraph.exe fetch --workers 4
.\.venv\Scripts\tactigraph.exe ingest --scope wsl
.\.venv\Scripts\tactigraph.exe audit
```

Allow disk space and time for 457 event files, the database and Parquet exports. Repeating
the corpus import checks source hashes and skips completed partitions. Failed matches
remain explicit in `data/quarantine/`; reruns retry them. `audit` exits unsuccessfully
if coverage or integrity checks fail. Do not run multiple ingest writers concurrently.
The full-data browser tests require the complete import, audit and both xG and xT publication.

## Reproduce the graph experiment

Install the optional CPU training stack with `uv sync --frozen --extra dev --extra modeling --extra graph`.
Then run `tactigraph graph develop`, `tactigraph graph evaluate`, and `tactigraph graph publish`.
Development is resumable under unchanged source, feature and protocol hashes. Final-test access
is recorded once after locking all models. Raw samples and checkpoints remain private.

The full GINE's mean test log loss is **0.2607** across three seeds, compared with **0.2491**
for LightGBM. The paired 95% match-bootstrap difference is **+0.0081 to +0.0151**, favoring
LightGBM. Removing message passing also improved the neural model; this version does not
establish a graph-learning contribution. The application serves the prespecified tabular
fallback and exposes the complete negative experiment. See [the graph model card](docs/graph-model-card.md).
The project-wide 2023/24 holdout was previously inspected for xG/xT, which is disclosed.

## Reproduce the xG experiment

After the full corpus import and audit:

```powershell
.\.venv\Scripts\tactigraph.exe xg develop
.\.venv\Scripts\tactigraph.exe xg evaluate
.\.venv\Scripts\tactigraph.exe xg publish
.\.venv\Scripts\tactigraph.exe xt develop
.\.venv\Scripts\tactigraph.exe xt evaluate
.\.venv\Scripts\tactigraph.exe xt publish
```

Development fits on training, selects on tuning and locks the artifacts before evaluation
opens the final-test events. Evaluation reruns return the recorded result. Publish writes
stored probabilities to the configured application database; web requests do not load models
or start training. Visit **Experiments** for results, calibration, slices and the model card.
The Match Lab shows model xG, separate penalty contributions and citations to the fitted artifact.

The original final test has now been inspected. Any future improvement needs a new experiment
version and an explicit prior-inspection disclosure; it cannot claim a fresh untouched test.
Do not delete a test-access marker to repeat model selection. To reproduce in a clean workspace,
use the locked dependencies, pinned source, split manifest and `configs/xg-v1.json`.

Artifacts, feature datasets and local MLflow runs live under ignored `artifacts/`. Permitted
aggregate results are exported to `experiments/xg-v1/results.json`. The modeling extra includes
MLflow's lightweight local tracking client; the public app requires no MLflow server or inference API.
Only load joblib artifacts generated locally by this project. No upstream data or model artifacts
are included in the public Docker image. Offline fitting/publishing runs in an environment with
the modeling extra; the production image only reads precomputed PostgreSQL records.

See the [xG model card](docs/xg-model-card.md) and [experiment protocol](configs/xg-v1.json).

On macOS/Linux, install uv, then use `uv sync --frozen --extra dev --extra modeling`,
`uv run tactigraph ingest`, `npm --prefix frontend ci`,
`npm --prefix frontend run build`, and `uv run tactigraph serve`.

For frontend development, run the API and `npm.cmd --prefix frontend run dev` in separate
terminals. Vite proxies `/api` to port 8000. Open its printed local URL.

## Docker + PostgreSQL

```sh
docker compose up --build -d
docker compose exec app tactigraph ingest
```

Open http://127.0.0.1:8000. The database is not exposed on the host; app ports bind only
to loopback. The default password is for local development. Set `POSTGRES_PASSWORD`
before using another environment. Raw data lives in a private named volume, never the image.
For the full corpus, run `tactigraph fetch`, `tactigraph ingest --scope wsl`, then
`tactigraph audit` through `docker compose exec app`. Back up an existing database before
upgrading; startup applies Alembic migrations automatically. Unknown unversioned schemas
are refused. Destructive downgrades are intentionally unavailable: restore a backup.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
.\.venv\Scripts\tactigraph.exe openapi
npm.cmd --prefix frontend run types
npm.cmd --prefix frontend run build
```

For browser checks, keep the ingested application running on port 8000, then:

```powershell
cd frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Browser tests compare rendered counts to actual API responses, open exact citations,
exercise filters and zero results, check keyboard interaction, and detect mobile overflow.
They do not encode an invented match score or model result.

## Reproducibility and evidence

Source commit: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`.

Ingestion downloads the selected season indexes, event files, and lineup files from
the official repository at that commit. The full payload is validated before a transaction
replaces the match. Repeating ingestion does not duplicate records. Validation failures
write a quarantine diagnostic and preserve the existing database.

Source JSON, cache checksums, SQLite, and Parquet are under the ignored `data/` directory.
The ingestion manifest records source path, commit, hash, original cache retrieval time,
and source data version. Parquet is a reproducible export, not the API source of truth.

Each shot-count result includes its query bounds, metric version, source checksum, ordered
event UUIDs, period timestamps, and pinned upstream URL. Missing shot locations affect map
coverage but never remove a shot from the count. Finite coordinates outside the nominal
pitch are retained and flagged, without clipping; they are excluded from spatial views.
Shootouts are excluded. A zero-result
query is evidence of zero matching shots, not missing model output.

See [architecture and API contracts](docs/architecture.md),
[dataset contracts and split policy](docs/data-foundation.md),
[methodology](docs/methodology.md), [verification results](docs/verification.md),
and [remaining milestones](docs/roadmap.md).

## Publication boundary

The M8 package includes 36 cached reports for twelve quality-selected matches, a
private PostgreSQL seed/transfer workflow, a Render Blueprint and review gates.
It is prepared locally only. Pending reports are hidden in public mode and the
readiness endpoint remains 503 until independent review is recorded. See the
[release and backup runbook](docs/public-release.md). No cloud service was created.

`TACTIGRAPH_MODE=public` disables the full event endpoint. Analytical shot views and their
bounded evidence remain available. Static serving exposes only the built frontend, not
the raw-data directory. The default local mode is intended for research on your own machine.

This is **not yet a public release**. Deployment, remaining model experiments, human-reviewed
analyst reports, and the final publication review belong to later milestones. No cloud
resources are provisioned by setup. Infrastructure may cost money even with zero paid APIs.

## Attribution and data terms

Data provided by **StatsBomb**: [official open-data repository](https://github.com/hudl/open-data).
Read the [StatsBomb user agreement](https://github.com/hudl/open-data/blob/master/LICENSE.pdf)
and [attribution instructions](https://github.com/hudl/open-data#terms--conditions).
The agreement restricts redistribution and commercial exploitation; published analysis
requires attribution and StatsBomb branding. Register your interest with StatsBomb as requested
by the agreement. No raw dataset, data dump, or real-data test fixture is committed here.

The MIT license applies to original project code only, not StatsBomb data or branding.
