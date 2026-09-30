"""Allowlisted shot-time features from a strictly observed event prefix."""

import hashlib
import json
import math
from collections import Counter

import polars as pl

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.geometry import in_pitch
from tactigraph.data.ingest import period_milliseconds

FEATURE_VERSION = "shot-prefix-v1"
NUMERIC = [
    "x",
    "y",
    "distance",
    "opening_angle",
    "first_time",
    "pressure",
    "previous_elapsed_seconds",
    "assist_cross",
    "assist_cutback",
    "assist_x",
    "assist_y",
]
CATEGORICAL = [
    "body_part",
    "shot_type",
    "technique",
    "play_pattern",
    "previous_action",
    "assist_height",
]
FEATURES = NUMERIC + CATEGORICAL
CONTROLLED = {"Pass", "Carry", "Dribble", "Ball Recovery", "Interception", "Shot"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def named(value, field):
    return (value.get(field) or {}).get("name", "Unknown")


def feature_row(shot, prefix, schema="1.1.0"):
    """Never read labels, endpoints, shot-assist flags, identities, or future records."""
    location = shot.get("location", [])
    if len(location) < 2 or not in_pitch(*location[:2]):
        return None
    x, y = map(float, location[:2])
    dx = 120 - x
    # Goalposts at (120, 36) and (120, 44), in provider coordinate units.
    angle = math.atan2(abs(8 * dx), dx * dx + (36 - y) * (44 - y))
    body = shot["shot"]
    before = [e for e in prefix if e["index"] < shot["index"] and e["period"] == shot["period"]]
    own = [
        e
        for e in before
        if e.get("team", {}).get("id") == shot["team"]["id"]
        and e.get("possession") == shot.get("possession")
        and e["type"]["name"] in CONTROLLED
    ]
    previous = max(own, key=lambda e: e["index"], default=None)
    assist = next(
        (e for e in own if e["id"] == body.get("key_pass_id") and e["type"]["name"] == "Pass"), None
    )
    passing = assist.get("pass", {}) if assist else {}
    start = assist.get("location", []) if assist else []
    valid_start = len(start) >= 2 and in_pitch(*start[:2])
    elapsed = (
        (period_milliseconds(shot["timestamp"]) - period_milliseconds(previous["timestamp"])) / 1000
        if previous
        else None
    )
    supported = schema in {"1.0.2", "1.0.3", "1.1.0"}
    return {
        "x": x,
        "y": y,
        "distance": math.hypot(dx, y - 40),
        "opening_angle": angle,
        "first_time": int(body.get("first_time", False)) if supported else None,
        "pressure": int(shot.get("under_pressure", False)) if supported else None,
        "previous_elapsed_seconds": max(0, elapsed) if elapsed is not None else None,
        "assist_cross": int(passing.get("cross", False)) if assist else None,
        "assist_cutback": int(passing.get("cutback", False)) if assist else None,
        "assist_x": float(start[0]) if valid_start else None,
        "assist_y": float(start[1]) if valid_start else None,
        "body_part": named(body, "body_part"),
        "shot_type": named(body, "type"),
        "technique": named(body, "technique"),
        "play_pattern": named(shot, "play_pattern"),
        "previous_action": previous["type"]["name"] if previous else "None",
        "assist_height": named(passing, "height") if assist else "None",
    }


def match_samples(events, assignment, schema):
    rows, exclusions, prefix = [], Counter(), []
    for event in sorted(events, key=lambda e: e["index"]):
        if event["type"]["name"] == "Shot":
            if event["period"] == 5:
                exclusions["shootout"] += 1
            else:
                features = feature_row(event, prefix, schema)
                penalty = named(event["shot"], "type") == "Penalty"
                if features is None and not penalty:
                    exclusions["missing_or_outside_location"] += 1
                else:
                    rows.append(
                        {
                            "sample_id": event["id"],
                            "match_id": assignment["match_id"],
                            "season_id": assignment["season_id"],
                            "split": assignment["partition"],
                            "team_id": event["team"]["id"],
                            "home_team_id": assignment["home_team_id"],
                            "away_team_id": assignment["away_team_id"],
                            "penalty": penalty,
                            "label": int(named(event["shot"], "outcome") == "Goal"),
                            "reference_xg": event["shot"].get("statsbomb_xg"),
                            **(features or {f: None for f in FEATURES}),
                        }
                    )
        elif event["type"]["name"] in {"Own Goal Against", "Own Goal For"}:
            exclusions["own_goal_event_not_shot"] += 1
        prefix.append(event)
    return rows, exclusions


def build_dataset(settings, manifest, partitions):
    rows, exclusions, hashes = [], Counter(), {}
    root = settings.data_dir / "raw" / SOURCE_COMMIT / "data"
    schema = {}
    competition = manifest.get("competition_id", 37)
    for season in sorted({a["season_id"] for a in manifest["assignments"]}):
        for match in json.loads((root / f"matches/{competition}/{season}.json").read_bytes()):
            schema[match["match_id"]] = match.get("metadata", {}).get("data_version", "unknown")
    for assignment in manifest["assignments"]:
        if assignment["partition"] not in partitions:
            continue
        path = root / f"events/{assignment['match_id']}.json"
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if path.with_suffix(".sha256").read_text().strip() != checksum:
            raise ValueError(f"Source hash mismatch: {path.name}")
        hashes[str(assignment["match_id"])] = checksum
        samples, excluded = match_samples(
            json.loads(content), assignment, schema[assignment["match_id"]]
        )
        rows.extend(samples)
        exclusions.update(excluded)
    return rows, {
        "exclusions": dict(exclusions),
        "source_hashes": hashes,
        "feature_version": FEATURE_VERSION,
    }


def save_samples(path, rows):
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
