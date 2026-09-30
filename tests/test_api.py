import pytest
from fastapi.testclient import TestClient

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.data.ingest import ingest_payload


@pytest.fixture
def client(database, payload):
    engine, factory = database
    ingest_payload(factory, *payload)
    with TestClient(create_app(Settings(mode="local"), engine)) as client:
        yield client


def test_counts_reconcile_without_fabricated_xg(client):
    summary = client.get("/api/v1/matches/1/summary").json()
    layer = client.get("/api/v1/matches/1/shots").json()
    assert layer["total_shots"] == sum(t["shots"] for t in summary["teams"]) == 4
    assert layer["located_shots"] == 3
    assert all(t["xg"] is None and t["xg_status"] == "not_trained" for t in summary["teams"])
    assert all(s["xg"] is None for s in layer["shots"])


def test_untrained_experiment_is_explicit(client):
    response = client.get("/api/v1/experiments")
    assert response.status_code == 200
    assert response.json()["status"] == "not_trained"
    assert response.json()["report"] is None


def test_untrained_graph_and_bounded_predictions_are_explicit(client):
    response = client.get("/api/v1/experiments/graph")
    assert response.json() == {"status": "not_trained", "report": None}
    query = "/api/v1/matches/1/third-pass?team_id=10&period=1"
    assert client.get(query).json()["status"] == "unavailable"
    assert client.get(query + "&limit=101").status_code == 422
    assert client.get("/api/v1/matches/1/third-pass?team_id=999&period=1").status_code == 422


def test_graph_predictions_require_matching_release_and_clear_on_reingest(
    client, database, payload
):
    from datetime import datetime, timezone

    from tactigraph.config import SOURCE_COMMIT
    from tactigraph.db import DatasetReport

    _, sessions = database
    with sessions.begin() as session:
        session.add(
            DatasetReport(
                id="graph",
                generated_at=datetime.now(timezone.utc),
                payload={"lock": {"run_id": "synthetic-run"}},
            )
        )
        session.add(
            DatasetReport(
                id="graph-predictions-1",
                generated_at=datetime.now(timezone.utc),
                payload={
                    "source_commit": SOURCE_COMMIT,
                    "model": {
                        "model_version": "test-graph",
                        "family": "logistic",
                        "artifact_hash": "synthetic",
                        "run_id": "synthetic-run",
                        "feature_version": "synthetic-prefix",
                    },
                    "samples": [
                        {
                            "sample_id": "synthetic",
                            "cutoff_event_id": payload[1][0]["id"],
                            "team_id": 10,
                            "period": 1,
                            "timestamp": "00:00:01.000",
                            "cutoff_ms": 1000,
                            "probability": 0.2,
                            "split": "train",
                            "observed_later_shot": False,
                        }
                    ],
                },
            )
        )
    url = "/api/v1/matches/1/third-pass?team_id=10&period=1"
    response = client.get(url).json()
    assert response["status"] == "ready"
    assert response["samples"][0]["probability"] == 0.2
    assert response["total"] == 1
    assert "in-sample" in response["warning"]
    assert client.get(url + "&offset=1").json()["samples"] == []
    ingest_payload(sessions, *payload)
    assert client.get(url).json()["status"] == "unavailable"


def test_prediction_totals_provenance_and_stale_invalidation(client, database, payload):
    from datetime import datetime, timezone

    from tactigraph.db import ModelRelease, Prediction, PredictionSample

    _, sessions = database
    with sessions.begin() as session:
        session.add(
            ModelRelease(
                id="synthetic-xg",
                family="logistic",
                status="evaluated",
                artifact_hash="synthetic-hash",
                run_id="synthetic-run",
                feature_version="test",
                source_commit="synthetic",
                created_at=datetime.now(timezone.utc),
                report={},
            )
        )
        session.flush()
        for event, probability, penalty in (
            (payload[1][1], 0.2, False),
            (payload[1][2], 0.75, True),
        ):
            session.add(
                PredictionSample(
                    id=event["id"],
                    match_id=1,
                    task="xg",
                    split="test",
                    feature_version="test",
                    label=False,
                    penalty=penalty,
                    features={},
                )
            )
            session.flush()
            session.add(
                Prediction(
                    sample_id=event["id"], model_version="synthetic-xg", probability=probability
                )
            )
    summary = client.get("/api/v1/matches/1/summary").json()
    assert sum(t["xg"] for t in summary["teams"]) == pytest.approx(0.95)
    assert sum(t["penalty_xg"] for t in summary["teams"]) == 0.75
    assert all(t["xg_status"] == "partial" for t in summary["teams"])
    points = client.get("/api/v1/matches/1/shots").json()["shots"]
    assert points[0]["xg"] == 0.2
    assert points[0]["model"]["sample_id"] == points[0]["event_id"]
    assert points[0]["model"]["artifact_hash"] == "synthetic-hash"
    assert points[2]["xg"] is None
    ingest_payload(sessions, *payload)
    assert client.get("/api/v1/experiments").json()["status"] == "unavailable"
    assert all(t["xg"] is None for t in client.get("/api/v1/matches/1/summary").json()["teams"])


def test_period_window_is_half_open_and_does_not_confuse_halves(client):
    layer = client.get("/api/v1/matches/1/shots?period=2&start_ms=0&end_ms=900000").json()
    assert layer["total_shots"] == 1
    assert layer["shots"][0]["index"] == 4
    assert (
        client.get("/api/v1/matches/1/shots?period=1&start_ms=2700000").json()["total_shots"] == 1
    )


def test_evidence_resolves_exact_ordered_events_and_stable_result(client):
    layer = client.get("/api/v1/matches/1/shots?team_id=10").json()
    evidence = client.get(f"/api/v1/evidence/{layer['result_id']}").json()
    assert evidence["value"] == 2
    assert [e["event_id"] for e in evidence["references"]] == [
        s["event_id"] for s in layer["shots"]
    ]
    assert [e["index"] for e in evidence["references"]] == [2, 4]
    assert all(
        evidence["provenance"]["source_commit"] in r["source_url"] for r in evidence["references"]
    )
    assert "Home FC recorded 2 shots" in evidence["statement"]
    assert client.get(f"/api/v1/evidence/{layer['result_id']}").json() == evidence


def test_zero_is_evidence_not_missing_data(client):
    layer = client.get("/api/v1/matches/1/shots?period=2&start_ms=1&end_ms=2").json()
    evidence = client.get(f"/api/v1/evidence/{layer['result_id']}").json()
    assert evidence["value"] == 0
    assert evidence["references"] == []


@pytest.mark.parametrize(
    "query",
    [
        "team_id=999",
        "period=5",
        "start_ms=1",
        "period=1&start_ms=100&end_ms=50",
        "period=1&end_ms=7200001",
        "player_id=999",
        "team_id=10&player_id=21",
    ],
)
def test_invalid_filters_are_rejected(client, query):
    assert client.get(f"/api/v1/matches/1/shots?{query}").status_code == 422


def test_unknown_match_and_malformed_evidence(client):
    assert client.get("/api/v1/matches/999/summary").status_code == 404
    assert client.get("/api/v1/evidence/not-a-query").status_code == 422
    assert client.get("/api/v1/evidence/shots-1-10-2-100-50-0").status_code == 422


def test_local_event_pagination(client):
    result = client.get("/api/v1/matches/1/events?offset=1&limit=2").json()
    assert [e["index"] for e in result["events"]] == [2, 3]
    assert result["total"] == 6
    assert client.get("/api/v1/matches/1/events?limit=99999").status_code == 422


def test_dataset_without_audit_is_explicit(client):
    report = client.get("/api/v1/dataset").json()
    assert report["status"] == "not_audited"
    assert report["ingested_matches"] == 1
    assert report["report"] is None


def test_outside_pitch_shot_is_counted_but_not_plotted(database, payload):
    engine, factory = database
    payload[1][1]["location"] = [120.9, 40]
    ingest_payload(factory, *payload)
    with TestClient(create_app(Settings(mode="local"), engine)) as client:
        layer = client.get("/api/v1/matches/1/shots").json()
        assert layer["total_shots"] == 4
        assert layer["located_shots"] == 2
        assert layer["shots"][0]["location_status"] == "outside_pitch"
        assert layer["shots"][0]["x"] is None
        evidence = client.get(f"/api/v1/evidence/{layer['result_id']}").json()
        assert evidence["value"] == 4


def test_public_mode_blocks_full_event_access(database, payload):
    engine, factory = database
    ingest_payload(factory, *payload)
    with TestClient(create_app(Settings(mode="public"), engine)) as client:
        assert client.get("/api/v1/matches/1/events").status_code == 404
        assert client.get("/api/v1/matches/1/shots").status_code == 200
        assert client.get("/api/v1/matches").json()["mode"] == "public"
