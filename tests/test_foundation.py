from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, inspect, select, text

from tactigraph.data.derive import active_players_at, derive, replay_active_players
from tactigraph.data.ingest import ingest_payload, normalize
from tactigraph.db import Event, EventContext, Match, initialize
from tactigraph.migrations.schema import snapshot


def sequence(payload):
    match = payload[0]
    lineup = [
        {
            "team_id": 10,
            "lineup": [{"player_id": p, "player_name": f"Player {p}"} for p in (11, 12, 13, 14)],
        },
        {"team_id": 20, "lineup": [{"player_id": 21, "player_name": "Player 21"}]},
    ]
    raw = []

    def add(kind, team=10, player=11, possession=1, owner=10, period=1, **extra):
        index = len(raw) + 1
        raw.append(
            {
                "id": str(UUID(int=index)),
                "index": index,
                "period": period,
                "timestamp": f"00:00:{index:02d}.000",
                "minute": 0 if period == 1 else 45,
                "second": index,
                "type": {"name": kind},
                "team": {"id": team, "name": "Home FC" if team == 10 else "Away FC"},
                "player": {"id": player, "name": f"Player {player}"},
                "possession": possession,
                "possession_team": {"id": owner},
                "play_pattern": {"name": "Regular Play"},
                "location": [70, 40],
                **extra,
            }
        )

    def tactics(players):
        return {
            "lineup": [
                {
                    "player": {"id": p, "name": f"Player {p}"},
                    "position": {"id": pos, "name": f"Role {pos}"},
                }
                for p, pos in players
            ]
        }

    add("Starting XI", tactics=tactics([(11, 9), (12, 8), (13, 6)]))
    add("Starting XI", team=20, player=21, tactics=tactics([(21, 9)]))
    add("Pass", pass_={})
    raw[-1]["pass"] = {"end_location": [85, 40], "recipient": {"id": 12, "name": "Player 12"}}
    add("Pressure", team=20, player=21)
    add("Pass", player=12)
    raw[-1]["pass"] = {"end_location": [100, 40], "recipient": {"id": 11, "name": "Player 11"}}
    add("Shot", shot={"outcome": {"name": "Goal"}, "type": {"name": "Open Play"}})
    add("Carry", player=12, carry={"end_location": [85, 40]})
    add("Pass", player=12)
    raw[-1]["pass"] = {"end_location": [90, 40], "outcome": {"name": "Incomplete"}}
    add("Ball Recovery", team=20, player=21, owner=20, possession=2, ball_recovery={})
    add("Pass", team=20, player=21, owner=20, possession=2)
    raw[-1]["pass"] = {"end_location": [80, 40], "type": {"name": "Throw-in"}}
    add("Miscontrol", team=20, player=21, owner=20, possession=2)
    add("Half End", team=20, player=21, owner=20, possession=2)
    add(
        "Substitution",
        period=2,
        possession=3,
        substitution={"replacement": {"id": 14, "name": "Player 14"}},
    )
    add("Tactical Shift", period=2, possession=3, tactics=tactics([(12, 7), (13, 6), (14, 9)]))
    add(
        "Bad Behaviour",
        player=12,
        period=2,
        possession=3,
        bad_behaviour={"card": {"name": "Red Card"}},
    )
    add("Carry", player=14, period=2, possession=3, carry={"end_location": [90, 40]})
    add("Player Off", player=14, period=2, possession=3, player_off={"permanent": False})
    add("Player On", player=14, period=2, possession=3)
    add("Half End", player=14, period=2, possession=3)
    return match, raw, lineup


def test_opponent_events_rebounds_losses_and_restarts(payload):
    match, raw, lineup = sequence(payload)
    _, events, passes, shots = normalize(match, raw, lineup)
    derived = derive(match, raw, events, passes, shots, lineup)
    episodes = derived["control_episodes"]
    assert episodes[0]["completed_passes"] == 2
    assert episodes[0]["end_reason"] == "shot"
    assert episodes[0]["has_shot"]
    assert str(UUID(int=4)) not in {r["event_id"] for r in derived["episode_events"]}
    assert str(UUID(int=4)) in derived["possessions"][0]["event_ids"]
    assert episodes[1]["start_reason"] == "after_shot"
    assert episodes[1]["end_reason"] == "loss"
    assert episodes[2]["end_reason"] == "restart"
    assert episodes[3]["start_reason"] == "restart"
    assert episodes[3]["end_reason"] == "loss"
    assert episodes[-1]["end_reason"] == "period_end"
    members = [m["event_id"] for m in derived["episode_events"]]
    assert len(members) == len(set(members))


def test_lineup_event_replay_substitution_role_change_red_and_return(payload):
    match, raw, lineup = sequence(payload)
    _, events, passes, shots = normalize(match, raw, lineup)
    derived = derive(match, raw, events, passes, shots, lineup)
    stints = derived["lineup_stints"]
    assert active_players_at(stints, 10, 12) == {11, 12, 13}
    assert active_players_at(stints, 10, 13) == {12, 13, 14}
    assert active_players_at(stints, 10, 15) == {13, 14}
    assert active_players_at(stints, 10, 17) == {13}
    assert active_players_at(stints, 10, 18) == {13, 14}
    before = replay_active_players(1, raw, events, 10, 16)
    changed = deepcopy(raw)
    changed[16]["type"]["name"] = "Substitution"
    changed[16]["substitution"] = {"replacement": {"id": 99, "name": "Future player"}}
    _, changed_events, _, _ = normalize(match, changed, lineup)
    assert replay_active_players(1, changed, changed_events, 10, 16) == before == {13, 14}


def test_score_before_and_pressure_raw_vs_normalized(database, payload):
    match, raw, lineup = sequence(payload)
    _, sessions = database
    ingest_payload(sessions, match, raw, lineup)
    with sessions() as session:
        assert session.get(EventContext, str(UUID(int=6))).home_score_before == 0
        assert session.get(EventContext, str(UUID(int=7))).home_score_before == 1
        assert session.get(Event, str(UUID(int=3))).under_pressure is None
        context = session.get(EventContext, str(UUID(int=3)))
        assert context.pressure_value is False
        assert context.pressure_status == "omitted_false_supported_action"


def test_existing_m1_migrates_without_losing_rows(tmp_path, payload):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy = snapshot("m1")
    legacy.create_all(engine)
    match, events, passes, shots = normalize(*payload)
    with engine.begin() as connection:
        for name, rows in (
            ("matches", [match]),
            ("events", events),
            ("passes", passes),
            ("shots", shots),
        ):
            connection.execute(legacy.tables[name].insert(), rows)
    for _ in range(2):
        sessions = initialize(engine)
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 6
        assert session.get(Match, 1).home_score == 1
        assert session.execute(text("select version_num from alembic_version")).scalar() == "0003"
    assert "control_episodes" in inspect(engine).get_table_names()
    engine.dispose()


def test_unknown_unversioned_database_is_not_stamped(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'other.db'}")
    with engine.begin() as connection:
        connection.execute(text("create table unrelated (id integer primary key)"))
    with pytest.raises(RuntimeError, match="not the exact M1"):
        initialize(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()
    engine.dispose()


def test_sqlite_readers_can_query_during_ingestion(tmp_path):
    from sqlalchemy import text

    from tactigraph.config import Settings
    from tactigraph.db import make_engine

    engine = make_engine(
        Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'concurrent.db'}")
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe (value INTEGER)"))
        connection.execute(text("INSERT INTO probe VALUES (1)"))
    with engine.connect() as reader, engine.begin() as writer:
        writer.execute(text("INSERT INTO probe VALUES (2)"))
        assert reader.scalar(text("SELECT COUNT(*) FROM probe")) == 1
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM probe")) == 2
    engine.dispose()
