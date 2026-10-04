# Verification and deployment preparation

## Reproducible integration and load checks

The dedicated CI integration job uses PostgreSQL 16, migrations, an invented
88-event match, stored synthetic predictions and actual evidence resolution.
The fixture refuses a database containing matches: use an isolated empty database.
The same job dumps the invented database and restores it into a separate new database,
compares every table's row counts and content hashes, then checks migrations,
stored predictions, a verified report, source evidence and the closed readiness gate.
No StatsBomb files or API key are required. The main CI job builds the production
image and checks public endpoint boundaries and exclusion of training libraries.

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\python.exe infra/serve_synthetic.py --port 8011
```

In a second terminal:

```powershell
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:8011'
$env:TACTIGRAPH_SYNTHETIC_E2E='1'
npm.cmd --prefix frontend run test:e2e -- synthetic.spec.ts
.\.venv\Scripts\python.exe infra/benchmark_http.py --users 1 5 10 --requests-per-user 40
```

The browser suite covers desktop and mobile, guided/free questions, opening evidence,
clarification, provider/API error display and invalidation after context changes.
The load workload uses actual HTTP sockets, four warmup routes, a single uvicorn
process and 1/5/10 concurrent clients without think time. It reports sample counts,
latency percentiles and error rates. It covers summary, shots, guided calculations
and evidence. It excludes real-provider latency and production capacity claims.
See `experiments/operations-v2/synthetic-http.json` for the measured environment.

## Hosting estimate

Estimate checked on 4 October 2026 for the existing Frankfurt blueprint:

| Resource | Configuration | Base monthly USD |
| --- | --- | ---: |
| Web | `1c-2g`, 1 CPU / 2 GB | 25.00 |
| PostgreSQL | `0.5c-1g`, 0.5 CPU / 1 GB | 19.00 |
| PostgreSQL storage | 5 GB × $0.30 | 1.50 |
| Compute + storage estimate | One instance of each | **45.50** |

These are published list prices, checked against [Render pricing](https://render.com/pricing),
the [compute-plan mapping](https://render.com/docs/compute-plans), and Render's
[hosting cost explanation](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses).
The total is an estimate, calculated by addition. Workspace subscription, metered
bandwidth/build minutes, taxes, external backup storage and inference are excluded.
Recheck the quote before purchase. No hosting resource has been provisioned.

The public blueprint serves reviewed cached reports and requires no Groq key.
Its readiness check intentionally fails with empty or unapproved data. Paid
deployment and interactive public access remain separate decisions.

## Availability and restoration rehearsal

1. Build the exact repository revision into an image; retain its digest. Run
   `infra/smoke_http.py --base-url http://127.0.0.1:8012 --public` against an isolated
   public container. Health must return 200; readiness with no reviewed data must
   return 503. Raw events, guided generation, free queries and operational counters
   must return 404. A closed readiness gate is an expected staging state.
2. Before any import, take `pg_dump -Fc` into private storage. Record source/report
   hashes, schema revision and row counts beside the backup; keep credentials out
   of the repository and recorded terminal commands.
3. Restore with `pg_restore --exit-on-error --no-owner` into a **new empty** private
   PostgreSQL database. Retain the original database. Check migrations, match and
   prediction counts, source manifests, current report hashes and resolved evidence.
4. For a reviewed showcase, readiness must now return 200 with all 36 current
   approved reports. Verify one source citation and mobile navigation before routing
   traffic. For an unreviewed backup, confirm 503 remains and no report leaks.
5. Switch database URL and image digest together only after verification. Retain
   the previous database/image until the rollback is confirmed. Record the rehearsal
   outcome; a documented procedure alone is not a tested recovery-time objective.

See [public release](public-release.md) for the data transfer and review gates.
