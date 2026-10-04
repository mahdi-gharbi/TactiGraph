"""Compare an invented PostgreSQL backup with its NEW restored CI database."""

import hashlib
import json
import os

from fastapi.testclient import TestClient
from sqlalchemy import MetaData, select

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.db import make_engine
from tactigraph.testing import MATCH_ID, SYNTHETIC_VERSION


def table_fingerprints(engine):
    metadata = MetaData()
    metadata.reflect(engine)
    fingerprints = {}
    with engine.connect() as connection:
        for name, table in sorted(metadata.tables.items()):
            rows = sorted(
                json.dumps(dict(row), sort_keys=True, default=str, separators=(",", ":"))
                for row in connection.execute(select(table)).mappings()
            )
            fingerprints[name] = {
                "rows": len(rows),
                "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
            }
    return fingerprints


def verify_api(settings, engine):
    with TestClient(create_app(settings, engine, include_secondary_league=False)) as client:
        summary = client.get(f"/api/v1/matches/{MATCH_ID}/summary")
        assert summary.status_code == 200
        assert summary.json()["model"]["model_version"] == SYNTHETIC_VERSION
        assert [team["xg"] for team in summary.json()["teams"]] == [0.75, 0.25]
        response = client.post(
            "/api/v1/analyst/report",
            json={"match_id": MATCH_ID, "team_id": 10, "intent": "chance_creation"},
        )
        assert response.status_code == 200
        report = response.json()
        assert report["status"] == "verified"
        measured = next(c for c in report["claims"] if c["predicate"] == "compare_metric")
        assert (measured["before"], measured["after"]) == (1, 2)
        for evidence_id in measured["evidence_ids"]:
            evidence = client.get(f"/api/v1/tactical-evidence/{evidence_id}")
            assert evidence.status_code == 200
            assert evidence.json()["source_sha256"] == report["evidence"]["source_sha256"]
        assert client.get("/api/v1/ready").status_code == 503


def main():
    source_url = os.environ["TACTIGRAPH_RESTORE_SOURCE_URL"]
    restored_url = os.environ["TACTIGRAPH_RESTORE_TARGET_URL"]
    if source_url == restored_url:
        raise ValueError("Restoration verification requires a separate restored database")
    source_settings = Settings(_env_file=None, mode="local", database_url=source_url)
    restored_settings = Settings(_env_file=None, mode="local", database_url=restored_url)
    source, restored = make_engine(source_settings), make_engine(restored_settings)
    try:
        original = table_fingerprints(source)
        assert original == table_fingerprints(restored), "Restored table contents differ"
        verify_api(restored_settings, restored)
        # Idempotent startup migrations and read-only API calls must preserve the backup.
        assert original == table_fingerprints(restored), "Verification changed restored contents"
        print(json.dumps({"status": "verified", "tables": original}, indent=2))
    finally:
        source.dispose()
        restored.dispose()


if __name__ == "__main__":
    main()
