"""Run against local/staging DB; writes aggregate verification, never credentials."""

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tactigraph.analyst.contracts import AnalystReport
from tactigraph.analyst.evaluation import raw_oracle
from tactigraph.analyst.workflow import ALLOWED, run
from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.db import DatasetReport, Match, initialize, make_engine
from tactigraph.release import VERSION, current, fingerprint

parser = argparse.ArgumentParser()
parser.add_argument("--raw", action="store_true")
parser.add_argument("--output", type=Path, default=Path("output/m8-verification.json"))
args = parser.parse_args()
settings = Settings()
engine = make_engine(settings)
sessions = initialize(engine)
with sessions() as session:
    payload = session.get(DatasetReport, VERSION).payload
    assert len(payload["matches"]) == 12 and len(payload["reports"]) == 36
    selected = {m["match_id"] for m in payload["matches"]}
    assert len(selected) == 12
    total_matches = session.scalar(select(func.count()).select_from(Match))
    ids = set()
    oracle_count = 0
    for entry in payload["reports"]:
        report = AnalystReport.model_validate(entry["report"])
        assert current(session, report)
        assert fingerprint(report) == entry["sha256"]
        fresh = run(session, report.arguments)
        assert fresh.evidence.result_id == report.evidence.result_id
        assert fresh.claims == report.claims
        assert report.status == "verified" and report.verification_rejections == 0
        assert report.arguments.match_id in selected
        ids.update(e for c in report.claims for e in c.evidence_ids)
        if args.raw:
            path = (
                settings.data_dir
                / "raw"
                / report.evidence.source_commit
                / "data/events"
                / f"{report.arguments.match_id}.json"
            )
            content = path.read_bytes()
            assert hashlib.sha256(content).hexdigest() == report.evidence.source_sha256
            events = json.loads(content)
            core = ALLOWED[report.arguments.intent][0]
            for window, facts in (
                (report.arguments.before, report.evidence.before),
                (report.arguments.after, report.evidence.after),
            ):
                expected, _ = raw_oracle(
                    events, report.arguments.team_id, window.model_dump(), report.arguments.intent
                )
                actual = next(f.value for f in facts if f.metric == core)
                assert abs(actual - expected) < 1e-10
                oracle_count += 1

results = {
    "dialect": engine.dialect.name,
    "ingested_matches": total_matches,
    "showcase_matches": 12,
    "reports_recomputed": 36,
    "raw_oracle_comparisons": oracle_count,
    "human_review": "pending",
    "benchmark_scope": "warm single-client TestClient, three warmups then twenty requests; "
    "not internet latency",
}
with TestClient(
    create_app(Settings(database_url=settings.database_url, mode="public"), engine)
) as client:
    assert client.get("/api/v1/showcase").json() == {"status": "review_pending", "reports": []}
    assert client.get("/api/v1/ready").status_code == 503
    for path in (
        "/data/tactigraph.db",
        "/.env",
        "/output/release-review/reports.json",
        "/artifacts/styles-v1/model.joblib",
        f"/api/v1/matches/{min(selected)}/events",
    ):
        assert client.get(path).status_code == 404
    report = payload["reports"][0]["report"]
    assert client.post("/api/v1/analyst/report", json=report["arguments"]).status_code == 404
    for evidence_id in sorted(ids):
        response = client.get(f"/api/v1/tactical-evidence/{evidence_id}?limit=1")
        assert response.status_code == 200, evidence_id
        assert response.json()["source_sha256"]
    results["resolved_evidence_ids"] = len(ids)
    timings = {}
    for path in (
        "/api/v1/showcase",
        "/api/v1/experiments/styles",
        f"/api/v1/matches/{min(selected)}/summary",
    ):
        for _ in range(3):
            assert client.get(path).status_code == 200
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            assert client.get(path).status_code == 200
            samples.append(1000 * (time.perf_counter() - start))
        timings[path] = {"median_ms": statistics.median(samples), "p95_ms": sorted(samples)[18]}
    results["timings"] = timings
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
