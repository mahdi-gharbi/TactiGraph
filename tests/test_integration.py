"""Same migration/ingestion/publication/API journey on SQLite and a dedicated PostgreSQL DB."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.db import SourceManifest, initialize, make_engine
from tactigraph.testing import MATCH_ID, SYNTHETIC_VERSION, seed_synthetic


@pytest.fixture
def integration_database(tmp_path):
    # The explicit integration variable must point at an EMPTY disposable DB. Never use .env.
    url = os.environ.get("TACTIGRAPH_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'integration.db'}")
    settings = Settings(_env_file=None, database_url=url, mode="local")
    engine = make_engine(settings)
    sessions = initialize(engine)
    seed_synthetic(sessions)
    yield settings, engine, sessions
    engine.dispose()


def test_migrate_seed_publish_and_resolve_evidence(integration_database):
    settings, engine, sessions = integration_database
    # An idempotent second migration must preserve seeded rows and predictions.
    initialize(engine)
    with TestClient(create_app(settings, engine, include_secondary_league=False)) as client:
        summary = client.get(f"/api/v1/matches/{MATCH_ID}/summary")
        assert summary.status_code == 200, summary.text
        assert [team["xg"] for team in summary.json()["teams"]] == [0.75, 0.25]
        assert summary.json()["model"]["model_version"] == SYNTHETIC_VERSION
        assert client.get("/api/v1/experiments").status_code == 200
        layer = client.get(f"/api/v1/matches/{MATCH_ID}/shots").json()
        evidence = client.get(f"/api/v1/evidence/{layer['result_id']}").json()
        assert evidence["value"] == len(evidence["references"]) == 4
        with sessions() as session:
            source = session.scalar(
                select(SourceManifest).where(SourceManifest.path == f"data/events/{MATCH_ID}.json")
            )
            assert evidence["source_sha256"] == source.sha256
        response = client.post(
            "/api/v1/analyst/report",
            json={"match_id": MATCH_ID, "team_id": 10, "intent": "chance_creation"},
        )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["status"] == "verified"
        shots = next(c for c in report["claims"] if c["predicate"] == "compare_metric")
        assert (shots["before"], shots["after"]) == (1, 2)
        for evidence_id in shots["evidence_ids"]:
            cited = client.get(f"/api/v1/tactical-evidence/{evidence_id}")
            assert cited.status_code == 200, cited.text
            assert cited.json()["source_sha256"] == evidence["source_sha256"]
        assert client.get("/api/v1/ready").status_code == 503
    with pytest.raises(ValueError, match="empty dedicated"):
        seed_synthetic(sessions)
