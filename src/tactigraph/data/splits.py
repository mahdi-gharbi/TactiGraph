"""Outcome-blind, immutable chronological split assignment."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import delete

from tactigraph.config import SOURCE_COMMIT
from tactigraph.db import SplitAssignment


def manifest_digest(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_manifest(matches):
    if matches and all(m.get("competition", {}).get("competition_id") == 2 for m in matches):
        return build_premier_manifest(matches)
    ids = [m["match_id"] for m in matches]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate match IDs in split catalog")
    development = sorted(
        (m for m in matches if m["season"]["season_id"] == 90),
        key=lambda m: (m["match_date"], m["match_id"]),
    )
    dates = sorted({m["match_date"] for m in development})
    if len(dates) < 2:
        raise ValueError("At least two 2020/21 match dates required")
    boundary = min(
        dates[:-1],
        key=lambda date: (
            abs(sum(m["match_date"] <= date for m in development) - len(development) * 2 / 3),
            date,
        ),
    )
    assignments = []
    for m in sorted(matches, key=lambda m: (m["match_date"], m["match_id"])):
        season = m["season"]["season_id"]
        if season in {4, 42}:
            partition = "train"
        elif season == 90:
            partition = "tuning" if m["match_date"] <= boundary else "calibration"
        elif season == 281:
            partition = "test"
        else:
            raise ValueError(f"Unsupported season {season}")
        assignments.append(
            {
                "match_id": m["match_id"],
                "season_id": season,
                "match_date": m["match_date"],
                "partition": partition,
                "home_team_id": m["home_team"]["home_team_id"],
                "away_team_id": m["away_team"]["away_team_id"],
            }
        )
    if any(
        not any(a["partition"] == p for a in assignments)
        for p in ("train", "tuning", "calibration", "test")
    ):
        raise ValueError("Every partition must contain matches")
    team_ids = sorted({a[f"{side}_team_id"] for a in assignments for side in ("home", "away")})
    body = {
        "version": "wsl-chronological-v1",
        "source_commit": SOURCE_COMMIT,
        "algorithm": "Closest 2/3 tuning count at a whole-date boundary; earliest tie wins",
        "tuning_last_date": boundary,
        "assignments": assignments,
        "team_stress_groups": {str(t): i % 5 for i, t in enumerate(team_ids)},
        "counts": dict(Counter(a["partition"] for a in assignments)),
    }
    return {**body, "sha256": manifest_digest(body)}


def build_premier_manifest(matches):
    """Outcome-blind 60/15/10/15 split, keeping entire match dates together."""
    ordered = sorted(matches, key=lambda m: (m["match_date"], m["match_id"]))
    if len({m["match_id"] for m in ordered}) != len(ordered):
        raise ValueError("Duplicate match IDs in split catalog")
    if any(m["season"]["season_id"] != 27 for m in ordered):
        raise ValueError("Premier League v1 supports only 2015/16")
    dates = sorted({m["match_date"] for m in ordered})
    if len(dates) < 4:
        raise ValueError("At least four match dates required")
    boundaries = []
    for index, fraction in enumerate((0.60, 0.75, 0.85)):
        candidates = [d for d in dates[: -(3 - index)] if not boundaries or d > boundaries[-1]]
        boundaries.append(
            min(
                candidates,
                key=lambda d: (
                    abs(sum(m["match_date"] <= d for m in ordered) - len(ordered) * fraction),
                    d,
                ),
            )
        )
    names = ("train", "tuning", "calibration", "test")
    assignments = [
        {
            "match_id": m["match_id"],
            "season_id": 27,
            "match_date": m["match_date"],
            "partition": names[sum(m["match_date"] > d for d in boundaries)],
            "home_team_id": m["home_team"]["home_team_id"],
            "away_team_id": m["away_team"]["away_team_id"],
        }
        for m in ordered
    ]
    teams = sorted({a[f"{side}_team_id"] for a in assignments for side in ("home", "away")})
    body = {
        "version": "premier-league-chronological-v1",
        "competition_id": 2,
        "source_commit": SOURCE_COMMIT,
        "algorithm": (
            "Closest cumulative 60/75/85 percent at whole-date boundaries; earliest tie wins"
        ),
        "boundaries": boundaries,
        "assignments": assignments,
        "team_stress_groups": {str(t): i % 5 for i, t in enumerate(teams)},
        "counts": dict(Counter(a["partition"] for a in assignments)),
    }
    return {**body, "sha256": manifest_digest(body)}


def freeze_manifest(matches, path: Path, session_factory):
    expected = build_manifest(matches)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != expected:
            raise ValueError(
                "Immutable split manifest differs; use a reviewed new manifest version"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(expected, handle, indent=2)
            handle.write("\n")
    with session_factory.begin() as session:
        existing = session.query(SplitAssignment).all()
        if existing and any(row.manifest_hash != expected["sha256"] for row in existing):
            raise ValueError("Database split manifest is incompatible with frozen file")
        session.execute(delete(SplitAssignment))
        session.add_all(
            SplitAssignment(
                match_id=a["match_id"],
                season_id=a["season_id"],
                match_date=a["match_date"],
                partition=a["partition"],
                manifest_hash=expected["sha256"],
            )
            for a in expected["assignments"]
        )
    return expected
