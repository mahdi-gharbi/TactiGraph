# M8 release candidate — local preparation

The user requested a deployable package only: no GitHub repository, Render resource,
cloud upload or paid service has been created. This is a release candidate, not a
public launch. Independent report and publication review remain pending.

## Contents and publication boundary

`render.yaml` describes one Docker web service and PostgreSQL 16 in Frankfurt.
The database starts with an empty external IP allowlist. Automatic deployment is off.
There is no Groq key, Ollama, paid inference or model training in this deployment.
The web image contains code, configuration and the built frontend only. Source
JSON, databases, model artifacts, credentials and the review packet are excluded.
Normalized analytical data is loaded into the private database separately.

The showcase selects three matches from each of four WSL seasons. Eligibility
requires starting lineups, no recorded quality issues, shot locations, completed
pass recipients and complete numerical/model reports. Eligible matches rank by
pass-endpoint coverage, then stable match ID, without sorting on scores or model
outcomes. Three deterministic home-team reports compare second-half minutes
0–15 against 15–30: progression, chance creation and network concentration.
The selection is suitable for a curated demo, not an unbiased performance sample.

## Review the concrete reports

The local `output/release-review/index.html` contains all 36 reports, numerical
claims, pinned source links, denominators and fingerprints. `reports.json` is the
canonical stored content. `approvals.json` is a template, initially unapproved.

An independent human reviewer checks each interpretation and its supporting source,
fills their name, ISO review date, per-report approval and notes, and checks the
publication fields. Approvals are tied to each exact SHA-256; missing, changed or
stale reports are rejected. Record a completed review with:

```powershell
.\.venv\Scripts\tactigraph.exe showcase approve --review output/release-review/approvals.json
```

Do not mark review complete merely because the automated checks pass. Re-exporting
with `tactigraph showcase export` preserves an existing approvals file.
The local workspace can preview pending reports. Public `/api/v1/showcase` hides
all pending reports, and `/api/v1/ready` returns 503 until 36 current reports have
recorded review. The raw-event endpoint and live analyst generation stay disabled.

## Publication review sources

Data attribution and the StatsBomb logo are present in the application. The MIT
license covers project code, not upstream data. Review the current
[StatsBomb open-data terms and attribution instructions](https://github.com/hudl/open-data#terms--conditions)
and the [data agreement](https://github.com/hudl/open-data/blob/master/LICENSE.pdf)
for the intended public use. Registration/permission and the publication terms are
not declared complete by this release preparation. Do not publish the private seed
database, raw data, model checkpoints or local review files as repository assets.

## Local production rehearsal

```powershell
docker compose -p tactigraph-m8 -f compose.release.yaml up -d --build
```

This creates a separate PostgreSQL volume and serves public mode only on
`http://127.0.0.1:8002`. It does not replace the research database or its Docker
project. The staging password in this file is for isolated localhost use only;
the Render database generates its own credentials.

`tactigraph transfer-showcase --source <source-SQLAlchemy-URL>` copies the twelve
selected matches, required analytical rows, provenance and aggregate model reports
into the database specified by `TACTIGRAPH_DATABASE_URL`. It requires an empty
destination, inserts in foreign-key order, and rolls back on error. It never
deletes or overwrites an existing target. Prediction and evidence rows are retained;
unselected matches and their event streams are excluded. Training summaries still
describe the original research corpus and must not be interpreted as hosted row counts.

Private local staging seed: `output/m8-showcase.db`. Never commit it. For another
seed, configure a new, empty SQLite destination, then run the transfer command
against the research database. SQLite input is read in a consistent transaction.

## Future deployment steps

1. Complete independent review locally and record it against the frozen reports.
2. Review a Git repository containing code/configuration only. Confirm `.env`,
   `data/`, `artifacts/` and `output/` are absent from tracked files and history.
3. Confirm the prices and available plans in the Render dashboard. The blueprint
   explicitly selects `1c-2g` web and `0.5c-1g` PostgreSQL with 5 GB storage; these
   are paid resources. No spending has been authorized or incurred here.
4. Create the Blueprint from the reviewed repository. Provision the private DB,
   import the reviewed staging database, then complete the web deployment. A new
   empty database intentionally fails the readiness health check.
5. For import from a trusted workstation, temporarily allow only that workstation's
   public IP in the database access rules, use the TLS external URL and PostgreSQL
   tools, then restore the empty allowlist. Keep credentials out of commands saved
   in shell history and out of this repository. Alternatively use an authorized
   importer on Render's private network.
6. Confirm `/api/v1/ready` returns 200 with 36 reports, inspect the 12 matches,
   test citations and mobile navigation, and recheck raw/live endpoints return 404.

The URL adapter accepts Render's `postgres://`/`postgresql://` connection strings
and explicitly selects the installed psycopg driver. Hosting configuration follows
the [Render Blueprint reference](https://render.com/docs/blueprint-spec).

## Backups and rollback

Before importing or changing a deployed database, create a PostgreSQL custom-format
backup (`pg_dump -Fc`) to private encrypted storage. Restrict retention/access and
test `pg_restore --exit-on-error --no-owner` into a NEW empty database. Never use
`--clean` against the active database. A valid backup must reproduce report hashes,
counts and analytical results, not merely finish without a tool error.

Retain the previous image digest/commit and a matching database backup. For rollback,
restore to a new private database, verify it, then switch the service's connection
and image together. Keep the original database until rollback is verified. No
destructive downgrade or automated volume deletion is included in these scripts.

## Costs and measurements

Cloud spend during preparation: none; cloud infrastructure was not provisioned.
Generation requests for the 36 reports: zero; they are deterministic.
Hosting prices are not a measured deployment cost and must be confirmed before
launch on [Render pricing](https://render.com/pricing). Runtime, storage, bandwidth,
backups and taxes can contribute to the eventual bill.

Local verification results live in `output/m8-*-verification.json`. Benchmarks use
a warm single-client FastAPI TestClient, three warmups and twenty measured calls;
they do not measure internet latency, concurrency or Render cold starts.
