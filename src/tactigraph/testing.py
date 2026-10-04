"""Invented, deterministic integration fixtures. Never load these into a research database."""

import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from tactigraph.data.ingest import ingest_payload
from tactigraph.db import Match, ModelRelease, Prediction, PredictionSample

MATCH_ID = 900001
SYNTHETIC_VERSION = "synthetic-ci-v1"
FIXED_TIME = datetime(2020, 1, 1, tzinfo=timezone.utc)


def synthetic_payload():
    """One invented match with known second-half windows, lineups, passes and four shots."""
    match = {
        "match_id": MATCH_ID,
        "match_date": "2020-01-01",
        "competition": {"competition_id": 999, "competition_name": "Synthetic CI fixture"},
        "season": {"season_id": 999, "season_name": "Invented test season"},
        "home_team": {"home_team_id": 10, "home_team_name": "Synthetic Home FC"},
        "away_team": {"away_team_id": 20, "away_team_name": "Synthetic Away FC"},
        "home_score": 1,
        "away_score": 0,
        "metadata": {"data_version": "1.1.0"},
    }
    names = {10: "Synthetic Home FC", 20: "Synthetic Away FC"}
    lineups = [
        {
            "team_id": team,
            "lineup": [
                {"player_id": team + i, "player_name": f"Synthetic player {team + i}"}
                for i in range(1, 4)
            ],
        }
        for team in (10, 20)
    ]
    events = []

    def add(kind, period, seconds, team, player=None, **details):
        index = len(events) + 1
        event = {
            "id": str(UUID(int=MATCH_ID * 1000 + index)),
            "index": index,
            "period": period,
            "timestamp": f"00:{seconds // 60:02d}:{seconds % 60:02d}.000",
            "minute": (45 if period == 2 else 0) + seconds // 60,
            "second": seconds % 60,
            "team": {"id": team, "name": names[team]},
            "type": {"name": kind},
            "possession": index,
            "possession_team": {"id": team, "name": names[team]},
            "play_pattern": {"name": "Regular Play"},
            **details,
        }
        if player is not None:
            event["player"] = {"id": player, "name": f"Synthetic player {player}"}
        events.append(event)

    for team in (10, 20):
        add(
            "Starting XI",
            1,
            0,
            team,
            tactics={
                "formation": 433,
                "lineup": [
                    {
                        "player": {"id": team + i, "name": f"Synthetic player {team + i}"},
                        "position": {"id": i, "name": "Synthetic position"},
                        "jersey_number": i,
                    }
                    for i in range(1, 4)
                ],
            },
        )
    add("Half End", 1, 2700, 10)
    for window in range(2):
        for i in range(40):
            team = 20 if i % 5 == 0 else 10
            player = team + 1 + i % 3
            recipient = team + 1 + (i + 1) % 3
            add(
                "Pass",
                2,
                window * 900 + i * 20,
                team,
                player,
                location=[70.0 if window == 0 else 65.0, 35.0],
                **{
                    "pass": {
                        "recipient": {"id": recipient, "name": f"Synthetic player {recipient}"},
                        "end_location": [85.0 if window == 0 else 75.0, 40.0],
                        "length": 15.0,
                        "height": {"name": "Ground Pass"},
                        "body_part": {"name": "Right Foot"},
                    }
                },
            )
        for j in range(1 if window == 0 else 3):
            team = 20 if j == 2 else 10
            add(
                "Shot",
                2,
                window * 900 + 810 + j * 20,
                team,
                team + 1,
                location=[100.0, 40.0],
                shot={
                    "outcome": {"name": "Goal" if window == 1 and j == 0 else "Saved"},
                    "body_part": {"name": "Right Foot"},
                    "type": {"name": "Open Play"},
                },
            )
    add("Half End", 2, 2700, 10)
    return match, events, lineups


def seed_synthetic(sessions):
    """Require an empty migrated DB; seed hashed invented data and fixed test probabilities."""
    with sessions() as session:
        if session.scalar(select(func.count()).select_from(Match)):
            raise ValueError("Synthetic seed requires an empty dedicated database")
    match, events, lineups = synthetic_payload()
    manifests = [
        {
            "path": path,
            "commit": SYNTHETIC_VERSION,
            "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "retrieved_at": FIXED_TIME,
            "schema_version": "invented-fixture",
            "validation_status": "valid",
        }
        for path, payload in (
            (f"data/events/{MATCH_ID}.json", events),
            (f"data/lineups/{MATCH_ID}.json", lineups),
        )
    ]
    ingest_payload(sessions, match, events, lineups, manifests)
    shots = [event for event in events if event["type"]["name"] == "Shot"]
    scores = {
        "log_loss": -(math.log(0.25) + 3 * math.log(0.75)) / 4,
        "brier": 0.1875,
        "roc_auc": 0.5,
        "pr_auc": 0.25,
        "n": 4,
        "goals": 1,
    }
    report = {
        "version": SYNTHETIC_VERSION,
        "status": "synthetic_fixture",
        "serving": "synthetic_constant",
        "evaluated_at": FIXED_TIME.isoformat(),
        "lock": {"artifact_hash": manifests[0]["sha256"], "run_id": SYNTHETIC_VERSION},
        "test_matches": 1,
        "test_non_penalty_shots": 4,
        "metrics": {
            "synthetic_constant": {
                **scores,
                "intervals": {},
                "reliability": [],
                "calibration": None,
            }
        },
        "paired_lightgbm_minus_logistic": {},
        "reference": {"name": "No reference for invented data", "metrics": None},
        "penalties": {"probability": 0.0, "test_metrics": None},
        "slices": [],
        "logistic_coefficients": [],
        "permutation_importance": [],
        "team_stress": [],
        "prediction_batch_ms": 0.0,
        "limitations": ["Invented fixture; fixed test probabilities, not fitted model results."],
        "development": {
            "search": [],
            "calibration_decisions": {},
            "tuning_paired_difference": {},
            "counts": {},
            "penalty": {},
            "protocol": {},
        },
        "feature_names": [],
    }
    with sessions.begin() as session:
        session.get(Match, MATCH_ID).source_commit = SYNTHETIC_VERSION
        session.add(
            ModelRelease(
                id=SYNTHETIC_VERSION,
                family="synthetic_constant",
                status="evaluated",
                artifact_hash=manifests[0]["sha256"],
                run_id=SYNTHETIC_VERSION,
                feature_version=SYNTHETIC_VERSION,
                source_commit=SYNTHETIC_VERSION,
                created_at=FIXED_TIME,
                report=report,
            )
        )
        session.flush()
        for event in shots:
            session.add(
                PredictionSample(
                    id=event["id"],
                    match_id=MATCH_ID,
                    task="xg",
                    split="test",
                    feature_version=SYNTHETIC_VERSION,
                    label=event["shot"]["outcome"]["name"] == "Goal",
                    penalty=False,
                    features={"synthetic": True},
                )
            )
        session.flush()
        session.add_all(
            Prediction(sample_id=event["id"], model_version=SYNTHETIC_VERSION, probability=0.25)
            for event in shots
        )
    return {"match_id": MATCH_ID, "events": len(events), "predictions": len(shots)}
