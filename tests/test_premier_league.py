from copy import deepcopy

from fastapi.testclient import TestClient

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.data.ingest import ingest_payload
from tactigraph.data.splits import build_manifest
from tactigraph.db import EventContext, MatchQuality, initialize, make_engine


def test_negative_source_duration_is_flagged_without_mutating_source(database, payload):
    _, sessions = database
    payload[1][0]["duration"] = -12.5
    ingest_payload(sessions, *payload)
    assert payload[1][0]["duration"] == -12.5
    with sessions() as session:
        assert session.get(EventContext, payload[1][0]["id"]).duration is None
        quality = session.get(MatchQuality, payload[0]["match_id"]).payload
        assert quality["issue_counts"]["negative_duration_unavailable"] == 1


def test_premier_split_is_chronological_date_grouped_and_outcome_blind():
    matches = [
        {
            "match_id": i,
            "match_date": f"2015-09-{1 + i // 2:02d}",
            "competition": {"competition_id": 2},
            "season": {"season_id": 27},
            "home_team": {"home_team_id": 10},
            "away_team": {"away_team_id": 20},
        }
        for i in range(40)
    ]
    frozen = build_manifest(matches)
    assert frozen["counts"] == {"train": 24, "tuning": 6, "calibration": 4, "test": 6}
    partitions = {"train": 0, "tuning": 1, "calibration": 2, "test": 3}
    order = [partitions[a["partition"]] for a in frozen["assignments"]]
    assert order == sorted(order)
    for date in {m["match_date"] for m in matches}:
        assert len({a["partition"] for a in frozen["assignments"] if a["match_date"] == date}) == 1
    for match in matches:
        match["home_score"] = 999
    assert build_manifest(list(reversed(matches))) == frozen


def test_league_routes_keep_matches_and_models_isolated(tmp_path, payload):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path}/wsl.db")
    premier = settings.for_league("premier-league")
    assert premier.database_url != settings.database_url
    assert premier.data_dir != settings.data_dir
    for config, mid, competition in ((settings, 1, "WSL"), (premier, 2, "Premier League")):
        sample = deepcopy(payload)
        sample[0]["match_id"] = mid
        sample[0]["competition"]["competition_name"] = competition
        engine = make_engine(config)
        ingest_payload(initialize(engine), *sample)
        engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert [m["id"] for m in client.get("/api/v1/matches").json()["matches"]] == [1]
        prefix = "/leagues/premier-league/api/v1"
        assert [m["id"] for m in client.get(prefix + "/matches").json()["matches"]] == [2]
        assert client.get(prefix + "/matches/1/summary").status_code == 404
        assert client.get("/api/v1/matches/2/summary").status_code == 404
        assert client.get(prefix + "/experiments").json()["status"] == "not_trained"


def test_public_mode_does_not_mount_local_premier_database(tmp_path):
    settings = Settings(
        mode="public", data_dir=tmp_path, database_url=f"sqlite:///{tmp_path}/public.db"
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/leagues/premier-league/api/v1/matches").status_code == 404
