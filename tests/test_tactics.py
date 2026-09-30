from copy import deepcopy
from types import SimpleNamespace as NS
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tactigraph.analytics.windows import analyze, exposure, passing_network
from tactigraph.api.app import create_app
from tactigraph.api.tactical_schemas import Window
from tactigraph.config import Settings
from tactigraph.data.ingest import ingest_payload


def row(index, sender=11, recipient=12, x=70, end_x=85, complete=True, team=10, time=1000):
    event = NS(
        id=str(UUID(int=index)),
        index=index,
        period=2,
        period_ms=time,
        player_id=sender,
        player_name=str(sender),
        team_id=team,
        x=x,
        y=40,
        type="Pass",
    )
    pass_ = NS(
        completed=complete,
        recipient_id=recipient,
        recipient_name=str(recipient),
        end_x=end_x,
        end_y=40,
    )
    return event, pass_, None, None


def test_network_counts_strength_direction_and_exact_betweenness():
    rows = [row(1), row(2), row(3, 12, 13)]
    network, refs = passing_network(rows, [], Window(period=2, start_ms=0, end_ms=60000), "test")
    assert network["pass_count"] == len(refs) == 3
    assert network["density"] == pytest.approx(2 / 6)
    assert network["concentration"] == pytest.approx(5 / 9)
    nodes = {n["player_id"]: n for n in network["nodes"]}
    assert nodes[11]["out_strength"] == 2
    assert nodes[12]["in_strength"] == 2
    assert nodes[12]["out_strength"] == 1
    assert nodes[12]["betweenness"] == 0.5
    assert nodes[11]["betweenness"] == nodes[13]["betweenness"] == 0
    assert nodes[12]["x"] == pytest.approx((85 + 85 + 70) / 3)
    assert nodes[12]["exposure_minutes"] is None


def test_window_counts_boundaries_carries_field_tilt_and_missing_xg():
    rows = [
        row(1),
        row(2, complete=False),
        row(3, x=80),
        row(4, team=20),
        row(5, time=60000),
        row(6, x=121),
    ]
    carry = NS(id="carry", index=7, type="Carry", period=2, period_ms=3000, team_id=10, x=79, y=20)
    rows.append((carry, None, NS(end_x=80, end_y=20), None))
    analysis, refs = analyze(1, 10, Window(period=2, start_ms=0, end_ms=60000), rows, [], None, {})
    values = {m.metric: m for m in analysis.measurements}
    assert values["passes"].value == 4
    assert values["completed_passes"].value == 0.75
    assert values["final_third_entries"].value == 2
    assert values["final_third_entries"].denominator == 1
    assert values["field_tilt"].value == 0.75  # Endpoint valid even if origin invalid.
    assert len(refs["field_tilt"]) == 4  # Includes opponent denominator evidence.
    assert values["xg"].value is None
    assert any("invalid coordinates" in w for w in analysis.warnings)


def test_empty_window_is_not_zero_field_tilt_or_completion():
    result, _ = analyze(1, 10, Window(period=2, start_ms=0, end_ms=60000), [], [], None, {})
    values = {m.metric: m.value for m in result.measurements}
    assert values["field_tilt"] is values["completed_passes"] is None
    assert values["final_third_entries"] == values["passes"] == values["shots"] == 0
    assert result.network.concentration is None


def test_lineup_exposure_merges_overlapping_roles_and_respects_halftime():
    def stint(start, end, period=2):
        return NS(
            player_id=11, start_period=period, end_period=2, start_ms=start, end_ms=end
        ), "Player"

    minutes, _ = exposure(
        [stint(0, 40000), stint(30000, 60000)], Window(period=2, start_ms=0, end_ms=60000)
    )
    assert minutes == {11: 1}
    minutes, _ = exposure([stint(2700000, 30000, 1)], Window(period=2, start_ms=0, end_ms=60000))
    assert minutes == {11: 0.5}


@pytest.fixture
def client(database, payload):
    engine, factory = database
    match, events, lineups = deepcopy(payload)
    end = deepcopy(events[0])
    end.update(
        id=str(UUID(int=999)),
        index=99,
        period=2,
        timestamp="00:48:00.000",
        minute=93,
        type={"name": "Half End"},
    )
    end.pop("pass")
    events.append(end)
    ingest_payload(factory, match, events, lineups)
    with TestClient(create_app(Settings(mode="public"), engine)) as client:
        yield client


def arguments():
    return {
        "team_id": 10,
        "before": {"period": 2, "start_ms": 0, "end_ms": 900000},
        "after": {"period": 2, "start_ms": 900000, "end_ms": 1800000},
    }


def test_comparison_and_paginated_evidence_resolve_without_raw_public_events(client):
    response = client.post("/api/v1/matches/1/compare", json=arguments())
    assert response.status_code == 200, response.text
    report = response.json()
    assert report == client.post("/api/v1/matches/1/compare", json=arguments()).json()
    shots = next(m for m in report["before"]["measurements"] if m["metric"] == "shots")
    assert shots["value"] == 1
    evidence = client.get(f"/api/v1/tactical-evidence/{shots['evidence_id']}?limit=1").json()
    assert evidence["total"] == 1
    assert evidence["references"][0]["event_id"] == str(UUID(int=4))
    assert evidence["measurement"]["value"] == 1
    assert evidence["provenance"]["metric_version"] == "windows-network-v1"
    assert (
        client.get(f"/api/v1/tactical-evidence/{shots['evidence_id']}?offset=1").json()[
            "references"
        ]
        == []
    )
    assert client.get("/api/v1/matches/1/events").status_code == 404


@pytest.mark.parametrize("change", ["halftime", "overlap", "team", "coverage", "negative"])
def test_reject_unsupported_comparisons(client, change):
    args = arguments()
    if change == "halftime":
        args["before"]["period"] = 1
    elif change == "overlap":
        args["after"]["start_ms"] = 1
    elif change == "team":
        args["team_id"] = 999
    elif change == "coverage":
        args["after"]["end_ms"] = 7200000
    else:
        args["before"]["start_ms"] = -1
    assert client.post("/api/v1/matches/1/compare", json=args).status_code == 422


def test_invalid_evidence_and_network_ranges(client):
    assert client.get("/api/v1/tactical-evidence/arbitrary-sql").status_code == 404
    assert client.get("/api/v1/tactical-evidence/tactics-1-10-2-900-100-shots").status_code == 422
    assert (
        client.get(
            "/api/v1/matches/1/network?team_id=10&period=2&start_ms=0&end_ms=900000"
        ).status_code
        == 200
    )


def test_trends_do_not_cross_halftime_and_evidence_matches_curve(client):
    response = client.get("/api/v1/matches/1/trends?team_id=10&period=2")
    assert response.status_code == 200
    report = response.json()
    assert report["points"][0]["start_ms"] == 0
    assert report["points"][0]["end_ms"] == 60000
    assert report["points"][0]["shots"] == 1
    assert report["points"][0]["xg"] is None
    for point in report["points"]:
        assert 0 <= point["start_ms"] < point["end_ms"]
        assert point["end_ms"] - point["start_ms"] <= 300000
    assert client.get("/api/v1/matches/1/trends?team_id=10&period=3").status_code == 422


def test_candidate_shifts_are_ranked_by_rates_with_exact_backing_windows():
    from tactigraph.analytics.trends import trends

    rows = [
        row(1, time=1000),
        row(2, time=301000),
        row(3, time=302000),
        row(4, time=901000),
        row(5, time=902000),
        row(6, time=903000),
        row(7, time=1500000, complete=False),
    ]
    _, shifts = trends(1, 10, 2, rows, None, {}, None)
    assert len(shifts) == 3
    assert shifts[0].boundary_ms == 900000
    assert shifts[0].before_count == 0
    assert shifts[0].after_count == 3
    assert shifts[0].rate_difference == 0.6
    assert shifts[0].before_evidence_id == "tactics-1-10-2-600000-900000-final_third_entries"


def test_published_xt_is_invalidated_by_reimport(client, database, payload):
    from datetime import datetime, timezone

    from tactigraph.db import DatasetReport

    _, factory = database
    with factory.begin() as session:
        session.add(
            DatasetReport(
                id="xt",
                generated_at=datetime.now(timezone.utc),
                payload={
                    "version": "synthetic-xt",
                    "model": {"grid": [1, 1], "values": [0.1], "pipeline_version": "synthetic"},
                    "lock": {"artifact_hash": "synthetic", "run_id": "synthetic"},
                },
            )
        )
    report = client.post("/api/v1/matches/1/compare", json=arguments()).json()
    assert report["xt_status"] == "ready"
    assert report["xt_model"]["family"] == "spatial-markov"
    # The only event in this window is a shot: no movement-xT double credit.
    metric = next(m for m in report["before"]["measurements"] if m["metric"] == "movement_xt")
    assert metric["value"] == 0
    ingest_payload(factory, *payload)
    assert client.get("/api/v1/experiments/xt").json()["status"] == "not_trained"
    assert (
        client.get(
            "/api/v1/matches/1/network?team_id=10&period=5&start_ms=0&end_ms=900000"
        ).status_code
        == 422
    )
