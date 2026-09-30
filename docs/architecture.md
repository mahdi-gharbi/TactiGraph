# M4 architecture and contracts

## Execution path

Pinned StatsBomb JSON → complete payload validation → one SQL transaction → normalized
tables → optional Parquet export → SQL analytical queries → typed API → React.

The local default is SQLite to make the first slice usable without a database service.
Docker Compose runs the same schema and queries against PostgreSQL. Alembic upgrades from
frozen schema snapshots. Existing M1 databases are adopted only after their schema matches;
unknown unversioned databases are rejected. Back up before upgrading.

## Data

`source_manifest`: source path, commit, SHA-256, retrieval time, data version, validation status.
`matches`: competition, season, teams, date, final score, source schema, event count.
`events`: UUID, match, source index, period, period milliseconds, displayed minute/second,
type, team, player, possession, location, pressure availability.
`passes`: recipient, completion/outcome, endpoint, length, height, technique, body part.
`shots`: outcome, goal, body part, shot type, technique, preceding key-pass reference.
`lineup_sources`: validated team-level JSON, retained privately for traceability.
M2 adds dimensions, match-player membership, event context, stints, possessions, episodes,
ingestion status, quality reports, split assignments and a cached dataset audit.
See [data foundation](data-foundation.md) for semantics and reproducibility.

Final match scores and shot outcomes are analytical display data, not approved predictive
features. The offline xG pipeline uses a strict feature allowlist; labels and identity metadata stay outside its design matrix. `events.under_pressure=null`
preserves omission; `event_context` separately stores the schema-adapted value and status.

Validation currently covers nonempty events, UUIDs, duplicate IDs/indices, periods,
finite coordinates, known teams, lineup team coverage, timestamps, and shot outcomes.
Outside-pitch coordinates are flagged and retained, then omitted from spatial analysis.
Unknown optional source fields remain in the cached raw file; they are not silently
promoted to model features. File hashes establish local integrity, not independent source authenticity.

## API v1

| Method/path | Contract |
| --- | --- |
| GET `/health` | Process status, application version, local/public mode |
| GET `/dataset` | Coverage audit, immutable split provenance, training-only aggregate EDA |
| GET `/matches` | Ingested match cards with provenance |
| GET `/matches/{id}/summary` | Team shot/pass counts, available periods, null xG |
| GET `/matches/{id}/shots` | Analytical shot origins and shot-count result ID |
| GET `/evidence/{result_id}` | Recompute the exact query; supporting event references |
| GET `/matches/{id}/events` | Local-only paginated normalized events; maximum 250 rows |

All paths above have `/api/v1` prefix. Shot filters: `team_id`, `player_id`, `period`,
`start_ms`, and `end_ms`. Time bounds are period-local; an explicit period is mandatory
when bounds are supplied. Starts are inclusive; ends exclusive. No end means period end,
including stoppage time. Shootouts are excluded from analytical shot and pass counts.

Evidence IDs encode a typed, bounded shot-count query. They are not authorization tokens
or storage keys for generated text. The server parses and validates every component,
then reruns the allowlisted query. No free SQL or model-generated calculation is executed.
The pinned source and metric version make these IDs reproducible for this M1 dataset.

OpenAPI is exported by `tactigraph openapi`; `npm run types` generates the frontend types.
CI rejects drift between the exported schema and committed generated types.

## Failure behavior

Unknown match: 404. Unknown team/player, invalid windows, shootout period: 422.
Malformed or invalid reimport: validation error; previous database preserved.
Corrupt cached file: fail explicitly; remove that cached JSON/checksum pair and rerun ingestion.
Unavailable API: visible error and retry. No ingested data: explicit setup instructions.
No matching shots: zero count with an empty, inspectable supporting set.
Missing locations: retained in counts and timeline, omitted from the pitch.

Only `frontend/dist/assets` is mounted as a static directory. There is no upload or raw
download endpoint. The database URL is configured by environment, never returned by the API.

## Offline models and serving

Alembic revision 0003 adds model releases, prediction samples and stored probabilities.
`xg develop` locks preprocessing, model parameters and artifacts; `xg evaluate` records the
one-time final-test comparison; `xg publish` checks source hashes and writes predictions.
Models and MLflow runs remain local private artifacts. Only approved aggregate experiment
results are exported for publication. API serving imports no scikit-learn, LightGBM or MLflow.

`GET /api/v1/experiments` returns the typed evaluation and model provenance. Match summaries
include xG, non-penalty/penalty contributions, coverage and split; shot layers carry sample,
artifact hash and run citations. Untrained data stays null, incomplete coverage is partial,
and reimport invalidates affected releases instead of serving stale probabilities.

## Tactical analytics and xT

`analytics/windows.py` computes period-local measurements, lineup exposure and directed
passing networks. `analytics/trends.py` computes separate trailing xG/xT sums and
adjacent-window candidate shifts. The React clients draw server-returned values.
Tactical evidence endpoints are allowlisted, validated and paginated; no raw-event
objects are exposed in public mode.

`xt develop/evaluate/publish` uses a separate frozen experiment, with aggregate spatial
values and a paired match-bootstrap evaluation. Publication uses the existing
`dataset_reports` table (`id=xt`), so no schema migration is required. Any reingestion
invalidates this report; republishing validates source/code/artifact hashes first.
The API reads that aggregate surface through `xt_serving.py`, with no NumPy, sklearn
or training process in production. OpenAPI exposes typed xT evaluation, comparison,
network, trend and analytical-evidence responses.

## Third-pass graph experiment

`graph_features.py` filters the source prefix before lineup replay or feature construction.
Development datasets, model selection, calibration and the one-time final test are separate
offline steps. `graph develop/evaluate/publish` materializes the selected model's predictions;
the API imports neither PyTorch/PyG nor LightGBM. GINE remains an evaluated negative experiment
in graph-v1; the selected LightGBM baseline supplies the displayed predictions.

The existing `dataset_reports` table stores the aggregate report (`graph`) and per-match
prediction bundles (`graph-predictions-{match_id}`). Publication is transactional and any
reingestion invalidates these bundles. `/api/v1/experiments/graph` returns typed aggregate
evaluation; `/api/v1/matches/{match_id}/third-pass` validates team/period and limits pages to
100 predictions, with source commit, cutoff, split, artifact and run provenance. No raw
event stream or training operation is exposed. No schema migration was needed.
