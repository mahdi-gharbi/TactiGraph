from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from tactigraph.db import initialize


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = initialize(engine)
    yield engine, factory
    engine.dispose()


@pytest.fixture
def payload():
    """Entirely invented data: no redistribution of upstream match records."""
    match = {
        "match_id": 1,
        "match_date": "2018-09-09",
        "competition": {"competition_id": 37, "competition_name": "Synthetic WSL fixture"},
        "season": {"season_id": 4, "season_name": "2018/2019"},
        "home_team": {"home_team_id": 10, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": 20, "away_team_name": "Away FC"},
        "home_score": 1,
        "away_score": 0,
        "metadata": {"data_version": "1.0.3"},
    }
    events = []
    for index, period, timestamp, minute, team, kind, outcome in [
        (1, 1, "00:00:00.000", 0, 10, "Pass", None),
        (2, 1, "00:10:00.000", 10, 10, "Shot", "Goal"),
        (3, 1, "00:45:30.000", 45, 20, "Shot", "Saved"),
        (4, 2, "00:00:00.000", 45, 10, "Shot", "Off T"),
        (5, 2, "00:15:00.000", 60, 20, "Shot", "Blocked"),
        (6, 5, "00:01:00.000", 120, 10, "Shot", "Goal"),
    ]:
        event = {
            "id": str(UUID(int=index)),
            "index": index,
            "period": period,
            "timestamp": timestamp,
            "minute": minute,
            "second": 0,
            "type": {"name": kind},
            "team": {"id": team, "name": "Home FC" if team == 10 else "Away FC"},
            "player": {"id": team + 1, "name": f"Player {team + 1}"},
            "possession": index,
            "possession_team": {"id": team},
            "location": [100, 40],
        }
        if kind == "Pass":
            event["pass"] = {
                "recipient": {"id": 12, "name": "Player 12"},
                "end_location": [110, 40],
                "length": 10,
            }
        else:
            event["shot"] = {
                "outcome": {"name": outcome},
                "body_part": {"name": "Right Foot"},
                "type": {"name": "Open Play"},
            }
        events.append(event)
    del events[4]["location"]  # An unlocated shot must still count.
    return deepcopy((match, events, [{"team_id": 10, "lineup": []}, {"team_id": 20, "lineup": []}]))
