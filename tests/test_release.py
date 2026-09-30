import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tactigraph.analyst.workflow import run
from tactigraph.api.app import create_app
from tactigraph.api.showcase import showcase
from tactigraph.config import SOURCE_COMMIT, Settings
from tactigraph.data.ingest import ingest_payload
from tactigraph.db import DatasetReport, Match, SourceManifest, initialize, make_engine
from tactigraph.release import VERSION, approve, export_review, fingerprint
from tactigraph.transfer import transfer


def seed(sessions, payload):
    ingest_payload(sessions, *payload)
    with sessions.begin() as session:
        session.add(
            SourceManifest(
                path="data/events/1.json",
                commit=SOURCE_COMMIT,
                sha256="a" * 64,
                retrieved_at=datetime.now(timezone.utc),
                schema_version="synthetic",
                validation_status="valid",
            )
        )
        session.flush()
        report = run(
            session,
            {
                "match_id": 1,
                "team_id": 10,
                "intent": "chance_creation",
                "before": {"period": 1, "start_ms": 0, "end_ms": 600000},
                "after": {"period": 1, "start_ms": 600000, "end_ms": 1200000},
            },
        )
        stored = {
            "matches": [{"match_id": 1, "home": "Synthetic home", "away": "Synthetic away"}],
            "reports": [
                {
                    "report": report.model_dump(mode="json"),
                    "sha256": fingerprint(report),
                    "review": None,
                }
            ],
            "publication_review": None,
        }
        session.add(
            DatasetReport(id=VERSION, generated_at=datetime.now(timezone.utc), payload=stored)
        )
        return stored


def test_pending_reports_are_local_only_and_live_public_generation_is_blocked(database, payload):
    engine, sessions = database
    seed(sessions, payload)
    with sessions() as session:
        assert len(showcase(session, False).reports) == 1
        assert showcase(session, True).reports == []
    with TestClient(create_app(Settings(mode="public"), engine)) as client:
        assert client.get("/api/v1/showcase").json()["status"] == "review_pending"
        assert client.get("/api/v1/ready").status_code == 503
        assert client.get("/api/v1/matches/1/events").status_code == 404
        assert (
            client.post(
                "/api/v1/analyst/report",
                json={
                    "match_id": 1,
                    "team_id": 10,
                    "intent": "chance_creation",
                    "generation": "groq",
                },
            ).status_code
            == 404
        )


def test_review_is_bound_to_exact_report_and_source(database, payload, tmp_path):
    _, sessions = database
    stored = seed(sessions, payload)
    export_review(stored, tmp_path)
    path = tmp_path / "approvals.json"
    review = json.loads(path.read_text())
    with sessions.begin() as session, pytest.raises(ValueError, match="named reviewer"):
        approve(session, path)
    review.update(reviewer="Synthetic test reviewer", reviewed_at="2026-09-25T12:00:00+00:00")
    review["publication_review"] = dict.fromkeys(review["publication_review"], True)
    review["reports"][0]["approved"] = True
    path.write_text(json.dumps(review))
    with sessions.begin() as session:
        approve(session, path)
        assert showcase(session, True).status == "available"
        assert len(showcase(session, True).reports) == 1
        served = showcase(session, True).reports[0]
        assert fingerprint(served.report) == served.sha256
    # Export must preserve a human's work.
    export_review(stored, tmp_path)
    assert json.loads(path.read_text())["reviewer"] == "Synthetic test reviewer"
    with sessions.begin() as session:
        session.get(SourceManifest, "data/events/1.json").sha256 = "changed"
        session.flush()
        assert showcase(session, True).status == "stale"
        with pytest.raises(ValueError, match="stale report"):
            approve(session, path)


def test_tampered_report_never_served(database, payload):
    _, sessions = database
    seed(sessions, payload)
    with sessions.begin() as session:
        row = session.get(DatasetReport, VERSION)
        altered = json.loads(json.dumps(row.payload))
        altered["reports"][0]["report"]["claims"][0]["text"] = "Fabricated fact"
        row.payload = altered
        session.flush()
        assert showcase(session, False).status == "stale"
        assert showcase(session, True).reports == []


def test_transfer_preserves_evidence_and_refuses_nonempty_target(payload, tmp_path):
    source = Settings(database_url=f"sqlite:///{tmp_path / 'source.db'}")
    target = Settings(database_url=f"sqlite:///{tmp_path / 'target.db'}")
    engine = make_engine(source)
    sessions = initialize(engine)
    seed(sessions, payload)
    engine.dispose()
    result = transfer(source.database_url, target)
    assert result["selected_matches"] == result["rows"]["matches"] == 1
    with pytest.raises(ValueError, match="Target must be empty"):
        transfer(source.database_url, target)
    copied = make_engine(target)
    with initialize(copied)() as session:
        assert session.scalar(select(func.count()).select_from(Match)) == 1
        assert showcase(session, False).status == "review_pending"
    copied.dispose()


def test_render_postgres_url_uses_installed_driver():
    assert (
        Settings(database_url="postgres://u:p@host/db").database_url
        == "postgresql+psycopg://u:p@host/db"
    )
